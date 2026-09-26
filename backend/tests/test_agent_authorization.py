import pytest

from app.api.dependencies.authorization import (
    AGENT_ADMIN_REQUIRED,
    require_agent_administrator,
)
from app.models import Membership
from app.models.enums import MembershipRole
from app.services.exceptions import ForbiddenError


@pytest.mark.parametrize(
    "role",
    [MembershipRole.AGENT_ADMIN, MembershipRole.SYSTEM_ADMIN],
)
def test_agent_administrator_dependency_allows_management_roles(role: MembershipRole) -> None:
    membership = Membership(role=role)
    assert require_agent_administrator(membership) is membership


@pytest.mark.parametrize(
    "role",
    [MembershipRole.EMPLOYEE, MembershipRole.KNOWLEDGE_ADMIN],
)
def test_agent_administrator_dependency_denies_other_roles(role: MembershipRole) -> None:
    with pytest.raises(ForbiddenError, match=AGENT_ADMIN_REQUIRED):
        require_agent_administrator(Membership(role=role))
