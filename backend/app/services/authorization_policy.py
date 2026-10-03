"""Shared predicates over inert facts. These functions never grant runtime identity."""

from app.services.exceptions import NotFoundError

POLICY_VERSION = "workspace-policy-v1"
ADMIN_ROLES = frozenset({"agent_admin", "system_admin"})


def active_membership(status: str | None) -> bool:
    return status == "active"


def agent_administrator(role: str) -> bool:
    return role in ADMIN_ROLES


def require_scoped_resource(present: bool, detail: str) -> None:
    if not present:
        raise NotFoundError(detail)


def permission_observation(
    *, role: str, membership_status: str, operation: str, present: bool, active: bool
) -> dict:
    if not active_membership(membership_status) or (
        operation.endswith("_read") and not agent_administrator(role)
    ):
        status, category = 403, "forbidden"
    elif not present:
        status, category = 404, "not_found"
    elif operation in {"agent_route", "knowledge_answer"} and not active:
        status, category = 409, "conflict"
    else:
        status, category = 200, "allowed"
    return {"http_status": status, "result_category": category, "access_denied": status != 200}
