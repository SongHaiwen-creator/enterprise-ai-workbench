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
