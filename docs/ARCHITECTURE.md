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
Generic execution logs belong to the Logs & Evaluation milestone.

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