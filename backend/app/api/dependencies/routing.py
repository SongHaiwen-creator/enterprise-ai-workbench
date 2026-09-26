from typing import Annotated

from fastapi import Depends

from app.api.dependencies.auth import ApplicationSettings
from app.services.routing import LazyOpenAIRoutingProvider, RoutingProvider


def get_routing_provider(settings: ApplicationSettings) -> RoutingProvider:
    return LazyOpenAIRoutingProvider(settings)


ConfiguredRoutingProvider = Annotated[RoutingProvider, Depends(get_routing_provider)]
