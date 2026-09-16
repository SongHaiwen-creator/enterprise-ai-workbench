from collections.abc import Sequence
from math import isfinite
from typing import Protocol

from openai import APIError, OpenAI

from app.core.config import Settings

EMBEDDING_BATCH_SIZE = 256
EMBEDDING_PROVIDER_FAILURE = "Embedding provider request failed"


class EmbeddingConfigurationError(Exception):
    """Embedding service configuration is absent."""


class EmbeddingProviderError(Exception):
    """The provider failed or returned an incompatible response."""


class EmbeddingProvider(Protocol):
    model: str
    dimensions: int

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]: ...


def is_valid_embedding(vector: Sequence[float], dimensions: int) -> bool:
    return (
        len(vector) == dimensions
        and all(isfinite(value) for value in vector)
        and any(value != 0.0 for value in vector)
    )


class OpenAIEmbeddingProvider:
    def __init__(
        self,
        client: OpenAI,
        *,
        model: str,
        dimensions: int,
    ) -> None:
        self.client = client
        self.model = model
        self.dimensions = dimensions

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []

        embeddings: list[list[float]] = []
        for start in range(0, len(texts), EMBEDDING_BATCH_SIZE):
            batch = list(texts[start : start + EMBEDDING_BATCH_SIZE])
            try:
                response = self.client.embeddings.create(
                    input=batch,
                    model=self.model,
                    dimensions=self.dimensions,
                    encoding_format="float",
                )
            except APIError as exc:
                raise EmbeddingProviderError(EMBEDDING_PROVIDER_FAILURE) from exc

            if response.model != self.model:
                raise EmbeddingProviderError(EMBEDDING_PROVIDER_FAILURE)

            indexed = {item.index: item.embedding for item in response.data}
            if len(response.data) != len(batch) or set(indexed) != set(range(len(batch))):
                raise EmbeddingProviderError(EMBEDDING_PROVIDER_FAILURE)

            ordered = [indexed[index] for index in range(len(batch))]
            if any(not is_valid_embedding(vector, self.dimensions) for vector in ordered):
                raise EmbeddingProviderError(EMBEDDING_PROVIDER_FAILURE)
            embeddings.extend(ordered)

        return embeddings


def create_openai_embedding_provider(settings: Settings) -> OpenAIEmbeddingProvider:
    if settings.openai_api_key is None:
        raise EmbeddingConfigurationError("Embedding provider is not configured")

    client = OpenAI(
        api_key=settings.openai_api_key.get_secret_value(),
        timeout=settings.openai_timeout_seconds,
        max_retries=0,
    )
    return OpenAIEmbeddingProvider(
        client,
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
    )
