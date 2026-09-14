# Feature 001 - Workspace & RBAC

Status: Draft
Milestone: 1

## 1. Goal

Build the basic enterprise workspace and permission foundation.

The system should support:

- Users
- Workspaces
- Workspace membership
- Different roles in different workspaces
- Backend permission checks
- Workspace-level data isolation

This milestone does not include AI capabilities.

---

## 2. User Roles

### Employee

Can:

- Enter workspaces they belong to
- View basic workspace information
- Use employee-facing features

Cannot:

- Manage workspace members
- Change user roles
- Access system administration APIs

### Knowledge Admin

Can:

- Use employee capabilities
- Manage enterprise knowledge in later milestones

### Agent Admin

Can:

- Use employee capabilities
- Manage agents and tools in later milestones

### System Admin

Can:

- View workspace members
- Add members
- Change member roles
- Disable memberships

---

## 3. Core Entities

### User

Represents one platform user.

### Workspace

Represents one enterprise workspace.

### Membership

Connects a User and a Workspace.

Membership stores:

- user_id
- workspace_id
- role
- status

The same user may have different roles in different workspaces.

Example:

User A

Workspace 1 → employee

Workspace 2 → system_admin

---

## 4. Core User Stories

### US-001

As a user,
I want to log in,
so that the system can identify who I am.

### US-002

As a user,
I want to view the workspaces I belong to,
so that I can enter the correct enterprise workspace.

### US-003

As a system administrator,
I want to view workspace members,
so that I can manage enterprise access.

### US-004

As a system administrator,
I want to assign roles to workspace members,
so that users receive appropriate permissions.

### US-005

As an employee,
I should not be able to access administrator APIs,
so that enterprise management functions remain protected.

---

## 5. Core Business Rules

### BR-001

A user may belong to multiple workspaces.

### BR-002

A user has one role per workspace in the MVP.

### BR-003

A user can only access workspace resources
if an active Membership exists.

### BR-004

The backend must verify permissions.

Frontend visibility alone is not authorization.

### BR-005

Workspace A users must never access Workspace B data
without a valid Membership.

### BR-006

Disabled memberships cannot access workspace resources.

---

## 6. MVP Roles

Supported roles:

- employee
- knowledge_admin
- agent_admin
- system_admin

Custom roles are out of scope for this milestone.

---

## 7. MVP APIs

Planned API examples:

GET /api/workspaces

GET /api/workspaces/{workspace_id}

GET /api/workspaces/{workspace_id}/members

POST /api/workspaces/{workspace_id}/members

PATCH /api/workspaces/{workspace_id}/members/{membership_id}

---

## 8. Acceptance Criteria

### AC-001

Given:

User A belongs to Workspace A.

When:

User A requests Workspace A.

Then:

The request succeeds.

---

### AC-002

Given:

User A does not belong to Workspace B.

When:

User A requests Workspace B.

Then:

The backend returns 403 Forbidden.

---

### AC-003

Given:

User A is an employee.

When:

User A requests the workspace member administration API.

Then:

The backend returns 403 Forbidden.

---

### AC-004

Given:

User A is system_admin in Workspace A
and employee in Workspace B.

When:

User A accesses member administration.

Then:

Workspace A succeeds.

Workspace B returns 403 Forbidden.

---

### AC-005

Given:

User A has a disabled Membership.

When:

User A requests workspace resources.

Then:

The backend returns 403 Forbidden.

---

## 9. Out of Scope

This milestone does not include:

- Knowledge base
- RAG
- Agent
- Tool calling
- Custom role builder
- Enterprise SSO
- Fine-grained permission editor
- Department hierarchy