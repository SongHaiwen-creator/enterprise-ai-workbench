from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.enums import AgentStatus
from app.schemas.agent import (
    AgentConfigurationResponse,
    AgentCreate,
    AgentSummaryResponse,
    AgentUpdate,
)


def test_agent_create_trims_text_and_keeps_status_server_owned() -> None:
    payload = AgentCreate(
        name="  Assistant  ", description="  Service  ", system_prompt="  Scope  "
    )
    assert payload.name == "Assistant"
    assert payload.description == "Service"
    assert payload.system_prompt == "Scope"
    assert "status" not in payload.model_dump()


@pytest.mark.parametrize(
    "payload",
    [
        {"name": " ", "system_prompt": "Valid"},
        {"name": "Valid", "system_prompt": " "},
        {"name": "x" * 256, "system_prompt": "Valid"},
        {"name": "Valid", "system_prompt": "x" * 8001},
        {"name": "Valid", "system_prompt": "Valid", "description": "x" * 5001},
        {"name": "Valid", "system_prompt": "Valid", "status": "active"},
        {"name": "Valid", "system_prompt": "Valid", "unknown": True},
    ],
)
def test_agent_create_rejects_invalid_payloads(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        AgentCreate.model_validate(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"name": None},
        {"name": " "},
        {"system_prompt": None},
        {"system_prompt": " "},
        {"status": None},
        {"status": "unknown"},
        {"unknown": True},
    ],
)
def test_agent_update_rejects_invalid_payloads(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        AgentUpdate.model_validate(payload)


def test_agent_update_can_clear_description() -> None:
    payload = AgentUpdate.model_validate({"description": None})
    assert payload.model_dump(exclude_unset=True) == {"description": None}


def test_agent_summary_does_not_expose_system_prompt() -> None:
    now = datetime.now(UTC)
    agent = SimpleNamespace(
        id=uuid4(),
        workspace_id=uuid4(),
        name="Assistant",
        description=None,
        system_prompt="Private routing configuration",
        status=AgentStatus.ACTIVE,
        created_by=uuid4(),
        created_at=now,
        updated_at=now,
    )
    summary = AgentSummaryResponse.model_validate(agent)
    configuration = AgentConfigurationResponse.model_validate(agent)

    assert set(summary.model_dump()) == {
        "id",
        "workspace_id",
        "name",
        "description",
        "status",
        "created_by",
        "created_at",
        "updated_at",
    }
    assert configuration.system_prompt == agent.system_prompt
