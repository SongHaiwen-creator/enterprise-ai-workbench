# Feature 002 - Workspace & Membership API

Status: Draft  
Milestone: 1

## 1. Goal

Expose the existing Workspace and Membership persistence models
through a small FastAPI business API.

This feature should allow the system to:

- Create a workspace
- Retrieve a workspace
- List workspace members
- Add an existing user to a workspace
- Update membership role and status

This feature focuses on API contract and database interaction.

Authentication and RBAC authorization are intentionally out of scope
and will be implemented in later issues.

---

## 2. Existing Data Models

This feature uses the existing persistence models:

- User
- Workspace
- Membership

Relationship:

User
↓
Membership
↓
Workspace

A User may belong to multiple Workspaces.

A User may have a different role in each Workspace.

---

## 3. API Endpoints

### 3.1 Create Workspace

Endpoint:

POST /api/workspaces

Request:

```json
{
  "name": "AI Platform Department",
  "slug": "ai-platform"
}

Success:

HTTP 201 Created

Response:

{
  "id": "workspace-uuid",
  "name": "AI Platform Department",
  "slug": "ai-platform",
  "status": "active",
  "created_at": "2026-09-14T10:00:00Z",
  "updated_at": "2026-09-14T10:00:00Z"
}

Business Rules:

name is required.
slug is required.
slug is normalized to lowercase.
slug must be unique.
Workspace status defaults to active.

Errors:

409 Conflict: workspace slug already exists.
422 Unprocessable Entity: invalid request data.
3.2 Get Workspace

Endpoint:

GET /api/workspaces/{workspace_id}

Success:

HTTP 200 OK

Response:

{
  "id": "workspace-uuid",
  "name": "AI Platform Department",
  "slug": "ai-platform",
  "status": "active",
  "created_at": "2026-09-14T10:00:00Z",
  "updated_at": "2026-09-14T10:00:00Z"
}

Errors:

404 Not Found: workspace does not exist.
3.3 List Workspace Members

Endpoint:

GET /api/workspaces/{workspace_id}/members

Success:

HTTP 200 OK

Response:

[
  {
    "id": "membership-uuid",
    "user_id": "user-uuid",
    "email": "alice@company.com",
    "name": "Alice",
    "role": "employee",
    "status": "active",
    "joined_at": "2026-09-14T10:00:00Z"
  }
]

Business Rules:

Workspace must exist.
Response should include useful User information.
Membership and User data should be joined by the backend.

Errors:

404 Not Found: workspace does not exist.
3.4 Add Workspace Member

Endpoint:

POST /api/workspaces/{workspace_id}/members

Request:

{
  "user_id": "user-uuid",
  "role": "employee"
}

Success:

HTTP 201 Created

Response:

{
  "id": "membership-uuid",
  "user_id": "user-uuid",
  "workspace_id": "workspace-uuid",
  "role": "employee",
  "status": "invited",
  "joined_at": null
}

Business Rules:

Workspace must exist.
User must already exist.
A User can only have one Membership in the same Workspace.
Default Membership status is invited.
Role must be one of the supported roles.

Supported roles:

employee
knowledge_admin
agent_admin
system_admin

Errors:

404 Not Found: workspace does not exist.
404 Not Found: user does not exist.
409 Conflict: membership already exists.
422 Unprocessable Entity: invalid role or request data.
3.5 Update Workspace Membership

Endpoint:

PATCH /api/workspaces/{workspace_id}/members/{membership_id}

Request example:

{
  "role": "knowledge_admin",
  "status": "active"
}

The request may contain only one field:

{
  "role": "agent_admin"
}

or:

{
  "status": "disabled"
}

Success:

HTTP 200 OK

Response:

{
  "id": "membership-uuid",
  "user_id": "user-uuid",
  "workspace_id": "workspace-uuid",
  "role": "knowledge_admin",
  "status": "active",
  "joined_at": "2026-09-14T11:00:00Z"
}

Supported statuses:

invited
active
disabled

Business Rules:

Workspace must exist.
Membership must exist.
Membership must belong to the specified Workspace.
Role must be valid.
Status must be valid.
When an invited membership becomes active,
joined_at may be populated if it is currently null.

Errors:

404 Not Found: workspace does not exist.
404 Not Found: membership does not exist.
422 Unprocessable Entity: invalid role/status.
4. Request Schemas
WorkspaceCreate

Fields:

name: string
slug: string

Validation:

name cannot be empty.
slug cannot be empty.
slug is normalized to lowercase.
slug should only contain URL-safe characters.

Example:

{
  "name": "Finance Department",
  "slug": "finance-department"
}
MembershipCreate

Fields:

user_id: UUID
role: role enum

Default:

role = employee
MembershipUpdate

Optional fields:

role
status

At least one field must be provided.

5. Response Schemas
WorkspaceResponse

Fields:

id
name
slug
status
created_at
updated_at
MembershipResponse

Fields:

id
user_id
workspace_id
role
status
joined_at
WorkspaceMemberResponse

Used for member-list UI.

Fields:

id
user_id
email
name
role
status
joined_at

This response combines Membership and User information.

6. Error Strategy

Expected business errors should be translated into explicit HTTP responses.

404 Not Found

Use when:

Workspace does not exist.
User does not exist.
Membership does not exist.
409 Conflict

Use when:

Workspace slug already exists.
User is already a member of the Workspace.

Database IntegrityError must not be exposed directly as HTTP 500
for expected uniqueness conflicts.

422 Unprocessable Entity

Use when:

UUID format is invalid.
Role is invalid.
Membership status is invalid.
Required fields are missing.
Request schema validation fails.

Unexpected server errors may return HTTP 500.

Internal database error details must not be exposed to the client.

7. Business Rules
BR-001

Workspace slug must be unique.

BR-002

Workspace slug is normalized to lowercase before persistence.

BR-003

Membership creation requires an existing Workspace.

BR-004

Membership creation requires an existing User.

BR-005

A User can only have one Membership per Workspace.

BR-006

Membership role must be one of:

employee
knowledge_admin
agent_admin
system_admin
BR-007

Membership status must be one of:

invited
active
disabled
BR-008

A Membership retrieved or modified under a Workspace route
must belong to that Workspace.

8. Application Layers

The implementation should separate responsibilities:

HTTP Request
↓
FastAPI Route
↓
Service Layer
↓
SQLAlchemy
↓
PostgreSQL
↓
Response Schema

Route Layer

Responsibilities:

Receive HTTP requests
Validate request schemas
Call service functions
Return HTTP responses

Routes should not contain large amounts of business logic.

Service Layer

Responsibilities:

Workspace creation logic
Membership creation logic
Existence checks
Conflict handling
Business-rule enforcement
Database Layer

Responsibilities:

SQLAlchemy queries
Transactions
Database constraints

Do not introduce a separate Repository layer in this feature.

9. Acceptance Criteria
AC-001

Given:

A valid workspace request.

When:

POST /api/workspaces is called.

Then:

HTTP 201 is returned.
Workspace is persisted in PostgreSQL.
AC-002

Given:

A Workspace with slug ai-platform already exists.

When:

Another Workspace with the same slug is created.

Then:

HTTP 409 Conflict is returned.

AC-003

Given:

A Workspace exists.

When:

GET /api/workspaces/{workspace_id} is called.

Then:

HTTP 200 is returned with Workspace information.

AC-004

Given:

A Workspace does not exist.

When:

GET /api/workspaces/{workspace_id} is called.

Then:

HTTP 404 is returned.

AC-005

Given:

A valid User and Workspace exist.

When:

POST /api/workspaces/{workspace_id}/members is called.

Then:

A Membership is created.

Default status is invited.

AC-006

Given:

A User is already a member of a Workspace.

When:

The same Membership is created again.

Then:

HTTP 409 Conflict is returned.

AC-007

Given:

The requested User does not exist.

When:

Membership creation is attempted.

Then:

HTTP 404 is returned.

AC-008

Given:

A Workspace contains multiple Members.

When:

GET /api/workspaces/{workspace_id}/members is called.

Then:

The response includes:

user_id
email
name
role
status
joined_at
AC-009

Given:

A Membership exists.

When:

PATCH is used to change role or status.

Then:

The Membership is updated and persisted.

AC-010

Existing behavior must continue to work:

GET /health
PostgreSQL migrations
existing database integration tests
Ruff
frontend lint
frontend build
10. Testing Requirements

API tests must use the PostgreSQL test database.

Test at minimum:

Create Workspace successfully
Retrieve Workspace successfully
Workspace not found
Duplicate Workspace slug
Add Membership successfully
Unknown User
Unknown Workspace
Duplicate Membership
List Workspace Members
Update Membership role
Update Membership status
Invalid role/status
Membership belongs to requested Workspace
Existing /health still works

SQLite must not be used as a substitute for PostgreSQL.

11. Security Note

These APIs are temporarily unauthenticated.

This is intentional for the current development stage.

They are NOT production-ready until Authentication and RBAC
are implemented in later issues.

The temporary absence of authentication must not be interpreted
as a final product design.

12. Out of Scope

This feature does NOT implement:

User registration API
Login
Password authentication
JWT
Current-user context
RBAC authorization
Permission middleware
Invitation email
Custom roles
Department hierarchy
Knowledge Base
RAG
Agent
Tool Calling
AI functionality