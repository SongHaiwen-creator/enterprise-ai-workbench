from fractions import Fraction
from types import SimpleNamespace

import httpx2
import pytest
from openai import APIError

from app.core.config import Settings
from app.services.embeddings import (
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_MAX_INPUT_TOKENS,
    EMBEDDING_REQUEST_TOKEN_BUDGET,
    EmbeddingConfigurationError,
    EmbeddingProviderError,
    OpenAIEmbeddingProvider,
    create_openai_embedding_provider,
)

JWT_SECRET = "embedding-test-secret-longer-than-thirty-two-bytes"


class Utf8TokenEncoding:
    def encode(
        self,
        text: str,
        *,
        disallowed_special: object = (),
    ) -> list[int]:
        del disallowed_special
        return list(text.encode("utf-8"))


TEST_ENCODING = Utf8TokenEncoding()


class FakeEmbeddingsResource:
    def __init__(self, *, model: str = "test-model", dimensions: int = 3) -> None:
        self.model = model
        self.dimensions = dimensions
        self.calls: list[dict[str, object]] = []
        self.error: Exception | None = None

    def create(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        inputs = kwargs["input"]
        assert isinstance(inputs, list)
        return SimpleNamespace(
            model=self.model,
            data=[
                SimpleNamespace(index=index, embedding=[float(index + 1)] * self.dimensions)
                for index in range(len(inputs))
            ],
        )


def provider(resource: FakeEmbeddingsResource) -> OpenAIEmbeddingProvider:
    client = SimpleNamespace(embeddings=resource)
    return OpenAIEmbeddingProvider(
        client,  # type: ignore[arg-type]
        model="test-model",
        dimensions=3,
        encoding=TEST_ENCODING,
    )


def test_embedding_provider_batches_and_preserves_order() -> None:
    resource = FakeEmbeddingsResource()
    service = provider(resource)
    texts = [f"text-{index}" for index in range(EMBEDDING_BATCH_SIZE + 1)]

    embeddings = service.embed_texts(texts)

    assert [len(call["input"]) for call in resource.calls] == [EMBEDDING_BATCH_SIZE, 1]
    assert all(call["model"] == "test-model" for call in resource.calls)
    assert all(call["dimensions"] == 3 for call in resource.calls)
    assert all(call["encoding_format"] == "float" for call in resource.calls)
    assert embeddings[0] == [1.0, 1.0, 1.0]
    assert embeddings[-1] == [1.0, 1.0, 1.0]


def test_embedding_provider_batches_high_token_density_inputs_within_budget() -> None:
    resource = FakeEmbeddingsResource()
    service = provider(resource)
    high_density_text = "漢字政策🔐🚀" * 300
    per_input_tokens = len(TEST_ENCODING.encode(high_density_text, disallowed_special=()))
    assert 0 < per_input_tokens <= EMBEDDING_MAX_INPUT_TOKENS
    texts = [high_density_text for _ in range(100)]

    embeddings = service.embed_texts(texts)

    assert len(resource.calls) > 1
    assert len(embeddings) == len(texts)
    for call in resource.calls:
        inputs = call["input"]
        assert isinstance(inputs, list)
        assert len(inputs) <= EMBEDDING_BATCH_SIZE
        assert (
            sum(len(TEST_ENCODING.encode(text, disallowed_special=())) for text in inputs)
            <= EMBEDDING_REQUEST_TOKEN_BUDGET
        )
    assert [text for call in resource.calls for text in call["input"]] == texts


def test_embedding_provider_rejects_oversized_input_before_request() -> None:
    resource = FakeEmbeddingsResource()
    oversized = "🔐" * 5_000
    assert len(TEST_ENCODING.encode(oversized, disallowed_special=())) > EMBEDDING_MAX_INPUT_TOKENS

    with pytest.raises(EmbeddingProviderError, match="Embedding provider request failed"):
        provider(resource).embed_texts([oversized])

    assert resource.calls == []


@pytest.mark.parametrize(
    "response",
    [
        None,
        SimpleNamespace(model="wrong-model", data=[]),
        SimpleNamespace(model=123, data=[]),
        SimpleNamespace(model="test-model", data=None),
        SimpleNamespace(model="test-model", data=[]),
        SimpleNamespace(model="test-model", data=[SimpleNamespace()]),
        SimpleNamespace(
            model="test-model",
            data=[SimpleNamespace(index=0, embedding=[1.0, 2.0])],
        ),
        SimpleNamespace(
            model="test-model",
            data=[
                SimpleNamespace(index=0, embedding=[1.0, 2.0, 3.0]),
                SimpleNamespace(index=0, embedding=[1.0, 2.0, 3.0]),
            ],
        ),
        SimpleNamespace(
            model="test-model",
            data=[SimpleNamespace(index=True, embedding=[1.0, 2.0, 3.0])],
        ),
        SimpleNamespace(
            model="test-model",
            data=[SimpleNamespace(index="0", embedding=[1.0, 2.0, 3.0])],
        ),
        SimpleNamespace(
            model="test-model",
            data=[SimpleNamespace(index=1, embedding=[1.0, 2.0, 3.0])],
        ),
        SimpleNamespace(
            model="test-model",
            data=[SimpleNamespace(index=0, embedding="not-a-vector")],
        ),
        SimpleNamespace(
            model="test-model",
            data=[SimpleNamespace(index=0, embedding=[1.0, True, 3.0])],
        ),
        SimpleNamespace(
            model="test-model",
            data=[SimpleNamespace(index=0, embedding=[1.0, None, 3.0])],
        ),
        SimpleNamespace(
            model="test-model",
            data=[SimpleNamespace(index=0, embedding=[1.0, "2", 3.0])],
        ),
        SimpleNamespace(
            model="test-model",
            data=[SimpleNamespace(index=0, embedding=[1.0, float("nan"), 3.0])],
        ),
        SimpleNamespace(
            model="test-model",
            data=[SimpleNamespace(index=0, embedding=[1.0, float("inf"), 3.0])],
        ),
        SimpleNamespace(
            model="test-model",
            data=[SimpleNamespace(index=0, embedding=[1.0, Fraction(10**400), 3.0])],
        ),
        SimpleNamespace(
            model="test-model",
            data=[SimpleNamespace(index=0, embedding=[0.0, 0.0, 0.0])],
        ),
    ],
)
def test_embedding_provider_rejects_incompatible_responses(response: object) -> None:
    resource = FakeEmbeddingsResource()
    resource.create = lambda **kwargs: response  # type: ignore[method-assign]

    with pytest.raises(EmbeddingProviderError, match="Embedding provider request failed"):
        provider(resource).embed_texts(["text"])


def test_embedding_provider_reconstructs_out_of_order_response_by_index() -> None:
    resource = FakeEmbeddingsResource()
    resource.create = lambda **kwargs: SimpleNamespace(  # type: ignore[method-assign]
        model="test-model",
        data=[
            SimpleNamespace(index=1, embedding=[2.0, 2.0, 2.0]),
            SimpleNamespace(index=0, embedding=[1.0, 1.0, 1.0]),
        ],
    )

    assert provider(resource).embed_texts(["first", "second"]) == [
        [1.0, 1.0, 1.0],
        [2.0, 2.0, 2.0],
    ]


def test_embedding_provider_sanitizes_api_errors(
    caplog: pytest.LogCaptureFixture,
) -> None:
    resource = FakeEmbeddingsResource()
    api_key = "sk-sensitive-test-value"
    query_text = "private employee search query"
    resource.error = APIError(
        "provider body containing sensitive text",
        httpx2.Request(
            "POST",
            "https://api.openai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {api_key}"},
        ),
        body={"detail": "sensitive"},
    )

    with pytest.raises(EmbeddingProviderError) as exc_info:
        provider(resource).embed_texts(["private document text", query_text])

    assert str(exc_info.value) == "Embedding provider request failed"
    assert "sensitive" not in str(exc_info.value)
    assert "private" not in str(exc_info.value)
    assert api_key not in caplog.text
    assert "private document text" not in caplog.text
    assert query_text not in caplog.text
    assert "provider body containing sensitive text" not in caplog.text


def test_embedding_provider_requires_environment_configuration() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://unused/unused",
        jwt_secret_key=JWT_SECRET,
        openai_api_key=" ",
        _env_file=None,
    )

    with pytest.raises(EmbeddingConfigurationError, match="not configured"):
        create_openai_embedding_provider(settings)


def test_embedding_provider_resolves_tokenizer_for_exact_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested_models: list[str] = []

    def encoding_for_model(model: str) -> Utf8TokenEncoding:
        requested_models.append(model)
        return TEST_ENCODING

    monkeypatch.setattr("app.services.embeddings.tiktoken.encoding_for_model", encoding_for_model)
    resource = FakeEmbeddingsResource(model="text-embedding-3-small", dimensions=1536)
    OpenAIEmbeddingProvider(
        SimpleNamespace(embeddings=resource),  # type: ignore[arg-type]
        model="text-embedding-3-small",
        dimensions=1536,
    )

    assert requested_models == ["text-embedding-3-small"]


def test_embedding_provider_does_not_fallback_for_unknown_model_tokenizer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_encoding_lookup(model: str) -> Utf8TokenEncoding:
        raise KeyError(model)

    monkeypatch.setattr("app.services.embeddings.tiktoken.encoding_for_model", fail_encoding_lookup)

    with pytest.raises(EmbeddingConfigurationError, match="tokenizer is not configured"):
        OpenAIEmbeddingProvider(
            SimpleNamespace(embeddings=FakeEmbeddingsResource()),  # type: ignore[arg-type]
            model="unknown-model",
            dimensions=3,
        )
