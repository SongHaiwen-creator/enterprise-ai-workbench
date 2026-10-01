# Feature 015 - Evaluation Dataset

Status: Phase B implemented; pending independent review and human merge (PR #35)
Milestone: 4 (in progress)
Baseline: `main` at `760d7fb315993b52835a5a5ff019adaa200dbe13`
Branch: `feat/evaluation-dataset`
Issue: [#34](https://github.com/SongHaiwen-creator/enterprise-ai-workbench/issues/34)
Risk: High - new migration, Workspace isolation, administrative authorization,
and intentional storage of evaluation input content.

## 1. Goal and phase boundary

Let Workspace Agent/System administrators maintain reusable evaluation datasets
and cases for later automated evaluation. Feature 015 manages definitions only.
It never executes an Agent, calls a provider or Tool, creates an Approval,
computes metrics, or claims that a case passed.

The initial Phase A delivered a specification, tracking Issue, documentation commit,
and Phase-A-only PR. No application/test code, migration file, runtime database
changes, or new dependencies were authorized in that phase. Phase B was explicitly
approved on 2026-10-01 against commit `a55f634` (H1-H5). Feature 016 requires a separate design and
development thread.

## 2. Read-only baseline verification (2026-10-01)

| Check | Evidence / result |
|---|---|
| Current branch before changes | `main` |
| Local HEAD and cached `origin/main` | Both `760d7fb315993b52835a5a5ff019adaa200dbe13` |
| Live remote main | `git ls-remote origin refs/heads/main` returned the same SHA; no fetch or checkout needed |
| Feature 014 | PR [#33](https://github.com/SongHaiwen-creator/enterprise-ai-workbench/pull/33) merged at 2026-10-01 07:04:55 UTC; merge commit is the baseline |
| Issue #32 | [Closed](https://github.com/SongHaiwen-creator/enterprise-ai-workbench/issues/32) at 2026-10-01 07:04:56 UTC |
| Repository Alembic head | `ScriptDirectory.get_heads()` returned only `0010`; predecessor `0009` |
| Worktree | Not clean: modified `frontend/next-env.d.ts`; untracked `backups/`, `frontend/AGENTS.md`, `frontend/CLAUDE.md` |
| Worktree exception | User explicitly approved preserving those files and proceeding with documentation only; none belongs in this commit |
| Existing Feature 015 | No spec, migration, model, schema, service, route, or product test found |
| Existing evaluation work | Feature 009 offline EnterpriseRAG benchmark and baseline report exist; they are not dataset CRUD and will remain separate |

Runtime database revision was not inspected: the requested check is the
repository migration head, and this phase must not modify the runtime database.
Sources inspected: root `AGENTS.md`, `PRODUCT_SPEC.md`, `ARCHITECTURE.md`,
`DATABASE.md`, `ROADMAP.md`, Feature 011-014 specifications, authorization,
Knowledge Base CRUD, Agent/Tool/answer contracts, execution-log routes/schemas,
models, migration chain, PostgreSQL fixtures, and existing benchmark tests.

## 3. Scope and existing patterns

Approved and implemented Phase B scope:

- Workspace-owned Dataset and Case create, list, detail, edit, disable/reactivate.
- Exactly four case types: `knowledge_qa`, `tool_calling`,
  `permission_boundary`, `refusal_behavior`.
- Strict type-specific expected behavior, bounded input, optional scoped
  Agent/Knowledge Base/Tool references, server-owned identity and timestamps.
- Minimal administration UI recommended in Section 10 (H3).
- Offline unit tests, real PostgreSQL integration and migration tests,
  frontend tests and regression verification; independent review before merge.

Reuse `AgentAdministratorMembership` and `CurrentUser`, the existing request
Session, explicit service-owned commits, `NotFoundError`/`ConflictError`,
Pydantic `extra="forbid"`, `StringEnumType`, database-generated UUIDs,
timezone-aware timestamps, and the list envelope `{items, limit, offset}`.
Use the same scoped lookup style as `services/knowledge_bases.py` and the
composite constraints used by Agent Tools, Approvals and Execution Logs.

`DATABASE.md` Section 15 is a planning sketch, not an existing table. This
proposal refines its flat Case/Agent model into Dataset -> Case, makes Agent
context optional to support reusable datasets, and replaces free-form expected
text with typed JSONB. Update that section and the Workspace hierarchy in Phase
B together with the implemented schema. No architecture or
existing authentication redesign is proposed.

## 4. Product and business rules (H4)

1. Workspace -> EvaluationDataset -> EvaluationCase. Dataset names and Case
   names need not be unique. No default dataset, seeded cases, or bulk import.
2. Both objects default to `active`; `disabled` retains data for editing and
   read access by authorized administrators. Dataset disabling does not change
   individual Case statuses. Effective eligibility for a future runner would
   require both active, but no eligibility execution is implemented here.
3. Disabled datasets accept Case edits and status changes, but Case creation
   returns `409` until the Dataset is reactivated. Dataset PATCH remains allowed.
4. Case cannot move between datasets; `workspace_id`, `dataset_id`, `id`,
   `created_by`, timestamps, `case_type`, and schema version are client-immutable.
   Create a new Case for a different category. No hard delete API or cloning.
5. Input is plain text, not a prompt template, URL, executable script or
   arbitrary HTTP request. It is never interpreted or executed in this feature.
6. Case references describe a fixture/expectation and confer no access or
   assignment. Draft/disabled Agents, KBs and Tools may be referenced to stage
   negative cases; ownership and existence must still be validated.
7. No Agent-Tool assignment is created or required for storage. An expectation
   may deliberately describe unavailable capabilities. Future execution must
   freshly authorize all resources and must never trust Case metadata as a grant.
8. A PATCH merges supplied fields with the persisted object, then validates the
   complete resulting Case and its references before any write. Failed updates
   are atomic. Unknown fields and empty PATCH objects return sanitized `422`.
   Serialize Dataset status changes and Case creation on the parent Dataset
   row; hold the scoped parent lock through creation commit so disabling cannot
   race past the active-parent check. Serialize Case PATCH on its scoped row
   so concurrent partial updates merge against the latest committed state.
   Reuse the existing bounded lock-timeout pattern; timeout returns sanitized
   `409` with `Evaluation resource is busy`, with no partial mutation.
9. All references are explicit UUID columns. JSON expectations never accept
   UUIDs, resource paths, URLs, names of people, arbitrary tool keys, or scripts.
   Negative cross-Workspace contexts use synthetic labels, never another
   Workspace's real IDs. Free text is opaque and never treated as a reference.
10. Service updates `updated_at` on a successful PATCH. Last committed update
    wins; no revision history or optimistic concurrency token in this MVP.
    Creatorship remains immutable and does not claim a full mutation audit.

## 5. Exact proposed persistence model (H1)

All fields below are required unless marked nullable. All foreign keys use
`ON DELETE RESTRICT`. No existing table changes are needed.

### 5.1 `evaluation_datasets`

| Column | PostgreSQL type | Rules |
|---|---|---|
| `id` | UUID | PK; `gen_random_uuid()` |
| `workspace_id` | UUID | FK -> `workspaces.id` |
| `name` | VARCHAR(255) | Trimmed nonblank; 1-255 characters |
| `description` | TEXT | Nullable; trimmed; at most 5000 characters |
| `status` | VARCHAR(16) | `active` / `disabled`; default `active` |
| `created_by` | UUID | Composite FK `(created_by, workspace_id)` -> `memberships(user_id, workspace_id)` |
| `created_at`, `updated_at` | TIMESTAMPTZ | Database default `now()`; service maintains update time |

Unique `(id, workspace_id)` supports the child composite FK. Index
`ix_evaluation_datasets_workspace_created` on `(workspace_id, created_at, id)`
supports newest-first lists; index `ix_evaluation_datasets_created_by` supports
creator references.

### 5.2 `evaluation_cases`

| Column | PostgreSQL type | Rules |
|---|---|---|
| `id` | UUID | PK; `gen_random_uuid()` |
| `workspace_id` | UUID | FK -> `workspaces.id` |
| `dataset_id` | UUID | Composite FK `(dataset_id, workspace_id)` -> `evaluation_datasets(id, workspace_id)` |
| `case_type` | VARCHAR(32) | One of the four Section 3 values; immutable |
| `name` | VARCHAR(255) | Trimmed nonblank; 1-255 characters |
| `description` | TEXT | Nullable; trimmed; at most 5000 characters |
| `test_input` | TEXT | Trimmed nonblank; 1-2000 characters, matching Agent request limit |
| `expected_behavior` | JSONB | Required type-specific object; no empty-object default |
| `schema_version` | SMALLINT | Server-owned constant `1`; immutable |
| `agent_id` | UUID | Nullable; composite FK -> `agents(id, workspace_id)` |
| `knowledge_base_id` | UUID | Nullable; composite FK -> `knowledge_bases(id, workspace_id)` |
| `tool_id` | UUID | Nullable; composite FK -> `tools(id, workspace_id)` |
| `status` | VARCHAR(16) | `active` / `disabled`; default `active` |
| `created_by` | UUID | Composite FK -> `memberships(user_id, workspace_id)` |
| `created_at`, `updated_at` | TIMESTAMPTZ | Database default `now()`; service maintains update time |

Unique `(id, workspace_id)` allows later same-Workspace references without
implementing results now. Index `ix_evaluation_cases_workspace_dataset_created`
on `(workspace_id, dataset_id, created_at, id)` supports nested lists; indexes
on `created_by`, `agent_id`, `knowledge_base_id`, `tool_id` support references.

Dataset and Case checks enforce status enums, trimmed nonblank bounded names,
description limits, Case type, bounded nonblank input, `schema_version = 1`,
and object-typed nonempty JSONB. Strict nested field/type/combination validation
belongs to Pydantic and the service; JSONB checks alone do not claim to enforce
the complete expectation schema. All production writes must use that service.

The composite Membership FK validates Workspace membership existence for the
creator; it does not encode active status or role. Those remain backend checks.

## 6. Expected behavior contract (H4)

The server chooses the expectation schema using immutable `case_type`.
All nested schemas forbid extra fields. Enums use exact strings; booleans and
integers reject coercion. Every listed field is required unless explicitly
optional. Null is rejected unless listed as permitted. There is no free-form
expected answer, semantic score, judge prompt, expression language or payload.

### 6.1 Knowledge Q&A

```json
{"routing_intent":"knowledge_qa","answer_status":"answered","citation_requirement":"present"}
```

- `routing_intent`: literal `knowledge_qa`.
- `answer_status`: `answered` / `unsupported`.
- `citation_requirement`: `present` / `none`; `answered` requires `present`,
  `unsupported` requires `none`, matching the existing grounded-answer contract.
- `knowledge_base_id`: required Case column for this type; `agent_id` optional;
  `tool_id` must be null.

The KB column is the expected knowledge context. Citation expectation only
records presence/absence; exact Document/Chunk IDs, citation excerpts, answer
facts and citation scoring are deferred. This avoids unstable Chunk references
after reindexing and a new reference table without a demonstrated MVP need.

### 6.2 Tool calling

```json
{"routing_intent":"tool_request","outcome":"approval_required","tool_key":"create_it_access_request","approval_required":true,"non_execution_reason":null}
```

- `routing_intent`: literal `tool_request`.
- `outcome`: `executed` / `approval_required` / `not_executed`.
- `tool_key`: one of the three existing registry keys, or null.
- `approval_required`: strict boolean.
- `non_execution_reason`: null or `no_available_tool` / `no_matching_tool` /
  `missing_required_arguments`, exactly the current Tool outcome vocabulary.
- `executed`: non-null `tool_id` and matching read-only registry key,
  `approval_required=false`, reason null.
- `approval_required`: non-null `tool_id`, matching
  `create_it_access_request`, `approval_required=true`, reason null. This is
  an expected proposal, not an actual Approval or business write.
- `not_executed`: `tool_id` and `tool_key` null, `approval_required=false`,
  non-null reason. Future selected-but-denied tools need a new contract.
- `knowledge_base_id` must be null; `agent_id` optional.

Service resolves `tool_id` within the Workspace and verifies key consistency
against the existing registry; no adapter dispatch occurs.

### 6.3 Permission boundary

```json
{"actor_role":"employee","actor_membership_status":"active","target_context":"other_workspace","operation":"agent_route","expected_http_status":404,"result_category":"not_found","access_denied":true}
```

- `actor_role`: one of the four existing Membership roles.
- `actor_membership_status`: `active` / `invited` / `disabled` / `absent`.
- `target_context`: `same_workspace` / `other_workspace` / `nonexistent`.
- `operation`: `agent_route` / `knowledge_answer` / `agent_configuration_read` /
  `tool_configuration_read` / `evaluation_dataset_read`.
- `expected_http_status`: strict integer, `403` / `404` only.
- `result_category`: `forbidden` iff `403`, `not_found` iff `404`.
- `access_denied`: literal true.

These are proposed test labels, not live identity overrides. No actor User,
Membership, credential or foreign Workspace ID is accepted. Optional scoped
Agent or KB columns may describe a same-Workspace fixture: `agent_id` allowed
only for `agent_route`/`agent_configuration_read`, `knowledge_base_id` only
for `knowledge_answer`, `tool_id` only for `tool_configuration_read`.
`evaluation_dataset_read` uses the enclosing Dataset and permits no references.
All non-same-Workspace target contexts require these reference columns null.
The author declares an expected denial; storage does not certify the scenario
or determine how a future runner constructs an isolated fixture.

### 6.4 Refusal behavior

```json
{"routing_intent":"unsupported","response_category":"unsupported_request","safe_response_required":true}
```

- `routing_intent`: `unsupported` / `knowledge_qa`.
- `response_category`: `unsupported_request` for `unsupported`, or
  `knowledge_unsupported` for `knowledge_qa`.
- `safe_response_required`: literal true, expressing author intent only.
- `agent_id` optional; KB required for `knowledge_qa`, otherwise null;
  `tool_id` null.

The current Agent API has no distinct `refused` outcome. Do not invent one or
equate provider failure with refusal. An unsupported response does not by
itself prove safety; measuring safe refusal belongs to Feature 016.

## 7. Authorization and Workspace isolation (H2)

All operations require active User, active route Workspace and active Membership.

| Operation | employee | knowledge_admin | agent_admin | system_admin |
|---|---|---|---|---|
| Dataset/Case list and detail, including content | Deny | Deny | Allow | Allow |
| Dataset/Case create and edit | Deny | Deny | Allow | Allow |
| Dataset/Case disable and reactivate | Deny | Deny | Allow | Allow |
| Run evaluation or grant permissions | No endpoint | No endpoint | No endpoint | No endpoint |

Reuse `AgentAdministratorMembership`; add no role, role inheritance, or adjacent
KB/Member/Approval privileges. Authorization runs before resource lookups in
the handler. Existing Workspace boundary responses remain unchanged: missing
Workspace `404`, disabled Workspace or absent/inactive Membership `403`.

Every Dataset query uses `(workspace_id, dataset_id)`. Every Case query uses
`(workspace_id, dataset_id, case_id)` and first resolves the scoped parent.
Foreign and nonexistent Dataset/Case/reference IDs return identical generic
`404` bodies; no ownership explanation, name or foreign ID is echoed.
Cross-dataset Case IDs also return `404`. Lists always filter route Workspace
and parent Dataset, including with filters/pagination.

Referenced Agent/KB/Tool queries always include the same Workspace; composite
FKs independently prevent foreign edges. Unknown and foreign supplied references
use `{"detail":"Evaluation reference not found"}` for either condition.
Membership roles/status are never read from the request. Disabled objects can
remain references; hard deletion is restricted. No database RLS is added, so
correct scoped services plus integration tests remain essential.

## 8. API and data contracts

All routes below are under `/api/workspaces/{workspace_id}` and role-gated.

| Method | Path suffix | Success | Behavior |
|---|---|---|---|
| POST | `/evaluation-datasets` | 201 DatasetResponse | Create |
| GET | `/evaluation-datasets` | 200 DatasetListResponse | List metadata |
| GET | `/evaluation-datasets/{dataset_id}` | 200 DatasetResponse | Detail |
| PATCH | `/evaluation-datasets/{dataset_id}` | 200 DatasetResponse | Edit/status |
| POST | `/evaluation-datasets/{dataset_id}/cases` | 201 CaseResponse | Create under active Dataset |
| GET | `/evaluation-datasets/{dataset_id}/cases` | 200 CaseListResponse | List summaries |
| GET | `/evaluation-datasets/{dataset_id}/cases/{case_id}` | 200 CaseResponse | Explicit content detail |
| PATCH | `/evaluation-datasets/{dataset_id}/cases/{case_id}` | 200 CaseResponse | Edit/status |

Dataset create: `{name, description?}`; description defaults null and status
is server-default active. Dataset PATCH accepts `name`, `description`, `status`.
Case create: `{case_type, name, description?, test_input, expected_behavior,
agent_id?, knowledge_base_id?, tool_id?}`; nullable references default null,
status server-default active. Case PATCH accepts those same fields except
`case_type`, plus `status`; cannot alter ownership or move the Case.

PATCH omission retains a field; null clears description or nullable references
only when the complete merged Case remains valid. Name, input, expectation
and status cannot be null. `expected_behavior` is replaced as a whole, never
deep-merged. Validation limits are the same as the persistence model. Trim
strings; reject embedded NUL; blank descriptions normalize to null. Preserve
internal line breaks in input. Server fields in request bodies return `422`.

DatasetResponse exposes all Dataset columns. CaseResponse exposes all Case
columns including input and typed expectation. CaseSummary excludes
`test_input` and `expected_behavior`; remaining Case columns are included.
No linked names, emails, prompts, business results or provider fields are added.
All response models validate their declared types.

Lists return `{items: [...], limit: 50, offset: 0}`. `limit` defaults 50,
range 1-100; `offset` defaults 0, minimum 0. Optional `status` filter on both,
optional `case_type` on Cases. Default includes active and disabled objects.
Sort by `created_at DESC, id DESC`; no total count, free-text search, export
or unbounded list. Concurrent edits can shift offset pages; this is accepted
for the small MVP and is not a snapshot contract.

Errors: existing `401` (Bearer challenge), Workspace/role `403`, scoped `404`,
disabled-parent creation `409` with `{"detail":"Evaluation dataset is disabled"}`,
and sanitized validation `422`. Missing Dataset/Case detail strings are
`Evaluation dataset not found` / `Evaluation case not found`. No provider
configuration or model error belongs to this API. DELETE and run/score/import
actions are absent; unsupported methods return `405`, absent paths `404`.

For these new routes only, request-validation errors use a fixed safe
`{"detail":"Invalid evaluation request"}` body. FastAPI's default validation
payload can echo sensitive `input` or exception context; use a route-local
validation handler that does not serialize either. Do not change validation
responses for existing routes. Failed reference checks or writes roll back;
unexpected persistence errors expose no SQL, parameters or exception text.

## 9. Migration 0011 (H1 approved; implemented)

Additive revision `0011`, `down_revision = "0010"`, creates only the
two tables, keys, checks and indexes in Section 5. Revisions `0001`-`0010`
remain byte-for-byte unchanged. No seed data, backfill, extension, trigger,
existing-table change or runtime migration is proposed.

Upgrade creates parent Dataset before Case. Downgrade drops Case then Dataset
and their owned objects; it destroys evaluation data and is authorized only
for isolated test fixtures after H1 approval, never as a runtime operation.
Migration tests cover `0010 -> 0011 -> 0010 -> 0011`, single head and ORM drift.
Approval must name the dedicated `enterprise_ai_workbench_test` database;
reuse the safety gate requiring `_test` suffix and a URL distinct from runtime.
No runtime database access is needed in Phase A.

## 10. Frontend recommendation (H3)

Recommend a minimal Evaluation Datasets administration view for Phase B.
Show its navigation only for Agent/System admins in the selected Workspace;
backend authorization remains authoritative. Provide Dataset list/create/edit/
status, nested Case list/create/detail/edit/status, and a category-specific
form for the typed expectation. No raw unrestricted JSON editor or Run button.
Optional resource selectors use existing authorized Workspace APIs; disabled
resources remain identifiable for negative fixtures. Display input as literal
text, never HTML or executable Markdown.

Include loading/empty/error states, pagination, duplicate-submit prevention,
content-entry guidance, and explicit disabled Dataset behavior. Clear Case
content on logout and Workspace switch; discard late responses from the old
Workspace; store no dataset content or tokens in browser persistent storage.
No charts, metric results, dashboard, bulk operations or evaluation animation.
API-only is a valid H3 alternative if the maintainer defers this UI; record that
decision and adjust acceptance/tests before implementing.

## 11. Threat model and sensitive-data policy (H5)

Unlike Feature 014 metadata-only execution logs, Case input and descriptive
text are intentional stored content. Classify them as Workspace-confidential
administrative test data. Use synthetic or redacted examples only: credentials,
tokens, JWTs, private keys, real employee identifiers, personal/regulated records,
production business results and verbatim production conversation replay are
prohibited by the authoring policy. References use UUIDs only, not copied content.

This is an author policy, not an automated guarantee that text is secret-free.
No DLP scanner, semantic sanitizer, per-case ACL or encryption system is added.
If that limitation is unacceptable, H5 must reject the proposal until a separate
approved data-handling design exists. No production-sensitive datasets should
be loaded under this MVP policy.

| Threat | Required mitigation / accepted limitation |
|---|---|
| Cross-Workspace or cross-dataset access | Scoped parent/child queries, generic 404, composite FKs; negative integration tests |
| Role spoofing or privilege escalation | Current backend Membership dependency; actor context is inert test data |
| Stored prompt injection, script or URL execution | No provider/executor/parser dispatch; literal rendering; no fetch of input URLs |
| Author supplied foreign reference hidden in JSON | Exact nested schemas with no identifier fields; scoped UUID columns only |
| Secret/PII copied into Cases | Synthetic/redacted authoring policy and UI guidance; automated detection explicitly absent |
| Input leaked by validation or exceptions | Route-local safe validation body; no input/SQL/exception logging; sentinel tests |
| Content appears in execution logs or tracing | No recorder added for this CRUD; Feature 014 operation allow-list unchanged; no telemetry integration |
| Excessive payload/list | Bounded text and fixed shallow schemas; max 100 rows; no arbitrary arrays, blobs or JSON trees; no storage quota yet |
| False claim of safety or correctness | Expectations are author declarations; no scoring, pass state or certified policy |
| Concurrent overwrites | Atomic validated merged PATCH; last committed write wins; no history/concurrency token |
| Mutation audit gap | Immutable creator and timestamps only; full change audit intentionally deferred |
| Content retained in DB/backups | Disabled is not deletion; no expiry/purge; retain until separately approved maintenance policy |

No application logs, errors, test snapshots, committed fixtures or third-party
systems may receive real Case content. Unit tests use synthetic sentinel text.
The database and its backups retain plaintext content under existing storage
controls; no new at-rest encryption is promised. Authorized detail responses
necessarily disclose that content to both administrative roles. No export or
external provider transfer is added. Any future evaluation runner must separately
approve its data egress and identity/Tool execution boundaries.

## 12. Dependency evaluation

This feature is ordinary product CRUD, not substantial AI infrastructure.

| Candidate | Fit | License / maintenance consideration | Deployment / integration cost | Decision |
|---|---|---|---|---|
| Existing FastAPI, SQLAlchemy, Pydantic and PostgreSQL | Typed CRUD and composite ownership constraints | Existing pinned stack; no new license or maintenance commitment | No new service/package; follows existing tested patterns | Use |
| Official model SDK | No inference requirement here | Already present; no new dependency | Any call would exceed scope | Do not invoke |
| External evaluation platforms (LangSmith/Langfuse) or telemetry (OpenTelemetry) | No concrete need for execution/metrics/traces | No package or service selected; license/activity audit deferred until a concrete need exists | Adds external data/policy boundaries or deployment work without CRUD benefit | Do not add |
| Evaluation frameworks (Ragas/DeepEval) | Scoring/execution is Feature 016 | No candidate selected or new license accepted | Unnecessary integration and dependency lifecycle | Do not add |
| Small external dataset component | No unmet requirement demonstrated | Would need a license/activity review if selected | Duplicates Workbench-owned RBAC and data management | Do not add |

Keep the existing benchmark harness separate; do not import its external corpus
or benchmark scoring functions into this feature. No commodity execution or
scoring infrastructure is reimplemented. Reassess candidates in Feature 016.

## 13. Acceptance criteria and test requirements

| ID | Acceptance criterion | Required evidence in Phase B |
|---|---|---|
| AC-01 | Dataset/Case schema and migration match Section 5 | PostgreSQL upgrade/downgrade, single-head and ORM drift tests; earlier migrations unchanged |
| AC-02 | Server owns identity/ownership/creator/timestamps/version | Create/PATCH contract tests; forbidden fields rejected |
| AC-03 | Every CRUD action enforces Section 7 matrix | Both resources, every verb, all four roles; inactive User/Workspace/Membership and absent Membership cases |
| AC-04 | No foreign or cross-dataset disclosure | List/detail/create/PATCH tests using missing/foreign IDs; identical 404 bodies; no partial writes |
| AC-05 | DB independently rejects foreign ownership edges | Direct invalid insert/update tests for Dataset, Agent, KB, Tool and creator Membership composite FKs |
| AC-06 | Four expectation schemas enforce exact contracts | Positive examples and exhaustive enum/null/type/extra-field/invalid-combination tests, including Tool key mismatch |
| AC-07 | PATCH validates merged state atomically | Ref changes with/without expectation replacement; rollback on mismatch; immutable type and parent; separate-connection concurrent PATCH and disable/create tests; lock timeout rollback |
| AC-08 | Disable/reactivate behavior matches Section 4 | Dataset creation gate; children retained; disabled Case editing and reading; no status cascade |
| AC-09 | Lists are bounded, filtered and ordered | Pagination/ties/invalid query tests; Case summaries omit input and expectations; explicit detail includes them |
| AC-10 | Content stays within approved storage/response boundary | Input/description sentinels absent from captured logs and errors, especially malformed-body 422; no ExecutionLog rows for CRUD |
| AC-11 | Dataset management never runs evaluations | Provider/answer/router/selector/adapter stubs fail if called; no Approval or Mock write; no new run/score route or result table |
| AC-12 | Minimal administration UI if H3 accepted | Role visibility, four forms, list/detail/status, literal hostile markup, empty/errors, Workspace/logout reset and late-response tests |
| AC-13 | Existing product behavior regresses cleanly | Full backend and frontend suites; existing authorization/Approval/Tool/log contracts unchanged |
| AC-14 | High-risk delivery reviewed | Approved H1-H5 recorded; implementation self-review and independent review before human merge |

Feature-specific tests first: proposed schema unit tests and Dataset/Case API,
persistence and migration PostgreSQL tests. Then full backend `pytest` using the
dedicated test database with no skipped required tests, Ruff, frontend API/UI
tests, `pnpm lint`, `pnpm build`, and `git diff --check`. No live model calls or
external integrations. Phase A checks documentation consistency, exact changed
paths, no migration/application edits, and diff whitespace; application suites
are not run for this documentation proposal. Feature 015 is not implementation-
complete until Phase B verification and review pass and a human merges the PR.

## 14. Explicit human decisions and approval gate

H1-H5 were explicitly approved by the maintainer on 2026-10-01 against the
Phase A baseline `a55f634`. The following recommendations were accepted. The
additional requirement to sanitize at the actual FastAPI validation boundary
and test all sensitive-output channels is implemented in `EvaluationRoute`.

| ID | Decision requiring approval | Recommendation |
|---|---|---|
| H1 | Migration and ownership constraints | Add only the two Section 5 tables in `0011` after `0010`, composite FKs and indexes; create/run migration only after approval, only on dedicated test DB, with isolated destructive downgrade tests |
| H2 | Authorization and content read access | `agent_admin` and `system_admin` may read/manage all Cases in their Workspace; employee/knowledge_admin denied; no adjacent privileges |
| H3 | Frontend delivery | Minimal typed administration UI in Section 10; API-only alternative requires a recorded scope adjustment |
| H4 | Product/API/expectation contract | Approve Sections 4-8: optional reusable Agent context, strict four-category schemas, citation presence only, synthetic permission context, immutable category, no hard delete/history, last-write-wins edits |
| H5 | Content sensitivity, disclosure and retention | Synthetic/redacted confidential test content only; plaintext DB/backups under existing controls; safe local 422 errors; no external transfer, automated DLP or purge; disabling retains content |

Explicit approval of H1-H5 authorizes only scoped Feature 015 Phase B,
including documentation synchronization, tests, migration file creation and
dedicated-test-database verification. It does not authorize runtime migrations,
production-sensitive content, destructive runtime operations, any change to
existing authentication/Approval policy, external platform integration,
Feature 016, or merging into `main`. Independent review remains required
before a human merge. Phase B stops at PR-ready implementation for independent review.

## 15. Out of scope

- Evaluation execution/runs, metrics, semantic scoring, automated scoring,
  LLM-as-a-judge and claims of deterministic Agent behavior.
- Bad-case management, Agent version comparison, dashboards and charts.
- External evaluation/telemetry platforms, MCP integration, conversation
  replay, live production data, background workers or scheduling.
- Dataset import/export, uploads, bulk writes, cloning, cross-Workspace sharing,
  arbitrary JSON input, executable assertions, exact citation ID expectations.
- Hard delete, retention/purge jobs, full mutation history, quotas, new roles,
  per-case ACL, database RLS, new dependencies or broad abstractions.
- Existing API deletion or behavior changes and edits to migrations 0001-0010.

## 16. Tracking and lifecycle

- Issue: [#34](https://github.com/SongHaiwen-creator/enterprise-ai-workbench/issues/34); remains open until feature delivery by human merge.
- PR: [#35](https://github.com/SongHaiwen-creator/enterprise-ai-workbench/pull/35),
  targeting `main`; updated for the implementation with `Closes #34`.
- Phase B status: implemented under H1-H5 approval; independent review pending.
- Feature 014 is merged/delivered; Milestone 4 remains in progress. Feature 015
  is the next unfinished feature, and Feature 016 is not started here.

## 17. Implementation and verification record

- `app/models/evaluation.py` and additive `0011` implement the two tables.
- `app/schemas/evaluation.py` validates all four typed expectation categories;
  `app/services/evaluation.py` owns scoped lookups, reference checks, locks,
  atomic merged PATCH and commits. Five-second lock timeout is sanitized.
- `app/api/routes/evaluation.py` defines eight authorized endpoints using an
  Evaluation-only `APIRoute` wrapper around FastAPI's generated handler. It
  catches pre-handler `RequestValidationError` and merged-state errors without
  logging or serializing their content; existing routers are unchanged.
- The frontend uses typed category forms and authorized resource selectors,
  literal input rendering, disable/reactivate, list pagination, safe errors,
  duplicate-write guards and complete content remount on Workspace/session change.
- Runtime database untouched; all PostgreSQL/migration verification uses
  `enterprise_ai_workbench_test`. Existing migrations are checked against the
  main baseline by Git object and SHA-256 comparisons.
- No new dependency, provider/execution path or Feature 016 code was added.
- Accepted MVP risks remain Section 11: plaintext confidential synthetic data,
  disabling retains content, no DLP/purge/history or optimistic concurrency.
- Verification: 153 Feature 015 backend tests (68 unit, 85 PostgreSQL integration);
  full backend `pytest -q -p no:cacheprovider`: 972 passed, no skips. Full frontend
  `pnpm test`: 9 API tests and 81 Vitest tests passed (including 23 Feature 015
  tests across forms, client contracts and role-gated navigation). Ruff,
  `pnpm lint`, `pnpm build`, and `git diff --check` passed. Existing Starlette
  and Alembic deprecation warnings remain. Independent review remains
  outstanding; no merge is authorized.
