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

Status: Baseline delivered

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

Status: Baseline delivered (Features 001-005 merged)

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

Status: Baseline delivered (Features 006-010 merged)

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

Status: Baseline delivered (Features 011-013 merged)

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

Feature 013 persists Approvals with an immutable execution snapshot, lets a
same-Workspace `system_admin` other than the requester approve or reject, and
executes a single local Mock IT access write only after a still-valid
approval. A minimal Approvals UI lists, shows, approves, and rejects.

## Acceptance Criteria

- Agent can distinguish knowledge questions from tool requests
- Business data is obtained through tools rather than hallucinated
- Tool arguments are validated
- High-risk actions create approval requests
- High-risk tools cannot execute before approval
- Tool execution creates logs (write-sensitive executions are recorded as Feature 013
  Approval lifecycle facts; Feature 014 execution logs record every Agent request,
  including read-only Tool executions)

---

# 6. Milestone 4 - Logs, Evaluation & Bad Cases

Status: In Progress (Feature 014 Execution Logs merged/delivered in PR #33;
Feature 015 Evaluation Dataset merged/delivered in PR #35 on 2026-10-02;
Feature 016 Evaluation Run & Metrics merged/delivered in PR #37 on 2026-10-03;
Features 017-020 merged/delivered, including Feature 020 PR #49;
Feature 021 Document Version Management is in Phase A specification,
with implementation awaiting explicit approval)

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

Feature 015 covers Workspace-owned dataset and case management only. Its
approved specification is in `docs/features/015-evaluation-dataset.md`.
Delivered Phase B includes typed Dataset/Case CRUD, administrative UI, and additive
migration `0011`, with verification recorded in its specification. PR #35 is
merged and Issue #34 is closed. Repository migration head does not guarantee
the revision of any runtime database.
Evaluation execution and metrics are delivered separately in Feature 016.

Support evaluation cases for:

- Knowledge Q&A
- Tool calling
- Permission boundaries
- Refusal behavior

### Evaluation Run & Metrics (Feature 016)

H1-H7-approved Phase B implementation: `docs/features/016-evaluation-run-metrics.md`.
Revision `0012`, bounded synchronous runner and administration UI are implemented
and merged into `main` through PR #37 on 2026-10-03. Issue #36 is closed.
Metrics supported by current structured Case expectations are:

- Overall/category pass rates with separate ERROR counts and evaluation coverage
- Routing match rate
- Tool selection and would-execute/approval-outcome match rates (dry run only)
- Shared permission-policy fixture pass rate
- Structured refusal compliance
- Citation presence/absence requirement compliance
- Latency summary

Semantic answer correctness, citation correctness and retrieval relevance require
ground truth not present in Feature 015 and are deferred. Tool adapter execution,
Approval creation, semantic judging and version comparison are outside Feature 016.

### Chinese UI Refresh (Feature 017)

User-prioritized presentation scope: `docs/features/017-chinese-ui-refresh.md`,
Issue #39, branch `feat/chinese-ui-refresh`. Public Chinese product introduction
at `/`, existing platform at `/app` with Assistant as the default, shared blue
and white styling, grouped navigation and mobile drawer. Existing Feature 016
run/metrics UI is included. No new product capabilities, migrations or
permission-policy changes. Required verification passed; PR #41 was human-merged
on 2026-10-04 and Issue #39 is closed.

### Bad Case Management

Feature 018 H1-H4-approved Phase B implementation:
`docs/features/018-bad-case-management.md`, Issue #42, branch
`feat/bad-case-management`, PR #43 (human-merged on 2026-10-04; Issue #42 closed). Scope is manual issue tracking from
terminal Evaluation Run Cases, separating behavioral FAIL, execution ERROR
and human review, with classification, possible causes, handling state and
atomic change history, with revision conflict protection and additive migration
`0013`. The user subsequently authorized the local runtime upgrade: `0012 -> 0013`
was backed up and verified on 2026-10-04, with the existing 17 table structures and
row counts unchanged. This does not imply any other deployment was upgraded. Verification is recorded in
`docs/features/018-bad-case-management-verification.md`.
Run/version comparison and retest linking are deferred to proposed
Feature 023 in planning PR #40, which is not yet merged.

- Identify failed cases
- Classify bad cases
- Record possible causes
- Compare versions

### Knowledge Administration UI (Feature 019 - merged/delivered)

The user selected Feature 019 as the next feature after delivered Feature 018
and the supporting business evaluation baseline. Its specification is
`docs/features/019-knowledge-admin-ui.md`, tracked in Issue #46 on branch
`feat/knowledge-admin-ui`. The user approved proposal `1c61fca` with
"approve，实施"; Phase B is implemented and verified in PR #47, human-merged
on 2026-10-10; Issue #46 is closed.
Evidence: `docs/features/019-knowledge-admin-ui-verification.md`.
The scope follows the Knowledge Administration UI entry in planning PR #40,
which remains unmerged, and reuses merged Features 006-010 on latest `main`.

Current-Workspace Knowledge/System administrators can manage Knowledge Base
metadata and status, upload and inspect Documents, explicitly index/re-index,
and disable/re-enable Documents through existing APIs. No new backend contract,
migration, authorization policy or dependency was added. Parsing readiness
and indexing success must remain distinct; Document version/replacement work
is deferred to proposed Feature 021. Delivery of this feature does not approve
the full remaining MVP plan.

### Agent & Tool Administration UI (Feature 020 - merged/delivered)

The user selected Feature 020 after Feature 019's human merge, requested
specification first, and then approved proposal `6cc4278` with "approve".
The specification is `docs/features/020-agent-tool-admin-ui.md` on branch
`feat/agent-tool-admin-ui`, tracked in Issue #48 and PR #49.
Implementation, full backend/frontend checks and browser acceptance
are recorded in `docs/features/020-agent-tool-admin-ui-verification.md`.
The user separately authorized the dedicated PostgreSQL test-schema verification;
all required checks passed. PR #49 has been human-merged; Issue #48 is closed.
This was rechecked from GitHub and latest main `2508d67` when starting Feature 021.
It follows the Feature 020 entry in still-open planning PR #40 at `77acb1a`,
without adopting that unmerged plan as the delivered baseline.

Scope: Chinese Agent create/edit/status UI, three registered Mock Tool
configurations, assignment/unassignment, and read-only capability restrictions.
Only current-Workspace Agent/System administrators manage configurations;
employees retain the existing active-Agent use path. It reuses Features 011-013
and the current navigation without new APIs, migrations, execution permissions,
approval policies or dependencies. Configuration versions remain Feature 022;
its implementation thread ends with human merge.

### Document Version Management (Feature 021 - Phase A proposal)

The user selected Feature 021 after Feature 020's human merge and requested
specification first. The proposal is
`docs/features/021-document-version-management.md`, tracked in Issue #50 on
branch `feat/document-version-management`, based on latest main `2508d67`.
It adopts only Feature 021's minimum scope from still-open planning PR #40
at `77acb1a`; the full remaining MVP plan is not adopted or implemented.

Proposed scope: stable document families with immutable concrete versions,
replacement upload and explicit activation, failure preservation of the old
current version, frozen successful Chunk sets, current-only retrieval and
Evaluation corpus capture, and historical citation identity. Reuse the existing
Knowledge Administration UI and current Knowledge/System administrator policy.

This is high-risk Phase A design only. Proposed migration 0014, legacy backfill,
indexing compatibility changes, atomic activation, historical storage, API/UI
and dedicated-test-database destructive verification require explicit H1-H4
approval tied to the proposal commit. No application implementation, migration,
database reset, runtime upgrade or live Provider verification has occurred.
Independent implementation review and human merge remain required; do not start
Feature 022 in this development thread.

### Supporting business evaluation baseline

User-requested benchmark work after Feature 018: Issue #44,
`docs/evaluation/business-baseline-spec.md`. An original synthetic employee-service
corpus contains 12 policies and 108 cases, grouped into 74 development and 34
holdout cases. It reuses existing APIs and does not implement Features 019–023.
After normal login configuration, all 108 cases were imported and measured in
26 Runs: 91 PASS, 9 FAIL, 8 ERROR. RAG measured 56 retrieval and 56 answer first
attempts; 48 answerable questions had 100% Document Recall@5 on 12 short synthetic
policies. Four representative findings are open in existing Bad Case management;
tool holdout expectations need review. These are synthetic structural measures,
not real business accuracy or ROI. Business-owner gold/answer review and real-task
pilot measurements remain necessary. See `docs/evaluation/business-baseline-v1-report.md` and
`docs/evaluation/employee-service-pilot.md`.

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
