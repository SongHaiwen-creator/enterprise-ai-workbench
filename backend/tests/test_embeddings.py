from types import SimpleNamespace

import httpx2
import pytest
from openai import APIError

from app.core.config import Settings
from app.services.embeddings import (
    EMBEDDING_BATCH_SIZE,
    EmbeddingConfigurationError,
    EmbeddingProviderError,
    OpenAIEmbeddingProvider,
    create_openai_embedding_provider,
)

JWT_SECRET = "embedding-test-secret-longer-than-thirty-two-bytes"


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
    return OpenAIEmbeddingProvider(client, model="test-model", dimensions=3)  # type: ignore[arg-type]


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


@pytest.mark.parametrize(
    "response",
    [
        SimpleNamespace(model="wrong-model", data=[]),
        SimpleNamespace(model="test-model", data=[]),
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
            data=[SimpleNamespace(index=0, embedding=[1.0, float("nan"), 3.0])],
        ),
        SimpleNamespace(
            model="test-model",
            data=[SimpleNamespace(index=0, embedding=[0.0, 0.0, 0.0])],
        ),
    ],
)
def test_embedding_provider_rejects_incompatible_responses(response: SimpleNamespace) -> None:
    resource = FakeEmbeddingsResource()
    resource.create = lambda **kwargs: response  # type: ignore[method-assign]

    with pytest.raises(EmbeddingProviderError, match="Embedding provider request failed"):
        provider(resource).embed_texts(["text"])


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
