# Feature 004 - Backend Workspace Authorization

Status: Approved
Milestone: 1

## 1. Goal

Enforce authenticated, workspace-scoped authorization for the existing
Workspace and Membership APIs.

This feature answers:

"May the current user perform this operation in this workspace?"

It builds on Feature 003 authentication and the existing Membership role
and status fields. Authorization is enforced by FastAPI dependencies and
PostgreSQL-backed membership checks.

---

## 2. Scope

This feature will:

- Require authentication for all Workspace and Membership APIs.
- List the workspaces available to the current user.
- Require an active Membership for workspace access.
- Require an active `system_admin` Membership for member administration.
- Evaluate Membership role and status separately for each Workspace.
- Grant a workspace creator an active `system_admin` Membership atomically.
- Preserve the public health and login endpoints.

No new database table, column, migration, or dependency is required.

---

## 3. Roles

The existing MVP roles remain:

- `employee`
- `knowledge_admin`
- `agent_admin`
- `system_admin`

For the APIs currently available:

- All four roles may read basic information for a Workspace where they
  have an active Membership.
- Only `system_admin` may list, add, or update Workspace Memberships.
- Knowledge and Agent administration permissions will be defined when
  those resource APIs are introduced.

There is no global administrator role. A role applies only to the
Membership and Workspace where it is stored.

---

## 4. Membership and Workspace Status

Workspace access requires both:

- Workspace status is `active`.
- Current User Membership status is `active`.

An `invited` or `disabled` Membership cannot access Workspace resources.
A disabled Workspace cannot be accessed through Workspace-scoped APIs.

The existing User authentication dependency continues to reject disabled
Users before workspace authorization is evaluated.

---

## 5. Authorization Matrix

| Endpoint | Authentication | Authorization |
|---|---|---|
| `GET /health` | Public | None |
| `POST /api/auth/login` | Public | None |
| `GET /api/auth/me` | Required | Active User |
| `POST /api/workspaces` | Required | Active User |
| `GET /api/workspaces` | Required | Returns only accessible Workspaces |
| `GET /api/workspaces/{workspace_id}` | Required | Active Membership |
| `GET /api/workspaces/{workspace_id}/members` | Required | Active `system_admin` Membership |
| `POST /api/workspaces/{workspace_id}/members` | Required | Active `system_admin` Membership |
| `PATCH /api/workspaces/{workspace_id}/members/{membership_id}` | Required | Active `system_admin` Membership |

Workspace and Membership authorization is enforced on the backend.
Frontend visibility is not an authorization control.

---

## 6. Workspace Creation

When an authenticated User creates a Workspace, the backend must create
both records in one transaction:

1. The Workspace with status `active`.
2. A Membership for the creator with:
   - role `system_admin`
   - status `active`
   - `joined_at` set to the current UTC time

If Workspace or Membership persistence fails, neither record is committed.

The response remains the existing `WorkspaceResponse`.

---

## 7. List Current User Workspaces

Endpoint:

`GET /api/workspaces`

The response contains only active Workspaces where the current User has an
active Membership.

Response item:

```json
{
  "id": "workspace-uuid",
  "name": "AI Platform Department",
  "slug": "ai-platform",
  "status": "active",
  "role": "system_admin",
  "joined_at": "2026-09-14T10:00:00Z"
}
```

Fields:

- `id`
- `name`
- `slug`
- `status`
- `role`
- `joined_at`

Results are ordered by Workspace name and ID. An authenticated User with
no accessible Workspace receives an empty list.

---

## 8. Workspace Authorization Dependency

The authorization layer resolves the `workspace_id` path parameter and:

1. Loads the Workspace.
2. Returns 404 if the Workspace does not exist.
3. Returns 403 if the Workspace is disabled.
4. Loads the current User Membership for that Workspace.
5. Returns 403 if no Membership exists.
6. Returns 403 if Membership status is not `active`.
7. Returns the active Membership for subsequent role checks.

The system administrator dependency requires the resolved Membership role
to be exactly `system_admin`.

Authorization queries must always include both current `user_id` and route
`workspace_id`.

---

## 9. Error Behavior

### 401 Unauthorized

Used when authentication credentials are missing or invalid. Existing
Feature 003 behavior and `WWW-Authenticate: Bearer` are preserved.

### 403 Forbidden

Response:

```json
{
  "detail": "Not authorized for this workspace"
}
```

Used when:

- The Workspace is disabled.
- The current User has no Membership in the Workspace.
- The current Membership is invited or disabled.

Insufficient administrator role returns:

```json
{
  "detail": "System administrator role required"
}
```

### 404 Not Found

Used when the route Workspace does not exist. Existing resource-not-found
behavior remains unchanged after authorization succeeds.

A Membership ID belonging to a different Workspace continues to return
`Membership not found`.

---

## 10. Update Semantics

Authorization is evaluated using the current persisted Membership before
the requested update is applied.

A system administrator may update their own Membership. No last-admin or
self-demotion safeguard is added in this feature because no such policy is
defined for the MVP.

The updated role or status takes effect on the next request.

---

## 11. Application Structure

Request flow:

```text
HTTP Request
-> Current User dependency
-> Active Workspace Membership dependency
-> System Administrator dependency when required
-> Route
-> Service
-> SQLAlchemy
-> PostgreSQL
```

Routes declare their required dependency. Services retain persistence and
transaction responsibilities. Authorization is not implemented in the
frontend and no repository layer is introduced.

---

## 12. Acceptance Criteria

### AC-001 - Authentication Required

Workspace and Membership APIs return 401 without a valid Bearer token.

### AC-002 - Workspace Creation

An authenticated User can create a Workspace and receives an active
`system_admin` Membership in the same transaction.

### AC-003 - Accessible Workspace List

`GET /api/workspaces` returns only active Workspaces where the current User
has an active Membership, including the role for each Workspace.

### AC-004 - Active Member Access

An active member can retrieve basic information for their Workspace.

### AC-005 - Cross-Workspace Isolation

A User without a Membership in the requested Workspace receives 403.

### AC-006 - Membership Status

Invited and disabled Memberships receive 403 for Workspace resources.

### AC-007 - Member Administration

Only an active `system_admin` Membership can list, create, or update
Memberships in that Workspace.

### AC-008 - Per-Workspace Roles

A User who is `system_admin` in Workspace A and `employee` in Workspace B
may administer Workspace A but receives 403 for Workspace B administration.

### AC-009 - Disabled Workspace

An active member of a disabled Workspace receives 403.

### AC-010 - Existing Behavior

Login, current-user resolution, PostgreSQL migrations, health, CORS,
frontend lint, and frontend build continue to pass.

---

## 13. Test Requirements

PostgreSQL integration tests must cover:

- Missing and invalid token behavior.
- Atomic Workspace creation and creator Membership values.
- Accessible Workspace listing and exclusion rules.
- Active member Workspace access.
- Non-member cross-Workspace access.
- Invited and disabled Membership access.
- Disabled Workspace access.
- Employee, Knowledge Admin, and Agent Admin denial for member management.
- System Admin member list, add, and update success.
- Different roles for the same User in different Workspaces.
- Membership IDs scoped to the route Workspace.
- Existing authentication, migration, and API regressions.

SQLite must not replace PostgreSQL tests.

---

## 14. Out of Scope

- Custom roles or permissions.
- Global administrator role.
- Fine-grained permission editor.
- Last-system-administrator safeguards.
- Invitation acceptance or email.
- Public user registration.
- Refresh tokens, password reset, MFA, OAuth, or SSO.
- Frontend Workspace management UI.
- Knowledge Base, Document, RAG, Agent, Tool, Workflow, or AI functionality.
