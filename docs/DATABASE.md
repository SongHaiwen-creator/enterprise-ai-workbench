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
| created_by | UUID | Foreign key → users.id |
| created_at | TIMESTAMP | Creation time |
| updated_at | TIMESTAMP | Last update time |

The MVP only supports text-extractable documents.

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
| embedding | VECTOR | Vector representation |
| created_at | TIMESTAMP | Creation time |

Chunks are used for RAG retrieval.

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

---

# 10. Tool

Represents an external business capability callable by an agent.

Table: tools

Fields:

| Field | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| workspace_id | UUID | Foreign key → workspaces.id |
| name | VARCHAR | Tool name |
| description | TEXT | Tool purpose |
| tool_type | VARCHAR | api / mock_api |
| endpoint | VARCHAR | API endpoint |
| risk_level | VARCHAR | low / medium / high |
| status | VARCHAR | active / disabled |
| created_at | TIMESTAMP | Creation time |

Example:

- get_expense_status
- create_it_access_request
- get_employee_profile

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

Represents a human approval request.

Table: approvals

Fields:

| Field | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| workspace_id | UUID | Foreign key → workspaces.id |
| requester_id | UUID | Foreign key → users.id |
| approver_id | UUID | Foreign key → users.id |
| action_type | VARCHAR | Requested action |
| status | VARCHAR | pending / approved / rejected / cancelled |
| request_payload | JSONB | Requested operation data |
| decision_note | TEXT | Approval comment |
| created_at | TIMESTAMP | Creation time |
| decided_at | TIMESTAMP | Decision time |

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

Stores important AI and tool execution events.

Table: execution_logs

Fields:

| Field | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| workspace_id | UUID | Foreign key → workspaces.id |
| user_id | UUID | Foreign key → users.id |
| agent_id | UUID | Foreign key → agents.id |
| event_type | VARCHAR | rag / tool_call / approval / error |
| input_data | JSONB | Input summary |
| output_data | JSONB | Output summary |
| status | VARCHAR | success / failed |
| latency_ms | INTEGER | Execution latency |
| created_at | TIMESTAMP | Creation time |

Sensitive information should not be stored
without filtering.

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
- Agent-to-tool many-to-many relationships
- Workflow node representation
- Conversation message structure
- Prompt version management
- Evaluation run and metric structure