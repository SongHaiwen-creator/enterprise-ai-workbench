from types import SimpleNamespace

import pytest
from pydantic import TypeAdapter, ValidationError

from app.core.config import Settings
from app.schemas.agent_routing import AgentRouteResponse, ModelRoutingOutput, RoutingIntent
from app.services.routing import (
    ROUTING_INPUT_TOO_LARGE,
    ROUTING_PROVIDER_FAILURE,
    LazyOpenAIRoutingProvider,
    OpenAIRoutingProvider,
    RoutingConfigurationError,
    RoutingInputTooLargeError,
    RoutingProviderError,
    create_openai_routing_provider,
)

JWT_SECRET = "routing-test-secret-longer-than-thirty-two-bytes"


class RecordingEncoding:
    def __init__(self, *, token_count: int | None = None) -> None:
        self.token_count = token_count
        self.inputs: list[str] = []

    def encode(self, text: str, *, disallowed_special: object = ()) -> list[int]:
        del disallowed_special
        self.inputs.append(text)
        return list(range(self.token_count if self.token_count is not None else len(text)))


class FakeResponses:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def parse(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def response(
    *,
    output: object | None = None,
    status: str = "completed",
    model: str = "gpt-5.6-terra",
) -> object:
    return SimpleNamespace(
        status=status,
        model=model,
        output_parsed=output,
    )


def provider(
    resource: FakeResponses,
    *,
    encoding: RecordingEncoding | None = None,
    max_input_tokens: int = 8000,
) -> OpenAIRoutingProvider:
    return OpenAIRoutingProvider(
        SimpleNamespace(responses=resource),  # type: ignore[arg-type]
        model="gpt-5.6-terra",
        reasoning_effort="low",
        prompt_version="agent-intent-routing-v1",
        max_input_tokens=max_input_tokens,
        max_output_tokens=64,
        encoding=encoding or RecordingEncoding(token_count=100),
    )


@pytest.mark.parametrize("intent", list(RoutingIntent))
def test_provider_uses_strict_minimized_contract(intent: RoutingIntent) -> None:
    resource = FakeResponses(response(output=ModelRoutingOutput(intent=intent)))
    encoding = RecordingEncoding(token_count=250)
    service = provider(resource, encoding=encoding)
    request = "What is my private reimbursement status?"
    prompt = "Route employee service topics only."

    result = service.route(request, prompt)

    assert result is intent
    assert len(resource.calls) == 1
    call = resource.calls[0]
    assert call["model"] == "gpt-5.6-terra"
    assert call["reasoning"] == {"effort": "low"}
    assert call["max_output_tokens"] == 64
    assert call["truncation"] == "disabled"
    assert call["tools"] == []
    assert call["parallel_tool_calls"] is False
    assert call["store"] is False
    assert call["stream"] is False
    assert call["background"] is False
    assert call["text_format"] is ModelRoutingOutput
    assert set(call) == {
        "model", "instructions", "input", "text_format", "reasoning",
        "max_output_tokens", "truncation", "tools", "parallel_tool_calls",
        "store", "stream", "background",
    }
    assert request in str(call["input"])
    assert prompt in str(call["input"])
    assert "agent_system_prompt" in str(call["input"])
    assert "workspace_id" not in str(call["input"])
    assert "knowledge_base_id" not in str(call["input"])
    assert "created_by" not in str(call["input"])
    assert "tool_args" not in str(call["input"])
    assert "untrusted data" in str(call["instructions"])
    assert len(encoding.inputs) == 1
    assert request in encoding.inputs[0]
    assert prompt in encoding.inputs[0]
    assert "ModelRoutingOutput" in encoding.inputs[0]


def test_input_budget_is_checked_before_provider_call() -> None:
    resource = FakeResponses(response(output=ModelRoutingOutput(intent="tool_request")))
    service = provider(
        resource,
        encoding=RecordingEncoding(token_count=8001),
    )

    with pytest.raises(RoutingInputTooLargeError, match=ROUTING_INPUT_TOO_LARGE):
        service.route("Question", "Scope")

    assert resource.calls == []


@pytest.mark.parametrize(
    "bad_response",
    [
        response(output=None),
        response(output=ModelRoutingOutput(intent="knowledge_qa"), status="incomplete"),
        response(output=ModelRoutingOutput(intent="knowledge_qa"), model="wrong-model"),
        response(output={"intent": "tool_request"}),
        response(output=SimpleNamespace(intent="tool_request")),
    ],
)
def test_provider_rejects_unvalidated_or_incomplete_output(bad_response: object) -> None:
    with pytest.raises(RoutingProviderError, match=ROUTING_PROVIDER_FAILURE):
        provider(FakeResponses(bad_response)).route("Question", "Scope")


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"intent": "unknown"},
        {"intent": "tool_request", "reason": "private"},
        {"intent": "knowledge_qa", "tool_name": "finance"},
    ],
)
def test_model_output_schema_rejects_missing_unknown_or_extra_fields(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        ModelRoutingOutput.model_validate(payload)


def test_provider_failure_is_sanitized() -> None:
    request = "private employee request"
    prompt = "private Agent scope"
    resource = FakeResponses(AttributeError(f"upstream echoed {request} and {prompt}"))

    with pytest.raises(RoutingProviderError) as exc_info:
        provider(resource).route(request, prompt)

    assert str(exc_info.value) == ROUTING_PROVIDER_FAILURE
    assert request not in str(exc_info.value)
    assert prompt not in str(exc_info.value)


def test_provider_timeout_is_sanitized() -> None:
    resource = FakeResponses(TimeoutError("upstream timeout with private request"))
    with pytest.raises(RoutingProviderError, match=ROUTING_PROVIDER_FAILURE):
        provider(resource).route("private request", "private scope")


def test_public_response_union_rejects_cross_intent_outcome() -> None:
    response_adapter = TypeAdapter(AgentRouteResponse)
    with pytest.raises(ValidationError):
        response_adapter.validate_python(
            {
                "request": "Question",
                "intent": "tool_request",
                "outcome": {
                    "status": "unsupported",
                    "message": "Wrong outcome for this intent.",
                },
            }
        )


def test_provider_requires_configuration_and_lazy_setup() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://unused/unused",
        jwt_secret_key=JWT_SECRET,
        openai_api_key=None,
        _env_file=None,
    )
    lazy = LazyOpenAIRoutingProvider(settings)
    with pytest.raises(RoutingConfigurationError, match="not configured"):
        lazy.route("Question", "Scope")


def test_factory_uses_fixed_client_and_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    client_arguments: dict[str, object] = {}
    encoding = RecordingEncoding(token_count=100)

    def fake_openai(**kwargs: object) -> object:
        client_arguments.update(kwargs)
        return SimpleNamespace(responses=FakeResponses(response()))

    monkeypatch.setattr("app.services.routing.OpenAI", fake_openai)
    monkeypatch.setattr("app.services.routing.tiktoken.encoding_for_model", lambda model: encoding)
    settings = Settings(
        database_url="postgresql+psycopg://unused/unused",
        jwt_secret_key=JWT_SECRET,
        openai_api_key="routing-secret",
        _env_file=None,
    )

    service = create_openai_routing_provider(settings)

    assert client_arguments == {
        "api_key": "routing-secret",
        "timeout": 30.0,
        "max_retries": 0,
    }
    assert service.model == "gpt-5.6-terra"
    assert service.reasoning_effort == "low"
    assert service.prompt_version == "agent-intent-routing-v1"
    assert service.max_input_tokens == 8000
    assert service.max_output_tokens == 64
