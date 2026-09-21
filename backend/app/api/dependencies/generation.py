from typing import Annotated

from fastapi import Depends

from app.api.dependencies.auth import ApplicationSettings
from app.services.generation import (
    GenerationProvider,
    LazyOpenAIGenerationProvider,
)


def get_generation_provider(settings: ApplicationSettings) -> GenerationProvider:
    return LazyOpenAIGenerationProvider(settings)


ConfiguredGenerationProvider = Annotated[
    GenerationProvider,
    Depends(get_generation_provider),
]
