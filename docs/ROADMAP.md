# Enterprise AI Workbench - Roadmap

Version: 0.1

## 1. Development Principles

The project will be developed incrementally.

Each milestone should:

- Deliver one coherent product capability
- Have clear acceptance criteria
- Be developed through GitHub Issues
- Be tested before merging into main
- Avoid implementing future features prematurely

The goal is not to build every planned feature at once.

---

# 2. Milestone 0 - Project Foundation

Status: In Progress

Goal:

Define the product, system architecture and initial data model
before application development begins.

Deliverables:

- PRODUCT_SPEC.md
- ARCHITECTURE.md
- DATABASE.md
- ROADMAP.md

Acceptance Criteria:

- Product scope is defined
- MVP boundaries are defined
- Core technical architecture is defined
- Core entities and relationships are defined
- Initial development milestones are defined

---

# 3. Milestone 1 - Workspace & RBAC

Goal:

Build the enterprise workspace and permission foundation.

This milestone should work without any AI capability.

## Features

### Workspace

- Create workspace
- View workspace information
- Select current workspace

### User

- Basic user account
- Login
- User profile

### Membership

- Add users to a workspace
- View workspace members
- Change member status

### Role-Based Access Control

MVP roles:

- employee
- knowledge_admin
- agent_admin
- system_admin

## Initial Issues

- Project frontend initialization
- Project backend initialization
- PostgreSQL connection
- Create users table
- Create workspaces table
- Create memberships table
- Implement authentication
- Implement workspace APIs
- Implement membership APIs
- Implement backend authorization
- Build workspace management interface

## Acceptance Criteria

- A user can log in
- A user can belong to a workspace
- A user can belong to multiple workspaces
- The same user can have different roles in different workspaces
- An employee cannot access system administrator APIs
- Workspace A users cannot access Workspace B data
- Permission checks happen on the backend

---

# 4. Milestone 2 - Enterprise Knowledge Base

Goal:

Allow enterprise administrators to manage knowledge
and allow employees to retrieve authorized information.

## Features

### Knowledge Base Management

- Create knowledge base
- Edit knowledge base
- Disable knowledge base

### Document Management

- Upload supported documents
- Parse text
- Track processing status
- Disable documents

### RAG

- Split document text into chunks
- Generate embeddings
- Store vectors
- Retrieve relevant chunks
- Generate answers using retrieved knowledge
- Display citations

## MVP Supported Files

- Text-extractable PDF
- TXT
- Markdown

## Out of Scope

- OCR
- Complex tables
- Images
- Audio and video ingestion

## Acceptance Criteria

- Administrator can upload documents
- Document processing status is visible
- Ready documents can be retrieved through RAG
- Disabled documents cannot appear in retrieval
- Answers contain source citations
- Workspace data isolation is preserved during retrieval

---

# 5. Milestone 3 - Agent & Enterprise Tools

Goal:

Move from knowledge Q&A to executable enterprise AI tasks.

## Features

### Agent

- Create agent
- Configure system prompt
- Enable or disable agent

### Intent Routing

Route user requests to:

- Knowledge retrieval
- Tool calling
- Unsupported request

### Tool Calling

Initial mock tools:

- Get reimbursement status
- Get employee information
- Create IT access request

### Human Approval

Sensitive actions require approval before execution.

## Acceptance Criteria

- Agent can distinguish knowledge questions from tool requests
- Business data is obtained through tools rather than hallucinated
- Tool arguments are validated
- High-risk actions create approval requests
- High-risk tools cannot execute before approval
- Tool execution creates logs

---

# 6. Milestone 4 - Logs, Evaluation & Bad Cases

Goal:

Make AI behavior measurable, traceable and improvable.

## Features

### Execution Logs

Record:

- User
- Agent
- Event type
- Tool
- Status
- Latency
- Error information

### Evaluation Dataset

Support evaluation cases for:

- Knowledge Q&A
- Tool calling
- Permission boundaries
- Refusal behavior

### Evaluation Metrics

Initial metrics may include:

- Answer correctness
- Citation correctness
- Retrieval success
- Tool calling success
- Task completion
- Refusal accuracy
- Latency

### Bad Case Management

- Identify failed cases
- Classify bad cases
- Record possible causes
- Compare versions

## Acceptance Criteria

- Important AI operations are traceable
- Evaluation cases can be executed repeatedly
- Failed cases can be reviewed
- At least two agent versions can be compared
- Evaluation results can support product iteration

---

# 7. Development Order

Planned order:

Milestone 0
Project Foundation

↓

Milestone 1
Workspace & RBAC

↓

Milestone 2
Knowledge Base & RAG

↓

Milestone 3
Agent & Tool Calling

↓

Milestone 4
Evaluation & Operations

The project should not move to the next milestone
until the previous milestone has a usable baseline.

---

# 8. Portfolio Target

The final project should demonstrate:

- B2B platform product thinking
- Workspace and permission design
- Enterprise knowledge management
- RAG understanding
- Agent and tool calling design
- Human-in-the-loop control
- AI evaluation
- Bad case analysis
- Product-to-engineering collaboration
- Git-based development workflow