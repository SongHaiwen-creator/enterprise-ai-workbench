# Enterprise AI Workbench - Architecture

Version: 0.1

## 1. Architecture Goals

The system should:

- Separate frontend, backend and AI capabilities
- Support workspace-level data isolation
- Support role-based access control
- Allow AI capabilities to call enterprise tools safely
- Keep important AI actions traceable
- Remain simple enough for an MVP

---

## 2. High-Level Architecture

User
↓
Next.js Frontend
↓
FastAPI Backend
↓
PostgreSQL / AI Services

The backend is the central control layer.

The frontend should not directly access LLM APIs or protected
enterprise data.

---

## 3. Frontend

Technology:

- Next.js
- TypeScript

Responsibilities:

- User interface
- Authentication state
- Workspace selection
- Knowledge management interface
- Agent interaction interface
- Approval interface
- Logs and evaluation dashboard

The frontend communicates with the backend through HTTP APIs.

---

## 4. Backend

Technology:

- FastAPI
- Python

Responsibilities:

- Business logic
- Authentication and authorization
- Workspace isolation
- Knowledge management
- Agent orchestration
- Tool execution
- Approval logic
- Logging
- Evaluation APIs

The backend is responsible for enforcing permissions.

---

## 5. Database

Technology:

- PostgreSQL

Responsibilities:

- Users
- Workspaces
- Memberships
- Roles
- Knowledge bases
- Documents
- Agents
- Tools
- Workflows
- Approvals
- Conversations
- Execution logs
- Evaluation cases
- Evaluation datasets

Vector search will use pgvector.

---

## 6. AI Layer

The AI layer contains:

- LLM API
- Embedding model
- RAG retrieval
- Intent routing
- Tool calling
- Prompt management

Initial agent flow:

User Question
↓
Permission Check
↓
Intent Routing
↓
RAG or Tool Call
↓
LLM Generation
↓
Response
↓
Execution Log

---

## 7. Tool Layer

Enterprise systems will initially be represented by mock APIs.

Example tools:

- Get reimbursement status
- Submit IT access request
- Query employee information

The LLM must not directly modify protected business data.

Tool execution is controlled by the backend.

---

## 8. Approval Layer

Sensitive actions require human approval before execution (Feature 013).

```text
Request production database access
↓
Agent routing and Tool selection (Features 011-012)
↓
Creation authorization → pending Approval + immutable execution snapshot
↓
Authorized reviewer (same-Workspace system_admin, never the requester)
↓
Decision authorization → reject | approve
↓
Execution authorization + drift check (before approved is committed)
  fails → Approval invalidated, 409, nothing executes
  passes → approved + one local Mock write in the same transaction
↓
Durable decision fact and separate execution fact
```

The backend owns Approval state, policy, and authorization. Execution input is
read only from the server-held snapshot; client-supplied arguments are never
trusted. Creation, decision, and execution are separately authorized from
current Membership, Agent, Tool, and assignment state, and competing
decisions are serialized by an Approval row lock. The only write executor is
a statically registered local Mock adapter; there is no generic HTTP executor.
Generic execution logs are recorded by Feature 014 (Section 9).

---

## 9. Security Principles

### Workspace Isolation

Data belonging to one workspace must not be accessible
from another workspace.

### Backend Authorization

Permission checks must happen on the backend.

Hiding UI elements is not considered authorization.

### Secret Management

API keys and secrets must be stored in environment variables.

They must never be committed to Git.

### Auditability

Sensitive AI and tool actions should generate execution logs.

Feature 014 records one allow-listed `execution_logs` row per handled Agent
request, grounded knowledge answer, and Approval decision or cancel. The
recorder wraps the route handler, classifies the outcome by exception type,
and writes after the business transaction ends: it unconditionally rolls back
the request Session before starting the log transaction, so work the handler
left uncommitted is never committed by the log. Recording is best-effort and never changes the
response; for write-sensitive actions the Approval row remains the
authoritative audit record. Records store IDs, enums, latency, and
allow-listed metrics only, never request or answer content. Same-Workspace
`agent_admin` and `system_admin` read them through the API and a read-only
view.

---

## 10. MVP Technical Stack

Frontend:
Next.js + TypeScript

Backend:
FastAPI + Python

Database:
PostgreSQL

Vector Search:
pgvector

AI:
LLM API + Embedding API

Testing:
pytest + Playwright

Version Control:
Git + GitHub

Deployment:
To be decided after local MVP is stable

## 11. Evaluation Definition Management (Feature 015)

Workspace -> EvaluationDataset -> EvaluationCase is an administrative CRUD
surface, separate from the AI execution layer. Same-Workspace `agent_admin`
and `system_admin` use typed frontend forms and eight backend list/detail/
create/PATCH endpoints. Current backend Membership checks authorize every
request; scoped queries and composite foreign keys isolate Dataset, Case,
creator and optional Agent/Knowledge Base/Tool references.

The Evaluation router uses a custom `APIRoute` around FastAPI's generated
handler to return the fixed `422` body before malformed body/path/query
validation can escape. It never serializes validation input, exception context,
SQL parameters or request content into errors or logs. This wrapper applies
only to Evaluation routes; existing validation contracts are unchanged.

Services serialize Case creation with Dataset status changes on the parent
row and merge Case PATCH against a freshly locked row. Five-second lock
timeout returns a sanitized `409` and rolls back. References and actor labels
are test definitions, never authorization or execution grants.

Cases contain synthetic/redacted Workspace-confidential input in PostgreSQL,
unlike the metadata-only Execution Logs. There is no provider call, Tool
dispatch, Approval, execution-log recorder, evaluation run, metric, scoring,
external transfer or background job. Disable retains content. Execution,
identity fixture construction and data egress require a separate Feature 016
design. Migration `0011` is additive; runtime migration is not authorized.
