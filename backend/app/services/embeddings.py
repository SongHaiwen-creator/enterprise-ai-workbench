from collections.abc import Sequence
from math import isfinite
from numbers import Real
from typing import Protocol

import tiktoken
from openai import APIError, OpenAI

from app.core.config import Settings

EMBEDDING_BATCH_SIZE = 256
EMBEDDING_MAX_INPUT_TOKENS = 8_192
EMBEDDING_REQUEST_TOKEN_BUDGET = 290_000
EMBEDDING_PROVIDER_FAILURE = "Embedding provider request failed"


class EmbeddingConfigurationError(Exception):
    """Embedding service configuration is absent."""


class EmbeddingProviderError(Exception):
    """The provider failed or returned an incompatible response."""


class EmbeddingProvider(Protocol):
    model: str
    dimensions: int

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]: ...


class TokenEncoding(Protocol):
    def encode(
        self,
        text: str,
        *,
        disallowed_special: object = ...,
    ) -> list[int]: ...


def normalize_embedding(vector: object, dimensions: int) -> list[float] | None:
    if (
        not isinstance(vector, Sequence)
        or isinstance(vector, (str, bytes, bytearray))
        or len(vector) != dimensions
    ):
        return None

    normalized: list[float] = []
    for value in vector:
        if isinstance(value, bool) or not isinstance(value, Real):
            return None
        try:
            normalized_value = float(value)
        except (OverflowError, TypeError, ValueError):
            return None
        if not isfinite(normalized_value):
            return None
        normalized.append(normalized_value)
    if not any(value != 0.0 for value in normalized):
        return None
    return normalized


class OpenAIEmbeddingProvider:
    def __init__(
        self,
        client: OpenAI,
        *,
        model: str,
        dimensions: int,
        encoding: TokenEncoding | None = None,
    ) -> None:
        self.client = client
        self.model = model
        self.dimensions = dimensions
        if encoding is not None:
            self.encoding = encoding
        else:
            try:
                self.encoding = tiktoken.encoding_for_model(model)
            except (KeyError, OSError, ValueError) as exc:
                raise EmbeddingConfigurationError(
                    "Embedding tokenizer is not configured"
                ) from exc

    def _batches(self, texts: Sequence[str]) -> list[list[str]]:
        batches: list[list[str]] = []
        batch: list[str] = []
        batch_tokens = 0

        for text in texts:
            if not isinstance(text, str) or not text:
                raise EmbeddingProviderError(EMBEDDING_PROVIDER_FAILURE)
            try:
                token_count = len(self.encoding.encode(text, disallowed_special=()))
            except (TypeError, UnicodeError, ValueError) as exc:
                raise EmbeddingProviderError(EMBEDDING_PROVIDER_FAILURE) from exc
            if token_count == 0 or token_count > EMBEDDING_MAX_INPUT_TOKENS:
                raise EmbeddingProviderError(EMBEDDING_PROVIDER_FAILURE)

            if batch and (
                len(batch) >= EMBEDDING_BATCH_SIZE
                or batch_tokens + token_count > EMBEDDING_REQUEST_TOKEN_BUDGET
            ):
                batches.append(batch)
                batch = []
                batch_tokens = 0
            batch.append(text)
            batch_tokens += token_count

        if batch:
            batches.append(batch)
        return batches

    def _validated_response(self, response: object, batch_size: int) -> list[list[float]]:
        try:
            response_model = response.model  # type: ignore[attr-defined]
            response_data = response.data  # type: ignore[attr-defined]
        except (AttributeError, TypeError, ValueError) as exc:
            raise EmbeddingProviderError(EMBEDDING_PROVIDER_FAILURE) from exc

        if (
            not isinstance(response_model, str)
            or response_model != self.model
            or not isinstance(response_data, list)
        ):
            raise EmbeddingProviderError(EMBEDDING_PROVIDER_FAILURE)
        if len(response_data) != batch_size:
            raise EmbeddingProviderError(EMBEDDING_PROVIDER_FAILURE)

        indexed: dict[int, list[float]] = {}
        for item in response_data:
            try:
                index = item.index
                vector = item.embedding
            except (AttributeError, TypeError, ValueError) as exc:
                raise EmbeddingProviderError(EMBEDDING_PROVIDER_FAILURE) from exc
            if (
                isinstance(index, bool)
                or not isinstance(index, int)
                or index < 0
                or index >= batch_size
                or index in indexed
            ):
                raise EmbeddingProviderError(EMBEDDING_PROVIDER_FAILURE)
            normalized = normalize_embedding(vector, self.dimensions)
            if normalized is None:
                raise EmbeddingProviderError(EMBEDDING_PROVIDER_FAILURE)
            indexed[index] = normalized

        return [indexed[index] for index in range(batch_size)]

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []

        embeddings: list[list[float]] = []
        for batch in self._batches(texts):
            try:
                response = self.client.embeddings.create(
                    input=batch,
                    model=self.model,
                    dimensions=self.dimensions,
                    encoding_format="float",
                )
            except (APIError, AttributeError, TypeError, ValueError) as exc:
                raise EmbeddingProviderError(EMBEDDING_PROVIDER_FAILURE) from exc
            embeddings.extend(self._validated_response(response, len(batch)))

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
