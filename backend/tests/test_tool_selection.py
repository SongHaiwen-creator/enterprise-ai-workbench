from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.services.tool_registry import TOOL_REGISTRY
from app.services.tool_selection import (
    TOOL_SELECTOR_INPUT_TOO_LARGE,
    TOOL_SELECTOR_PROVIDER_FAILURE,
    LazyOpenAIToolSelector,
    OpenAIToolSelector,
    ToolSelectionConfigurationError,
    ToolSelectionDecline,
    ToolSelectionInputTooLargeError,
    ToolSelectionProposal,
    ToolSelectionProviderError,
    create_openai_tool_selector,
)

JWT_SECRET = "tool-selector-secret-longer-than-thirty-two-bytes"


class RecordingEncoding:
    def __init__(self, token_count: int = 100) -> None:
        self.token_count = token_count
        self.inputs: list[str] = []

    def encode(self, text: str, *, disallowed_special: object = ()) -> list[int]:
        del disallowed_special
        self.inputs.append(text)
        return list(range(self.token_count))


class FakeResponses:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def function_call(name: str, arguments: str) -> object:
    return SimpleNamespace(type="function_call", name=name, arguments=arguments)


def response(*output: object, status: str = "completed", model: str = "gpt-5.6-terra") -> object:
    return SimpleNamespace(status=status, model=model, output=list(output))


def selector(
    resource: FakeResponses, *, encoding: RecordingEncoding | None = None
) -> OpenAIToolSelector:
    return OpenAIToolSelector(
        SimpleNamespace(responses=resource),  # type: ignore[arg-type]
        model="gpt-5.6-terra",
        reasoning_effort="low",
        prompt_version="enterprise-tool-selector-v1",
        max_input_tokens=8000,
        max_output_tokens=512,
        encoding=encoding or RecordingEncoding(),
    )


def test_selector_uses_one_strict_minimized_function_call() -> None:
    resource = FakeResponses(response(function_call("get_reimbursement_status", "{}")))
    encoding = RecordingEncoding()
    service = selector(resource, encoding=encoding)
    candidates = (TOOL_REGISTRY["get_reimbursement_status"],)

    result = service.select("Where is my claim?", "Handle employee service.", candidates)

    assert result == ToolSelectionProposal("get_reimbursement_status", {})
    assert len(resource.calls) == 1
    call = resource.calls[0]
    assert call["model"] == "gpt-5.6-terra"
    assert call["reasoning"] == {"effort": "low"}
    assert call["max_output_tokens"] == 512
    assert call["tool_choice"] == "required"
    assert call["parallel_tool_calls"] is False
    assert call["truncation"] == "disabled"
    assert call["store"] is False
    assert call["stream"] is False
    assert call["background"] is False
    assert set(call) == {
        "model", "instructions", "input", "tools", "tool_choice",
        "parallel_tool_calls", "reasoning", "max_output_tokens", "truncation",
        "store", "stream", "background",
    }
    tools = call["tools"]
    assert isinstance(tools, list)
    assert [item["name"] for item in tools] == [
        "get_reimbursement_status", "decline_tool_selection"
    ]
    assert all(item["strict"] is True for item in tools)
    assert "workspace_id" not in str(call)
    assert "user_id" not in str(call)
    assert "risk" not in str((call["input"], call["tools"]))
    assert "endpoint" not in str((call["input"], call["tools"]))
    assert "untrusted data" in str(call["instructions"])
    assert len(encoding.inputs) == 1


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        ('{"reason":"no_matching_capability"}', "no_matching_capability"),
        ('{"reason":"missing_required_arguments"}', "missing_required_arguments"),
    ],
)
def test_selector_accepts_only_typed_decline(arguments: str, expected: str) -> None:
    service = selector(
        FakeResponses(response(function_call("decline_tool_selection", arguments)))
    )
    result = service.select(
        "Request", "Scope", (TOOL_REGISTRY["get_employee_information"],)
    )
    assert result == ToolSelectionDecline(reason=expected)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "bad_response",
    [
        response(status="incomplete"),
        response(model="wrong-model"),
        response(),
        response(function_call("unknown_tool", "{}")),
        response(function_call("get_reimbursement_status", "[]")),
        response(function_call("get_reimbursement_status", '{"x":1,"x":2}')),
        response(
            function_call("get_reimbursement_status", "{}"),
            function_call("decline_tool_selection", '{"reason":"no_matching_capability"}'),
        ),
        response(SimpleNamespace(type="message")),
    ],
)
def test_selector_rejects_malformed_or_unavailable_calls(bad_response: object) -> None:
    with pytest.raises(ToolSelectionProviderError, match=TOOL_SELECTOR_PROVIDER_FAILURE):
        selector(FakeResponses(bad_response)).select(
            "private request",
            "private scope",
            (TOOL_REGISTRY["get_reimbursement_status"],),
        )


def test_selector_checks_complete_local_input_budget_before_call() -> None:
    resource = FakeResponses(response(function_call("get_reimbursement_status", "{}")))
    service = selector(resource, encoding=RecordingEncoding(token_count=8001))
    with pytest.raises(
        ToolSelectionInputTooLargeError, match=TOOL_SELECTOR_INPUT_TOO_LARGE
    ):
        service.select(
            "Request", "Scope", (TOOL_REGISTRY["get_reimbursement_status"],)
        )
    assert resource.calls == []


def test_lazy_selector_requires_configuration_only_when_called() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://unused/unused",
        jwt_secret_key=JWT_SECRET,
        openai_api_key=None,
        _env_file=None,
    )
    lazy = LazyOpenAIToolSelector(settings)
    with pytest.raises(ToolSelectionConfigurationError, match="not configured"):
        lazy.select(
            "Request", "Scope", (TOOL_REGISTRY["get_reimbursement_status"],)
        )


def test_selector_factory_uses_fixed_client_and_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client_arguments: dict[str, object] = {}

    def fake_openai(**kwargs: object) -> object:
        client_arguments.update(kwargs)
        return SimpleNamespace(responses=FakeResponses(response()))

    monkeypatch.setattr("app.services.tool_selection.OpenAI", fake_openai)
    monkeypatch.setattr(
        "app.services.tool_selection.tiktoken.encoding_for_model",
        lambda model: RecordingEncoding(),
    )
    settings = Settings(
        database_url="postgresql+psycopg://unused/unused",
        jwt_secret_key=JWT_SECRET,
        openai_api_key="selector-secret",
        _env_file=None,
    )

    service = create_openai_tool_selector(settings)

    assert client_arguments == {
        "api_key": "selector-secret", "timeout": 30.0, "max_retries": 0
    }
    assert service.model == "gpt-5.6-terra"
    assert service.reasoning_effort == "low"
    assert service.prompt_version == "enterprise-tool-selector-v1"
    assert service.max_input_tokens == 8000
    assert service.max_output_tokens == 512
