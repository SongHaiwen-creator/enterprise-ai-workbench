from typing import Annotated

from fastapi import Depends, HTTPException

from app.api.dependencies.auth import ApplicationSettings
from app.services.embeddings import (
    EmbeddingConfigurationError,
    EmbeddingProvider,
    create_openai_embedding_provider,
)


def get_embedding_provider(settings: ApplicationSettings) -> EmbeddingProvider:
    try:
        return create_openai_embedding_provider(settings)
    except EmbeddingConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


ConfiguredEmbeddingProvider = Annotated[
    EmbeddingProvider,
    Depends(get_embedding_provider),
]


class DeferredIndexProvider:
    """Frozen-index reads need configuration identity, never an SDK/client/key."""

    def __init__(self, settings):
        self.settings = settings
        self.model = settings.embedding_model
        self.dimensions = settings.embedding_dimensions

    def embed_texts(self, texts):
        return get_embedding_provider(self.settings).embed_texts(texts)


def get_index_embedding_provider(settings: ApplicationSettings) -> EmbeddingProvider:
    return DeferredIndexProvider(settings)


ConfiguredIndexEmbeddingProvider = Annotated[
    EmbeddingProvider,
    Depends(get_index_embedding_provider),
]
