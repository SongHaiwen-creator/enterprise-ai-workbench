from typing import Annotated

from fastapi import Depends

from app.api.dependencies.auth import ApplicationSettings
from app.services.tool_selection import LazyOpenAIToolSelector, ToolSelector


def get_tool_selector(settings: ApplicationSettings) -> ToolSelector:
    return LazyOpenAIToolSelector(settings)


ConfiguredToolSelector = Annotated[ToolSelector, Depends(get_tool_selector)]
