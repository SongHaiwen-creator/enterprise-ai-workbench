# Feature 005 - Workspace Management Interface

Status: Approved
Milestone: 1

## 1. Goal

Provide the first usable browser interface for the existing authentication,
Workspace, and Membership APIs so an authenticated user can enter an authorized
Workspace and a Workspace system administrator can manage its members.

## 2. Scope

This feature will:

- Replace the application-foundation placeholder with a login experience.
- Resolve and display the authenticated user's profile.
- List only Workspaces returned by the authorized Workspace API.
- Let the user select a Workspace and view its basic information.
- Show member-management controls only for a selected Workspace where the
  current Membership role is `system_admin`.
- Let a system administrator list members, add an existing User by UUID, and
  update a member's role or status.
- Provide loading, empty, success, validation, authorization, and request-error
  states.
- Keep the access token in browser memory only and clear it on sign out or an
  authentication failure.

The feature consumes existing backend contracts and does not change backend
authorization behavior.

## 3. Business Rules

- Authentication uses `POST /api/auth/login` and Bearer access tokens.
- The browser must not persist the access token in local storage, session
  storage, cookies, or source-controlled configuration.
- `GET /api/auth/me` supplies the displayed user identity.
- `GET /api/workspaces` is the source of truth for accessible Workspaces and the
  current user's role in each Workspace.
- A user can select only a Workspace returned by that endpoint.
- Member-management UI is available only when the selected Workspace list item
  has role `system_admin`.
- Frontend role checks control presentation only. The backend remains the
  authorization boundary and all API errors must be handled.
- Adding a member uses an existing User UUID because user search, invitation
  delivery, and public registration are not available in Milestone 1.
- Roles are limited to `employee`, `knowledge_admin`, `agent_admin`, and
  `system_admin`.
- Membership statuses are limited to `invited`, `active`, and `disabled`.

## 4. API / Data Contract

The frontend will use the existing API without contract changes:

- `POST /api/auth/login`
- `GET /api/auth/me`
- `GET /api/workspaces`
- `GET /api/workspaces/{workspace_id}`
- `GET /api/workspaces/{workspace_id}/members`
- `POST /api/workspaces/{workspace_id}/members`
- `PATCH /api/workspaces/{workspace_id}/members/{membership_id}`

All requests except login include:

```text
Authorization: Bearer <access_token>
```

Expected error payloads use the existing FastAPI shape:

```json
{
  "detail": "Human-readable error"
}
```

The frontend API helper must tolerate an unavailable backend and non-JSON error
responses without exposing implementation details to the user.

## 5. User Experience

### Login

- Email and password fields are required.
- The submit button exposes an in-progress state and prevents duplicate submits.
- Invalid credentials and unavailable-service failures are announced in the
  form.

### Workspace Selection

- After login, the header displays the current user's name and email.
- Accessible Workspaces are displayed as a selectable list with role labels.
- The first Workspace is selected by default.
- A user with no accessible Workspace sees an explicit empty state.
- The selected Workspace's name, slug, and status are visible.

### Member Management

- A `system_admin` sees the member roster, an add-member form, and role/status
  controls.
- Other roles see a clear read-only message and no administrative controls.
- Member mutations refresh the roster and display success or error feedback.
- Forms and controls have associated labels and keyboard-visible focus styles.
- The layout remains usable on narrow and wide screens.

## 6. Acceptance Criteria

### AC-001 - Login

An active user can submit valid credentials and reach the Workspace interface.
Invalid credentials remain on the login screen with an accessible error.

### AC-002 - User Identity

After authentication, the interface resolves and displays the current user's
name and email.

### AC-003 - Workspace List and Selection

The interface renders only Workspaces returned by `GET /api/workspaces`, selects
the first result by default, and lets the user switch between returned
Workspaces.

### AC-004 - Empty Workspace State

An authenticated user with no accessible Workspaces sees an explicit empty
state and does not see member-management controls.

### AC-005 - Role-Aware Member Management

For a selected Workspace with role `system_admin`, the interface loads and
displays members and supports adding a User UUID and updating role or status.

### AC-006 - Non-Administrator Experience

For a selected Workspace with any other role, administrative controls are not
rendered and the UI explains that member management requires a system
administrator.

### AC-007 - Authentication Failure

If an authenticated API request returns 401, the in-memory session is cleared
and the login experience is shown with an expiry message.

### AC-008 - Quality Gates

- Feature-specific frontend tests pass.
- Frontend lint passes.
- Frontend production build passes.
- Existing backend pytest and Ruff verification pass against PostgreSQL where
  required by the repository workflow.

## 7. Test Requirements

Feature tests must cover at minimum:

- API base URL normalization.
- Successful JSON request handling and Bearer header behavior.
- FastAPI error-detail parsing.
- Network and non-JSON failure normalization.
- Role and status label formatting used by the interface.

Manual/self-review must also confirm the login, empty, administrator,
non-administrator, loading, and error render paths in the component code.

## 8. Out of Scope

- Public registration, password reset, refresh tokens, MFA, OAuth, and SSO.
- Persisted browser sessions or server-managed authentication cookies.
- Changing authentication, RBAC, or Workspace isolation policy.
- Creating, disabling, or editing Workspaces.
- User directory search or user provisioning.
- Invitation email and invitation acceptance.
- Removing members or last-administrator safeguards.
- Knowledge Base, RAG, Agent, Tool, Workflow, or AI functionality.
- New backend APIs, database changes, or migrations.
