# Enterprise AI Workbench - Database Design

Version: 0.1

## 1. Design Goals

The database should support:

- Multiple enterprise workspaces
- Workspace-level data isolation
- Role-based access control
- Enterprise knowledge management
- Agent and tool configuration
- Human approval workflows
- AI conversation and execution logging
- AI evaluation and bad case management

The MVP uses PostgreSQL.

Vector data will later be stored using pgvector.

---

# 2. Core Entity Relationships

High-level relationships:

User
↓
Membership
↓
Workspace

Workspace
├── KnowledgeBase
├── Agent
├── Tool
├── Workflow
├── Approval
├── Conversation
├── ExecutionLog
└── EvaluationCase

KnowledgeBase
↓
Document
↓
Chunk

---

# 3. Workspace

Represents one enterprise or isolated business workspace.

Table: workspaces

Fields:

| Field | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| name | VARCHAR | Workspace name |
| slug | VARCHAR | Unique workspace identifier |
| status | VARCHAR | active / disabled |
| created_at | TIMESTAMP | Creation time |
| updated_at | TIMESTAMP | Last update time |

Example:

- Beijing Demo Company
- Finance Department Demo Workspace

---

# 4. User

Represents a platform user.

Table: users

Fields:

| Field | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| email | VARCHAR | Unique email |
| name | VARCHAR | Display name |
| status | VARCHAR | active / disabled |
| created_at | TIMESTAMP | Creation time |
| updated_at | TIMESTAMP | Last update time |

A user does not directly store a workspace role.

Workspace membership and role are stored in Membership.

---

# 5. Membership

Connects users and workspaces.

Table: memberships

Fields:

| Field | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| user_id | UUID | Foreign key → users.id |
| workspace_id | UUID | Foreign key → workspaces.id |
| role | VARCHAR | User role inside the workspace |
| status | VARCHAR | active / invited / disabled |
| joined_at | TIMESTAMP | Join time |

Supported MVP roles:

- employee
- knowledge_admin
- agent_admin
- system_admin

Constraint:

A user should only have one active membership record
for the same workspace.

Unique:

(user_id, workspace_id)

---

# 6. Knowledge Base

Represents a collection of enterprise knowledge.

Table: knowledge_bases

Fields:

| Field | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| workspace_id | UUID | Foreign key → workspaces.id |
| name | VARCHAR | Knowledge base name |
| description | TEXT | Description |
| status | VARCHAR | active / disabled |
| created_by | UUID | Foreign key → users.id |
| created_at | TIMESTAMP | Creation time |
| updated_at | TIMESTAMP | Last update time |

A knowledge base belongs to exactly one workspace.

---

# 7. Document

Represents a document uploaded into a knowledge base.

Table: documents

Fields:

| Field | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| workspace_id | UUID | Foreign key → workspaces.id |
| knowledge_base_id | UUID | Foreign key → knowledge_bases.id |
| file_name | VARCHAR | Original file name |
| file_type | VARCHAR | pdf / txt / md |
| status | VARCHAR | uploaded / processing / ready / failed / disabled |
| version | INTEGER | Document version |
| extracted_text | TEXT | Normalized text retained for later chunking; not exposed by the Document API |
| processing_error | VARCHAR | Sanitized processing failure summary |
| created_by | UUID | Foreign key → users.id |
| created_at | TIMESTAMP | Creation time |
| updated_at | TIMESTAMP | Last update time |

The MVP only supports text-extractable documents.

The Document Management API accepts PDF, TXT and Markdown uploads up to
10 MiB. It retains normalized extracted text in PostgreSQL but does not retain
the original uploaded binary. New documents start at version 1; replacement
and automatic version management are deferred until a stable document-family
model is defined.

Feature 008 migration `0006` adds a composite foreign key from
`documents(knowledge_base_id, workspace_id)` to
`knowledge_bases(id, workspace_id)`. A Document therefore cannot reference a
Knowledge Base owned by another Workspace. Existing single-column foreign keys
remain in place.

---

# 8. Chunk

Represents one retrievable unit from a document.

Table: chunks

Fields:

| Field | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| workspace_id | UUID | Foreign key → workspaces.id |
| document_id | UUID | Foreign key → documents.id |
| content | TEXT | Chunk text |
| chunk_index | INTEGER | Order inside document |
| embedding_model | VARCHAR | Embedding model used for the vector |
| embedding | VECTOR(1536) | Vector representation |
| created_at | TIMESTAMP | Creation time |

Chunks are used for RAG retrieval.

Feature 008 uses `text-embedding-3-small` with 1,536 dimensions and exact
cosine-distance search. Chunks are created or atomically replaced only through
the workspace-scoped Document indexing operation. Retrieval joins each Chunk
through its Document and filters the target Workspace, Knowledge Base, and
ready Document status before ranking. Approximate vector indexes are deferred.
A composite foreign key enforces that each Chunk's `workspace_id` matches its
parent Document's Workspace.

---

# 9. Agent

Represents an AI agent configuration.

Table: agents

Fields:

| Field | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| workspace_id | UUID | Foreign key → workspaces.id |
| name | VARCHAR | Agent name |
| description | TEXT | Agent purpose |
| system_prompt | TEXT | System prompt |
| status | VARCHAR | draft / active / disabled |
| created_by | UUID | Foreign key → users.id |
| created_at | TIMESTAMP | Creation time |
| updated_at | TIMESTAMP | Last update time |

Example agents:

- Employee Service Assistant
- IT Support Assistant
- Policy Q&A Assistant

Feature 011 Alembic revision `0007` creates this table with a database-generated
UUID primary key; non-null Workspace and creator foreign keys using
`ON DELETE RESTRICT`; required trimmed non-empty name and system prompt; nullable
description; status restricted to `draft`, `active`, or `disabled` with a `draft`
default; non-null timezone-aware creation and update timestamps; and indexes on
`workspace_id` and `created_by`. The service updates `updated_at` when an Agent
changes. Agent names are not unique. No Agent-to-Knowledge-Base relation is
persisted: the optional Knowledge Base ID is supplied per request and resolved
only for a knowledge question.

Feature 012 Alembic revision `0008` adds unique `(id, workspace_id)` on
`agents` so Agent-to-Tool assignments can enforce same-Workspace ownership
with a composite foreign key.

---

# 10. Tool

Represents a Workspace configuration for one application-registered enterprise
capability. Persistence enables and names a known capability; it never stores
executable code, URLs, credentials, request schemas, or provider instructions.

Table: tools

Fields:

| Field | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| workspace_id | UUID | Foreign key → workspaces.id |
| tool_key | VARCHAR(64) | Stable application-registry key |
| name | VARCHAR(255) | Workspace display name |
| description | TEXT | Administrative description; never sent to the selector |
| risk_level | VARCHAR(16) | low / medium / high; must match the registry |
| status | VARCHAR | active / disabled |
| created_by | UUID | Foreign key → users.id |
| created_at | TIMESTAMP | Creation time |
| updated_at | TIMESTAMP | Last update time |

Feature 012 registers exactly:

- get_reimbursement_status
- get_employee_information
- create_it_access_request

Revision `0008` creates unique `(workspace_id, tool_key)` and
`(id, workspace_id)` constraints, non-empty and enum checks, `RESTRICT`
Workspace/creator foreign keys, and Workspace/creator indexes. Status defaults
to `disabled`. Operation type and argument/result schemas remain immutable
application registry data and are not persisted.

## 10.1 Agent Tool Assignment

Table: agent_tools

| Field | Type | Description |
|---|---|---|
| workspace_id | UUID | Direct foreign key → workspaces.id |
| agent_id | UUID | Part of primary key; composite foreign key → agents(id, workspace_id) |
| tool_id | UUID | Part of primary key; composite foreign key → tools(id, workspace_id) |

The `(agent_id, tool_id)` primary key makes assignment idempotent. Both
composite foreign keys and the direct Workspace foreign key use `ON DELETE
RESTRICT`, preventing a cross-Workspace edge even if service validation is
bypassed. An assignment may be staged while either object is inactive, but it
is effective for routing only when the Agent and Tool are both active.

---

# 11. Workflow

Represents a business workflow.

Table: workflows

Fields:

| Field | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| workspace_id | UUID | Foreign key → workspaces.id |
| name | VARCHAR | Workflow name |
| description | TEXT | Workflow description |
| status | VARCHAR | draft / active / disabled |
| created_at | TIMESTAMP | Creation time |
| updated_at | TIMESTAMP | Last update time |

Detailed workflow node storage will be designed
when the Workflow feature is implemented.

---

# 12. Approval

Represents one human decision on a server-generated execution snapshot for a
write-sensitive Tool (Feature 013). Decision and execution are separate facts.

Table: approvals

Fields:

| Field | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| workspace_id | UUID | Foreign key → workspaces.id |
| requester_id | UUID | Composite foreign key (requester_id, workspace_id) → memberships(user_id, workspace_id) |
| agent_id | UUID | Composite foreign key → agents(id, workspace_id) |
| tool_id | UUID | Composite foreign key → tools(id, workspace_id) |
| action_type | VARCHAR(64) | it_access_request.create |
| canonical_arguments | JSONB | Validated arguments; the only execution input |
| canonical_arguments_sha256 | CHAR(64) | Versioned hash of the canonical arguments |
| capability_snapshot | JSONB | Execution-critical Workspace, requester Membership, Agent, Tool, assignment, and registry versions |
| policy_snapshot | JSONB | Approval policy version, reviewer roles, self-approval flag, TTL |
| snapshot_sha256 | CHAR(64) | Versioned digest over the arguments hash and both snapshots |
| decision_status | VARCHAR(16) | pending / approved / rejected / cancelled / expired / invalidated |
| decided_by | UUID | Reviewer or cancelling requester; composite foreign key → memberships |
| decided_at | TIMESTAMP | Time of leaving pending; equals expires_at for expired |
| decision_note | TEXT | Optional 1-1000 character note; approved / rejected only |
| invalidation_reason | VARCHAR(32) | requester_ineligible / capability_unavailable / configuration_drift |
| invalidation_triggered_by | UUID | Reviewer whose approve attempt found the problem; composite foreign key → memberships |
| execution_status | VARCHAR(16) | not_started / succeeded / failed |
| executed_at | TIMESTAMP | Time of the single execution attempt |
| execution_failure_category | VARCHAR(32) | adapter_error |
| expires_at | TIMESTAMP | created_at + 72 hours (database time) |
| created_at | TIMESTAMP | Creation time |
| updated_at | TIMESTAMP | Last update time |

Revision `0009` adds CHECK constraints for every value set and for the legal
`(decision_status, execution_status)` pairs (`approved` with `succeeded` or
`failed`; every other decision with `not_started`), timestamp and actor
presence, no self-decision, requester-only cancellation, notes only on human
decisions, and `decided_at = expires_at` for expiry. A partial unique index
`uq_approvals_pending_dedupe (workspace_id, requester_id, snapshot_sha256)
WHERE decision_status = 'pending'` suppresses duplicate pending requests only.
`uq_approvals_id_workspace_id` supports the Mock record foreign key. All
foreign keys use `ON DELETE RESTRICT`.

Users stay global identities. The composite Membership foreign keys only
guarantee that a named User has a Membership in the Approval's Workspace;
Membership status and role are verified by the service at each boundary.

## 12.1 Mock IT Access Request

Table: mock_it_access_requests

The record written by the single local Mock write adapter after an approval.
It is a mock enterprise-system object, never a Workbench permission.

| Field | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| workspace_id | UUID | Foreign key → workspaces.id |
| approval_id | UUID | Unique; composite foreign key → approvals(id, workspace_id) |
| requester_id | UUID | Composite foreign key → memberships(user_id, workspace_id) |
| reference | VARCHAR(32) | Unique deterministic ITAR-XXXXXXXXXXXX reference |
| system | VARCHAR(32) | production_database / analytics_warehouse / source_control |
| access_level | VARCHAR(16) | read_only / standard; production_database requires read_only |
| duration_days | INTEGER | 1-90 |
| status | VARCHAR(16) | recorded |
| created_at | TIMESTAMP | Creation time |

`UNIQUE (approval_id)` guarantees at most one business write per Approval.
The business justification is not copied into the Mock record.

---

# 13. Conversation

Represents one user-agent conversation.

Table: conversations

Fields:

| Field | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| workspace_id | UUID | Foreign key → workspaces.id |
| user_id | UUID | Foreign key → users.id |
| agent_id | UUID | Foreign key → agents.id |
| status | VARCHAR | active / closed |
| created_at | TIMESTAMP | Creation time |
| updated_at | TIMESTAMP | Last update time |

Messages will later be stored separately.

---

# 14. Execution Log

Append-only, allow-listed record of one handled AI operation
(Feature 014). One row per request to an in-scope route whose handler body
is entered: `agent_route`, `knowledge_answer`, `approval_decision`,
`approval_cancel`. Approval creation is the `agent_route` outcome
`tool_approval_required`.

Table: execution_logs

Fields:

| Field | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| workspace_id | UUID | Foreign key → workspaces.id |
| user_id | UUID | Composite foreign key (user_id, workspace_id) → memberships(user_id, workspace_id) |
| operation | VARCHAR(32) | agent_route / knowledge_answer / approval_decision / approval_cancel |
| routing_intent | VARCHAR(32) | knowledge_qa / tool_request / unsupported; agent_route only |
| status | VARCHAR(16) | succeeded / failed (failed iff non-2xx) |
| outcome | VARCHAR(40) | Fixed product outcome enum; nullable |
| error_category | VARCHAR(40) | Fixed sanitized failure enum; set iff failed |
| http_status | SMALLINT | Response status, 100-599 |
| latency_ms | INTEGER | Handler duration, >= 0 |
| agent_id | UUID | Composite foreign key → agents(id, workspace_id); nullable |
| tool_id | UUID | Composite foreign key → tools(id, workspace_id); nullable |
| tool_key | VARCHAR(64) | Denormalized Tool key; set iff tool_id is set |
| approval_id | UUID | Composite foreign key → approvals(id, workspace_id); nullable |
| knowledge_base_id | UUID | Composite foreign key → knowledge_bases(id, workspace_id); nullable |
| details | JSONB | Allow-listed metrics object (token counts, model and prompt version, citation count, not-executed reason, requested decision); default `{}` |
| created_at | TIMESTAMP | Creation time |

Revision `0010` creates the table with CHECK constraints for every value
set, `status`/`error_category`/`http_status` consistency, `routing_intent`
only on `agent_route`, the `tool_id`/`tool_key` pair, and an object-typed
`details`. Indexes `ix_execution_logs_workspace_created
(workspace_id, created_at, id)` and `ix_execution_logs_workspace_agent_created
(workspace_id, agent_id, created_at)` serve the newest-first list. All
foreign keys use `ON DELETE RESTRICT`; composite keys make cross-Workspace
references impossible. No existing table changes.

Request text, prompts, answers, citations, Tool arguments and results,
justifications, decision notes, names, emails, provider payloads, and
exception messages are never stored. Only same-Workspace `agent_admin` and
`system_admin` can read records; there is no write API. Retention is not
implemented yet.

---

# 15. Evaluation Case

Represents an AI evaluation test case.

Table: evaluation_cases

Fields:

| Field | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| workspace_id | UUID | Foreign key → workspaces.id |
| agent_id | UUID | Foreign key → agents.id |
| input | TEXT | Evaluation input |
| expected_behavior | TEXT | Expected result |
| category | VARCHAR | Evaluation category |
| status | VARCHAR | active / disabled |
| created_at | TIMESTAMP | Creation time |

Detailed evaluation result tables will be designed
when the evaluation module is implemented.

---

# 16. Workspace Isolation Rule

All workspace-owned business data should include:

workspace_id

Examples:

- knowledge_bases
- documents
- chunks
- agents
- tools
- workflows
- approvals
- conversations
- execution_logs
- evaluation_cases

Every backend query for workspace-owned resources
must verify workspace_id.

A user belonging to Workspace A must never be able to
read or modify Workspace B data.

---

# 17. MVP Phase 1 Tables

The first implementation milestone only requires:

- users
- workspaces
- memberships

Other tables are part of the planned data model,
but should not be implemented until their feature begins.

---

# 18. Open Design Questions

To be decided during later feature design:

- Fine-grained document permissions
- Department-level knowledge access
- Workflow node representation
- Conversation message structure
- Prompt version management
- Evaluation run and metric structure
