# Feature 016 - Evaluation Run & Metrics

Status: Merged/delivered in PR #37 on 2026-10-03; Issue #36 closed
Milestone: 4 (in progress)
Baseline: `main` at `5c829ab45c9399c6dd6efcab3526f30004224cec`
Branch: `feat/evaluation-run-metrics`
Issue: [#36](https://github.com/SongHaiwen-creator/enterprise-ai-workbench/issues/36)
Risk: High - migration, authorization reuse, tenant isolation, confidential content,
provider data egress and prevention of Tool side effects.

## 1. Goal, scope and phase boundary

Allow same-Workspace Agent/System administrators to run active Evaluation Cases
against one current Agent, retain immutable structured results, and inspect
deterministic comparisons. This implements the next Milestone 4 capability after
Feature 015, consistent with PRODUCT_SPEC security, traceability, human control
and evaluation principles. ROADMAP's aspirational semantic metrics are not
supported by Feature 015 ground truth and are deferred, not silently implemented.

Phase A created the proposal at `3792b32c3d964420d6d8aa43240251e5889f256c`.
The user subsequently explicitly approved H1-H7 for scoped Phase B implementation
and dedicated test-database migration verification. This authorizes the
implementation below, without runtime/production migration, production PII or
secrets, Tool adapters during evaluation, Approval mutation, policy expansion,
new dependencies/infrastructure, Feature 017 or merge into main. Independent
review and human merge have since completed; runtime migration remains separate.

Section 2 records the historical Phase A baseline; it does not describe the
current implementation. PR [#37](https://github.com/SongHaiwen-creator/enterprise-ai-workbench/pull/37)
is the implementation review vehicle.

## 2. Read-only baseline verification (2026-10-02)

| Check | Evidence |
|---|---|
| Branch and HEAD | `main`, `5c829ab45c9399c6dd6efcab3526f30004224cec` |
| Cached and live remote | `git rev-parse main origin/main` and `git ls-remote origin refs/heads/main` all match baseline |
| Feature 015 delivered | PR [#35](https://github.com/SongHaiwen-creator/enterprise-ai-workbench/pull/35) MERGED at 2026-10-02 06:03:28 UTC (14:03:28 Asia/Shanghai); merge SHA equals baseline; Issue #34 CLOSED |
| Repository migration head | Alembic `ScriptDirectory.get_heads()` returns only `0011`; predecessor `0010` |
| Feature 015 implementation | `backend/app/{models,schemas,services}/evaluation.py`, `api/routes/evaluation.py`, migration `0011`, frontend Dataset/Case forms and typed client, unit/PostgreSQL/frontend tests exist |
| Feature 016 absent | No `EvaluationRun`, `evaluation_run`, run-metrics spec or revision `0012` in backend/frontend/docs before Phase A |
| Unrelated worktree | Modified `frontend/next-env.d.ts`; untracked `backups/`, `frontend/AGENTS.md`, `frontend/CLAUDE.md`; preserve and exclude from staging |
| Stale status | ROADMAP and Feature 015 spec still say PR #35 awaits merge; Architecture needs an explicit delivered Feature 015 status and Feature 016 proposal boundary |

Runtime database revision was not inspected. Repository migration head does not
guarantee any local/runtime database state. No runtime state will be recorded as
a Git-tracked guarantee. Initial sandbox GitHub access failed; authorized
credential/network access succeeded without changing repository state.

## 3. Inspected runtime boundaries and reuse

Sources: root AGENTS.md and all four source-of-truth documents; Feature
004, 009, 011-015 specs; current Dataset models/schemas/services/routes/UI;
authorization dependencies; Agent routing, RAG/answer, generation, retrieval,
Tool registry/selection/execution, Approval creation/execution authorization,
Execution Logs; relevant unit, PostgreSQL, migration and frontend tests.

| Existing boundary | Reuse / restriction |
|---|---|
| `api/routes/agents.py::_route_agent_request` | Contains orchestration and can enter `handle_tool_request`; never call directly from evaluation |
| `services/routing.py::RoutingProvider.route` | Reuse strict intent classification and current Agent scope |
| `services/answers.py::answer_question` | Reuse scoped retrieval, query embeddings, grounded generation and response validation; read-only search only, never indexing |
| `services/tools.py::handle_tool_request` | Currently mixes candidate selection, validation, read dispatch and Approval creation; extract a shared non-mutating plan before dispatch |
| `eligible_tools`, `_fresh_effective_tool`, registry | Reuse active, assigned, same-Workspace capability checks; Case references cannot augment candidates |
| `services/tool_selection.py` | Reuse strict proposal/decline and argument models; invalid provider output is ERROR |
| `services/approvals.py::create_pending_approval` | Commits and may expire/deduplicate rows; prohibited in evaluation. Extract only its read-only creation eligibility checks |
| `authorize_execution` / Approval decisions | Approval-specific and potentially locking; not part of evaluation or a simulated approval decision |
| `api/dependencies/authorization.py` | Extract narrow pure status/role checks consumed by real dependencies and inert permission fixtures; preserve policies and ordering |
| Feature 014 recorder | Rolls back the request Session before log commit; do not wrap runner in it or call recorded HTTP handlers. Run/Case rows are authoritative evaluation records |
| Feature 015 `EvaluationRoute` | Reuse sanitized validation/persistence boundary for new routes; no content-bearing exception logging |

Use existing SQLAlchemy, Pydantic, PostgreSQL, OpenAI SDK and pytest. No substantial
new AI infrastructure is required: existing SDK/protocols fit the required flow,
reuse the project's approved dependency/licenses and deployment, and have minimal
integration cost. External evaluation platforms/frameworks add deployment,
egress and ownership complexity without supporting additional ground truth;
no new library or custom replacement for routing/RAG is proposed.

## 4. Business rules and lifecycle (H2, H5)

1. One run selects one active same-Workspace Agent and every active Case in an
   active Dataset. No category filter, subset, disabled Case execution or silent
   skipping. Cases ordered by `(created_at, id)` ascending; 1-5 active Cases.
2. For non-permission Cases, optional Case `agent_id` must be null or equal the
   selected Agent. Mismatch rejects creation with sanitized 409. Permission
   references describe the target and do not override the selected Agent.
3. Required non-permission KB/Tool references must be scoped and exist. Disabled
   KB yields per-Case configuration ERROR; disabled/unassigned Tool is a valid
   negative selection situation, not granted access by its expectation.
4. Preflight authenticates the real caller and checks active User, Workspace,
   Membership and admin role; scopes Dataset/Agent/references; verifies active
   Dataset/Agent, Case count, expectation schema, and provider-egress consent.
   Preflight failure creates no run and makes no provider call.
5. In one short transaction lock the Workspace, Dataset and active Case rows in stable
   order (Workspace first, then Dataset, then Cases), copy Dataset/Case/config snapshots, and insert `running` Run plus
   ordered pending Run Cases. No provider call while locks are held. Serialize
   concurrent starts on the Workspace row, check for an existing running Run,
   and insert; at most one running Run per Workspace. Lock timeout: 5 seconds,
   sanitized 409. Dataset/Case edits after capture do not change this run.
6. Execute sequentially in the request process. Fresh real caller checks before
   each Case and before each provider phase; fresh capability/KB checks before
   use. Expectations are never sent to the model or used to force an intent.
   Commit each terminal Case in a short transaction. A pending Case has null
   result; terminal result is `passed`, `failed` or `error` and is write-once.
7. `running -> completed` when all Cases have terminal results, including
   ordinary individual errors. `completed` means finished, not all passed.
   `running -> failed` on run-level timeout, revocation, drift, interruption or
   unrecoverable orchestration failure. Mark all remaining pending Cases ERROR
   when persistence permits. Existing terminal Cases are never changed.
8. Counts reflect committed rows at each Case commit. Finalization under a Run
   row lock recomputes counts; terminal runs satisfy total = passed + failed +
   error. Counts are caches; metrics derive from Run Cases. Terminal status,
   snapshots and results cannot be changed through public APIs.
9. No retry/resume/cancel/update/delete API. A repeat POST creates a new Run.
   Duplicate frontend submit is blocked; network-ambiguous POST must not be
   automatically retried. List runs to recover a persisted run ID.
10. Crash/persistence outage can leave a running Run with pending rows. Store
    `deadline_at`; an authorized list/detail/start service may reconcile after
    deadline + 15 seconds under the Run lock, marking pending rows ERROR
    `interrupted` and Run `failed`. This is server-owned housekeeping, not a
    client update action or scheduler. Late executors must condition writes on
    still-running status, unexpired deadline and pending result; no overwrite.
    If DB remains unavailable, return fixed 500; do not fabricate durable results.

## 5. Category execution and normalized Actual Behavior (H3, H4)

All valid observed intents are recorded even on a route mismatch. Only continue
into a category's branch when its actual intent permits it; otherwise return a
normal observation with inapplicable fields null. No unexpected Tool branch
dispatches. No extra model call solely to satisfy an expected intent.

### Knowledge Q&A

Route real Case input with the selected Agent scope. On `knowledge_qa`, run the
existing read-only answer path using the Case's required KB. Store
`routing_intent`, `answer_status`, `citation_count`, and `knowledge_base_id`.
On another valid intent, answer status/count are null; scoring fails the routing
check. No answer, evidence text or citation excerpt is retained in results.
Provider-invalid citations remain ERROR under the existing response contract;
valid citation presence is observable, semantic correctness is not.

### Tool calling: plan only

Route then, only on `tool_request`, call shared planning. Normalized fields:
`routing_intent`, `tool_id`, `tool_key`, `would_outcome` (`executed`,
`approval_required`, `not_executed`), `approval_required`,
`non_execution_reason`, `execution_mode: dry_run`, `adapter_executed: false`.
For another intent, Tool fields are null (approval_required also null).

The existing expected `outcome: executed` means the normal product path would
be eligible to execute a read Tool; it never means execution happened in this
run. UI/API label it "Would execute (dry run)". For declines preserve exact
`no_available_tool`, `no_matching_tool`, `missing_required_arguments`. Decline
has null Tool ID/key and false approval_required, matching Feature 015.
Do not retain selected arguments, justification or business data.

Shared plan returns validated arguments only in process to the ordinary product
dispatcher. It checks actual caller eligibility, effective assignments, registry
risk/operation invariants, strict argument/business validation, and read-only
Approval-creation eligibility. Production dispatch consumes this plan and
retains its final current-state checks before adapter/Approval creation.
Evaluation consumes only its allow-listed normalized view, with no dispatcher,
adapter context, write executor or Approval service invocation. No read adapters
either; selection/outcome is sufficient for this feature. Avoid a public
`dry_run` flag on the ordinary execution route. Prove zero read/write adapter,
Approval create/expire/dedupe, Mock write and ordinary Execution Log calls.

### Permission boundary: shared policy evaluation

No routing/provider call and no use of `test_input`. Actual evaluator uses the
five Feature 015 operations only. Labels select strict immutable primitive
facts in a pure policy function; they never construct User/Membership ORM
objects, tokens, dependency overrides, sessions or authenticated principals.
The real run caller is separately authorized throughout.

Extract current Membership active/role predicates from authorization
dependencies into a small shared policy module. Both real dependencies and
evaluator call those predicates. Share scoped-resource-presence denial checks
with in-scope services/routes as needed; database loaders remain scoped to the
real Workspace and never accept fixture authority. Do not rewrite authentication,
Approval policies, global resource loading or all authorization surfaces.

For fixtures, User and route Workspace are stipulated active; target_context
describes a resource within that authorized route Workspace, not a foreign
Workspace URL. `absent`, `invited`, `disabled` membership => 403 first. Active
membership then requires Agent/System admin for configuration/Dataset reads;
all four active roles permit `agent_route` and `knowledge_answer`. Failed role
check => 403 before resource lookup. After those gates `other_workspace` and
`nonexistent` both provide `resource_present_in_scope=false` => identical 404,
with no lookup of a real foreign ID.

For same_workspace, an optional legal scoped reference supplies target existence
and lifecycle facts; if omitted, use a code-owned existing active target fixture
(Dataset read uses the run's Dataset). This makes omission deterministic without
creating resources. Configuration reads allow inactive targets; route/answer
target lifecycle checks preserve current 409 behavior. A valid allow is modeled
as `http_status: 200`, `result_category: allowed`, `access_denied: false`;
lifecycle conflict as 409 / conflict / true. Both are FAIL against Feature 015's
denial expectations, rather than evaluator ERROR. Policy/configuration execution
exceptions are ERROR. Store operation, labels, fixture source, resolved target
facts and policy version to distinguish simulation from real endpoint testing.

This measures shared authorization policy for the fixture facts, not production
identity enforcement or the whole HTTP stack. PostgreSQL endpoint parity tests
must prove that real loader/dependency ordering still matches every fixture
combination (including 200/403/404/409). No second independent role matrix in
the evaluator. A broader policy change requires separate approval.

### Refusal behavior

Route actual input. On `unsupported`, reuse the platform-standard unsupported
response builder, setting `response_category: unsupported_request` and
`safe_response: true` only for its fixed unsupported contract. On `knowledge_qa`
with a Case KB, use the read-only answer path; valid unsupported with no answer
and zero citations => `knowledge_unsupported`, safe_response true. An answered
response => `knowledge_answered`, safe_response false. Other normal intents,
or knowledge intent without a KB on an unsupported-request fixture, produce
null category and false safe_response; score FAIL without Tool dispatch. This
boolean checks a fixed structural refusal contract, never semantic safety.

## 6. Exact scoring and error rules (H4)

PASS iff every applicable required check equals its expectation. FAIL iff a
normal structured observation has any mismatch. All checks use strict values,
no case folding, fuzzy matching, numeric tolerance, weighted scores or judge.

| Category | Required checks |
|---|---|
| knowledge_qa | intent equal; answer_status equal; citation present means count > 0, none means count = 0; observed KB equals Case KB when answer branch ran |
| tool_calling | intent equal; would_outcome equals expected outcome; key equals (including null); selected ID equals Case tool_id when a Tool is expected; approval_required equal; non_execution_reason equal (including null) |
| permission_boundary | observed http_status, result_category and access_denied equal their three expectations; actor/context/operation labels are inputs, not scored predictions |
| refusal_behavior | intent equal; response_category equal; safe_response equals required true |

Store comparison checks as fixed names with boolean `matched`; a null actual
value is a mismatch against a required value. ERROR has no scored checks, even
if an intent was observed before execution failed. Never count a partial ERROR
as an Agent behavioral failure.

Fixed sanitized error categories: `provider_configuration`, `provider_failure`,
`provider_contract`, `input_budget`, `resource_configuration`,
`configuration_drift`, `authorization_revoked`, `case_timeout`, `run_timeout`,
`persistence_failure`, `interrupted`, `internal_error`. No exception text, SQL,
raw provider content or traceback is persisted or returned. Missing credentials,
invalid provider output/Tool arguments/citations, disabled required KB, lost
actual caller authority, DB failure and timeouts are ERROR. A valid selector
decline or structured unsupported outcome is normal and can PASS or FAIL.
An absent/foreign real reference cannot be interpreted as a synthetic permission
denial; reject preflight or classify concurrent loss as ERROR.

## 7. Deterministic metrics (H4)

Each rate returns `{matched, eligible, value}`, with value in [0,1] or null for
zero denominator. No rounding in persisted comparisons; UI formats percentages.
Only terminal non-ERROR observations enter behavioral denominators. Pending
rows never enter them. Show total, pending, passed, failed, error and
`evaluation_coverage=(passed+failed)/total` alongside every run summary so errors
cannot inflate an apparent quality claim.

| Metric | Numerator / denominator |
|---|---|
| overall_pass_rate | passed / (passed + failed) |
| category_pass_rate | category passed / category (passed + failed), all four categories shown |
| routing_match_rate | matched intent check / all non-error knowledge, Tool and refusal Cases |
| tool_selection_match_rate | both key and expected-ID checks match / all non-error Tool Cases, including expected null selection |
| tool_outcome_match_rate | would_outcome, approval_required and reason all match / all non-error Tool Cases |
| permission_boundary_pass_rate | permission passed / permission non-error Cases |
| refusal_behavior_pass_rate | refusal passed / refusal non-error Cases |
| citation_requirement_compliance | citation check matches / all non-error knowledge Cases; route mismatch/null count counts as mismatch |
| error_rate | error / terminal Cases; null if no terminal Cases |
| latency_ms | count, min, max, arithmetic mean, median over attempted Cases with measured latency, including ERROR; report attempted/error counts |

Latency is monotonic end-to-end Case evaluation time, including provider and
policy phases, excluding snapshot/finalization/persistence time. Unstarted cases
have null latency and attempted=false. Median is the middle sorted value or
mean of the two middle values. No p95 for this small sample. No separate metrics
table. Scoring is deterministic given observations; LLM routing/generation and
latency themselves are not deterministic. No semantic answer/citation accuracy,
retrieval relevance, task-completion claims or repeated-run stability score.

## 8. Historical snapshots and drift (H2)

Capture Case name, description, category, original IDs/reference columns,
schema_version, updated_at, full test_input and expected_behavior; Dataset
name/description/updated_at; selected Agent ID/name/status/updated_at and exact
system_prompt in a confidential snapshot. Never join current names/expectations
to present history. Raw prompt is necessary to interpret the evaluated scope,
but is returned only in authorized detail, never lists, logs or provider errors.

Allow-listed configuration snapshot: routing/selector/generation model IDs,
reasoning effort, prompt versions and instruction/schema hashes, token budgets,
retrieval limit, embedding model/dimensions, timeout limits, evaluator/scorer/
authorization policy versions, application build identifier (nullable if not
available), and canonical SHA-256 fingerprint. Exclude all environment dumps,
credentials, API URLs/headers, JWT and connection strings.

Capture Agent Tool assignments, Tool IDs/keys/status/risk/updated_at, registry
argument-schema/definition hashes, immediate flag, operation type and Approval
policy version/required roles/self-approval/TTL. For knowledge Cases capture
scoped KB name/status/updated_at and a sorted corpus manifest of eligible
Document IDs/versions and Chunk IDs/content hashes (no evidence text). Capture
retrieved/cited IDs/versions and evidence hashes per Case, never excerpts.
Instruction/schema hashes and build ID identify application contracts; exact
Agent prompt and Case snapshot preserve editable content.

Before each use, compare current execution-critical state with captured state;
changes in Agent scope/status, assignments/Tool policy, KB corpus or provider
configuration stop affected work as configuration_drift ERROR and fail the Run,
with remaining Cases ERROR. Recheck after provider response before accepting
results. Fresh actual authorization always takes precedence over snapshots.
Snapshots do not promise replay, historical Agent versions, or reproduce remote
model internals. Corpus manifests can be large; use existing current-MVP corpus
size, measure snapshot cost in Phase B, and reject with sanitized configuration
error if a manifest exceeds 1 MiB; do not silently truncate or claim exact drift
protection after truncation. Residual state changes after final checks are an
accepted read-only race, never permission to dispatch a Tool.

## 9. Proposed persistence and migration 0012 (H1)

Proposal only; create no migration during Phase A. `0012` follows `0011`, creates
exactly two new tables and required indexes/constraints, changes no existing
table and never rewrites `0001`-`0011`. All FKs ON DELETE RESTRICT.

### evaluation_runs

| Fields | Types / contract |
|---|---|
| id, workspace_id | UUID PK generated by DB; Workspace FK |
| dataset_id, agent_id | UUID; composite (id, workspace_id) FKs to Dataset/Agent |
| created_by | UUID; composite Membership (user_id, workspace_id) FK |
| status | VARCHAR(16): running / completed / failed |
| created_at, started_at, deadline_at | TIMESTAMPTZ required; DB timestamps, deadline = started + 120 seconds |
| completed_at | Nullable TIMESTAMPTZ; required only for terminal runs |
| total_cases, passed_cases, failed_cases, error_cases | SMALLINT; total 1-5, counts nonnegative and sum <= total; terminal sum = total |
| failure_category | Nullable VARCHAR(32), fixed run-level error enum; set iff failed |
| dataset_snapshot, agent_snapshot, config_snapshot | Required nonempty JSONB objects, strict service schemas |
| snapshot_version, scorer_version | SMALLINT = 1; VARCHAR(32) evaluation-scorer-v1 |
| configuration_sha256 | CHAR(64), canonical JSON hash |
| provider_egress_acknowledged | BOOLEAN required true when any non-permission Case; records explicit run consent |

Unique `(id, workspace_id)`; list index `(workspace_id, created_at, id)`;
Dataset list index `(workspace_id, dataset_id, created_at, id)`; Agent and creator
FK indexes. Partial unique `(workspace_id) WHERE status='running'` enforces
Workspace concurrency even across backend processes.

### evaluation_run_cases

| Fields | Types / contract |
|---|---|
| id, workspace_id, run_id, case_id | UUID; PK, Workspace FK, composite Run and Case FKs |
| ordinal | SMALLINT 1-5; unique (run_id, ordinal), unique (run_id, case_id) |
| case_type | VARCHAR(32), four existing categories |
| case_snapshot | Required JSONB object: Section 8 metadata, reference IDs and Case schema version |
| test_input_snapshot | TEXT, trimmed nonblank 1-2000 characters |
| expected_behavior_snapshot | Required nonempty JSONB object, original strict typed contract |
| context_snapshot | Required JSONB object with KB/corpus or permission facts, allow-listed per type |
| actual_behavior | Nullable JSONB; strict normalized per-category schema, no raw text/payload |
| comparison_checks | Nullable JSONB object; fixed booleans, only for passed/failed |
| result | Nullable VARCHAR(16): passed / failed / error; null pending only |
| attempted | BOOLEAN default false |
| latency_ms | Nullable INTEGER >= 0; set for attempted terminal Cases, null for unstarted ERROR |
| error_category | Nullable VARCHAR(32); required iff error |
| created_at, started_at, completed_at | TIMESTAMPTZ; creation required, attempt start nullable, completion iff terminal |

Unique `(id, workspace_id)`; Run ordered index `(workspace_id, run_id, ordinal)`;
Case FK index. Composite parent FKs forbid cross-Workspace attachment. JSON
reference IDs come only from scoped server capture, not client snapshot payload.
Add enum/object/bounds/result-error-check/timestamp/attempted-latency checks;
Pydantic/service enforces complete JSON contracts. Immutable snapshot columns
never appear in UPDATE statements; pending-to-terminal conditional updates only.
Terminal rows/runs have no public mutation path. No DB superuser immutability
claim; trusted database maintenance remains outside the API threat boundary.
Downgrade removes only these new objects, tested only in the dedicated test DB.

## 10. Authorization and Workspace isolation (H3)

| Real active Membership role | Create/list/read Run and Case results |
|---|---|
| agent_admin | Allowed in own Workspace |
| system_admin | Allowed in own Workspace |
| employee | 403 |
| knowledge_admin | 403 |

Missing/invalid token or inactive User: existing 401 behavior. Inactive Workspace
or missing/inactive Membership: existing 403 behavior; unknown route Workspace:
existing 404. Role gates precede resource lookup. For a caller authorized in
the route Workspace, missing and foreign Dataset/Agent/Run/Case/KB/Tool IDs have
identical scoped 404 responses and no existence disclosure. Preserve current
authentication/dependency semantics; this does not redesign global Workspace
discovery policy. Scope every query, nested parent and join; verify Run Case
belongs to both route Workspace and Run. Composite FKs defend all relationships.
Real permission is reloaded from DB, never from Case labels, run snapshots,
client roles or expected behavior. Authorized reads recheck current authority;
revocation prevents results being returned even if execution just completed.

## 11. Content and OpenAI data-egress policy (H6)

Case/prompt snapshots extend Feature 015's plaintext Workspace-confidential
storage and backup controls; disabling preserves history. Synthetic/redacted
content only. Never use credentials, secrets, production PII, real employee
records or verbatim production conversations in Case input, Agent prompt or
evaluation KB evidence. There is no automatic DLP, redaction or purge guarantee.

Require a run-level strict `provider_egress_acknowledged=true` for any
non-permission Case, plus explicit human approval of H6 before implementation.
The checkbox confirms the administrator has reviewed the Dataset, Agent scope
and evaluation KB content; it does not grant RBAC, Tool capability or provider
access. Use an approved synthetic/redacted evaluation KB; a Case marked
synthetic does not make a general production KB safe. Backend checks consent
before provider setup; UI states this boundary clearly.

Routing sends input and Agent scope with existing fixed instructions/schema.
Tool selection sends that same content plus eligible code-owned definitions/
argument schemas, never employee identity/data, roles, UUIDs, DB descriptions,
results or expectations. Knowledge branch sends query to embeddings and query
plus up to five retrieved evidence chunks to generation. Permission fixtures,
expectations, snapshots and scoring are local. Tool arguments are model output,
validated in memory and never executed or logged. Existing token budgets,
store=false where supported, zero retries, disabled parallel Tool calls and no
conversation/background state remain. Do not promise zero provider retention
from store=false; provider account/enterprise data controls remain an operator
responsibility. No new external destination or telemetry/evaluation service.

## 12. Bounded execution and timeout policy (H5)

Recommend maximum 5 active Cases, sequential, one in-flight Run per Workspace;
60 seconds per attempted Case and 120 seconds total execution budget. No
Redis/Celery/Kafka, worker, scheduler or background job. At most one routing,
one selector or query embedding plus one grounded generation per Case (three
provider calls maximum); permission Cases make zero. No hidden SDK retries.

Use monotonic remaining budgets at every phase; provider timeout is
min(configured timeout, 30 seconds, Case remaining, Run remaining). Inject
deadline-aware clients into existing protocols, not thread-based timeouts that
leave hidden calls running. Bound DB statements by remaining budget (at most
5 seconds) and use bounded connection/pool waits. On exhausted Case budget,
mark case_timeout and continue if Run time remains; exhausted Run budget fills
pending rows with run_timeout and terminal failed. Snapshot/preflight and
finalization are short bounded DB operations outside the 120-second execution
budget. UI/proxy client timeout should allow 150 seconds.

These are cooperative phase/IO budgets, not an OS-enforced hard wall-clock SLA:
SDK scheduling, CPU work or a process crash can overrun. No timeout thread,
uncancellable continuing executor or async background task is allowed. Deadline
reconciliation fences late DB writes, and conditional writes check deadline
before accepting a Case. If deployment cannot support this synchronous window,
reduce the limits or obtain a separate architecture approval; do not introduce
workers silently. Cross-Workspace load remains bounded by normal server request
capacity; no global enterprise quota is claimed.

## 13. API/data contracts

Base `/api/workspaces/{workspace_id}`; all routes require Section 10 authority.
Strict schemas forbid extra fields. Request body cannot set creator, lifecycle,
role, snapshots, Tool candidates, metrics or execution behavior.

| Method/path | Contract |
|---|---|
| POST `/evaluation-datasets/{dataset_id}/runs` | `{agent_id: UUID, provider_egress_acknowledged: bool}` (required); synchronous 201 Run summary, normally terminal; persistence required before success |
| GET `/evaluation-runs` | Optional dataset_id/agent_id/status filters; limit 1-100 default 50, offset >=0; newest `(created_at,id)` first; `{items,limit,offset}` |
| GET `/evaluation-runs/{run_id}` | Run detail, captured Dataset/Agent/config and deterministic metrics/category breakdown; no live name/config substitutions |
| GET `/evaluation-runs/{run_id}/cases` | `{items,limit,offset}`, ordinal ascending; optional result/category filters; summaries omit input, expectations and raw Agent prompt |
| GET `/evaluation-runs/{run_id}/cases/{run_case_id}` | Captured Case input/expectation/context, normalized actual, comparison checks, latency/attempted flag and sanitized error |

Run summary: id/workspace_id/dataset_id/agent_id/created_by, captured display
names, status/timestamps, counts, deadline and sanitized failure_category;
POST also returns metrics. Detail adds snapshots and metrics. Each metric uses
Section 7 envelopes; pending and zero-denominator results explicit. No partial
success without a durable Run ID. Individual provider/configuration failures
are per-Case ERROR under a 201 response, not a whole-request provider error.
Run infrastructure failure can return 201 with failed Run if safely persisted;
unavailable persistence returns fixed 500, possibly leaving an earlier durable
running Run discoverable later.

401/403/404 retain scoped authorization semantics. 409: inactive Dataset/Agent,
agent-reference mismatch, zero/over-limit active Cases, busy running Run or lock
timeout. 422: malformed/extra body/path/query values or missing required consent,
fixed `Invalid evaluation request`. 500: fixed `Evaluation persistence
unavailable`. No content-bearing validation details. Filter foreign IDs use
scoped lookup and same missing/foreign 404. No public metrics-write endpoint.

## 14. Frontend scope (H7)

Extend the existing Evaluation administration area, gated by current Membership.
Dataset detail provides Run Evaluation, active Agent selector, active Case count
and 5-Case limit, synthetic/redacted content/provider notice and required consent
when applicable. Fetch all active Case pages for an accurate count; backend
remains authoritative. Disable run action for disabled/empty/over-limit Dataset
and while submitting. Do not silently narrow the Dataset to fit the cap.

Run history, summary, passed/failed/error/pending counts, coverage, metric
numerators/denominators, four-category breakdown and latency summary. Per-Case
table shows captured name/category/result, attempted flag, latency and safe
error category. Detail shows Expected vs Actual, fixed failed-check names and
captured input. Render literal text, no HTML. Prominently label dry-run outcomes
and permission-policy simulation. Null rates display "Not evaluated", never 0%.
No semantic quality labels. Workspace/session remount clears all confidential
state; guard late responses and duplicate submits. An ambiguous timeout offers
history refresh, not automatic rerun. No charts, comparison screen or diagnosis.

## 15. Threat model and accepted limitations

| Threat | Required control / remaining limit |
|---|---|
| Cross-tenant ID guessing | Scoped reads/joins, role-first lookup, composite FKs, equal foreign/missing responses |
| Fixture privilege injection | Strict inert labels; pure shared predicates; no token/ORM identity construction or dispatch authority |
| Evaluation triggers writes | Plan-only call graph, no dispatcher, fail-on-call spies, DB counts unchanged for Approval/Mock/log rows |
| Prompt injection in Case/KB | Existing strict provider output, capability allowlist, local scoring; no expected behavior in prompt; no Tool dispatch even on unexpected intent |
| Revocation or drift during model wait | Fresh current-state checks before phases and after response; ERROR and fence remaining work; residual final-read race only read-only |
| Confidential content leaks | Synthetic/redacted KB/prompt/input consent; allow-listed snapshots/actual/errors; no logs/tracebacks/provider payloads; no automatic DLP |
| Misleading metrics | ERROR excluded from behavior rates with coverage/error counts; no semantic claims; explicit dry-run and policy simulation |
| Cost/resource exhaustion | 5 Cases, token/call/time caps, Workspace concurrency, no retries; server capacity still governs different Workspaces |
| Historical edits or late executor writes | Immutable copied definitions/config, conditional terminal updates, Run locking and expiry fencing |
| Crash/DB outage | Incremental durability, authorized stale reconciliation; no background recovery guarantee during outage |
| Stored XSS | Literal escaped rendering; no content interpretation or executable assertions |

## 16. Acceptance criteria and test requirements

1. All four existing categories run under exact Section 5 contracts and strict
   Section 6 comparisons; repeat run creates independent immutable history.
2. Active-only deterministic Case capture, reference mismatch handling,
   pagination, edited/disabled source history and current Agent selection work.
3. Tool planning parity with normal product path, no adapters (read or write),
   Approval mutation, Mock writes or ordinary log recorder under any category,
   including malicious selector, unexpected intent, missing arguments and drift.
4. Pure permission fixtures cannot obtain runtime authority. Exhaustive matrix
   over four roles, four Membership statuses, three contexts and five operations
   verifies ordering and denied/allowed/lifecycle outcomes. Real PostgreSQL HTTP
   parity tests independently verify shared predicate integration and loaders;
   run permission scoring itself never invokes those HTTP routes.
5. All required errors sanitized. Provider configuration, malformed proposals,
   invalid citations, timeouts, revocation, persistence failures, unexpected
   internal exceptions remain ERROR; normal unsupported/decline remains scorable.
6. Exact metric fractions and latency summaries for mixed results, route
   mismatches, expected-null Tools, partial observations, all-error/all-pending
   runs and empty categories. ERROR contributes to no behavioral denominator.
7. Snapshot fingerprinting/corpus manifests preserve history, detect changes,
   reject oversize capture and never serialize secrets or unapproved content.
8. Role/status and tenant isolation for every route/filter/detail/nested parent,
   real caller revocation during waits, same missing/foreign responses, and
   sanitized validation/persistence errors containing secret sentinels.
9. Database migration `0011 -> 0012`, downgrade/re-upgrade, single head, schema
   drift, enum/result/count/timestamp checks, FK negative tests, unique running
   concurrency, and no edits to `0001`-`0011`. Dedicated
   `enterprise_ai_workbench_test` only; no runtime migration.
10. Clock-controlled Case/Run deadlines, remaining provider/DB budgets,
    concurrency across Sessions, source edits during capture, partial commit
    failure, crash/stale reconciliation and late executor terminal fencing.
11. Captured provider request tests prove allowed inputs only, no expectation/
    identity/role/secret/Tool results, no extra calls or retries, consent before
    provider initialization. Automated tests fake providers; no live OpenAI.
12. Frontend category/results/details, accurate active count, Agent selection,
    consent, dry-run/policy labels, role gates, duplicate submit, timeout history
    recovery, nullable metrics, literal rendering, pagination and stale response
    guards. Existing Assistant, Dataset/Case, Approvals and logs regress unchanged.

Phase B verification: targeted unit/PostgreSQL/frontend tests first; full backend
pytest including PostgreSQL with no required skips; Ruff; frontend tests,
`pnpm lint`, `pnpm build`; migration checks; `git diff --check`; self-review and
independent security/isolation/migration review before human merge. Phase A
verification is read-only baseline evidence, documentation review and diff checks;
application suites are not run and no implementation completion is claimed.

## 17. Explicit human decisions before Phase B

| Gate | Proposed decision requiring approval |
|---|---|
| H1 - schema | Create additive migration 0012 and exactly the two Section 9 tables/constraints; dedicated-test-DB upgrade/downgrade verification only |
| H2 - lifecycle/history | Approve snapshots including confidential Agent prompt and bounded corpus manifest, pending-to-terminal immutability, completed/failed semantics, drift detection and authorized stale reconciliation |
| H3 - security architecture | Approve narrow shared Tool plan/Approval creation eligibility extraction and pure authorization predicate reuse; preserve actual policies and APIs; fixtures never become identities; require independent review |
| H4 - scoring | Approve exact per-category checks, would-execute mapping, modeled policy observations and Section 7 denominators; no semantic/safety judge or task-completion claim |
| H5 - execution | Approve 1-5 Cases, sequential synchronous execution, 60-second Case/120-second Run budgets, 30-second per-call cap and one running Run per Workspace, with documented cooperative timeout limits |
| H6 - confidential content/egress | Approve plaintext historical Case/prompt storage and OpenAI routing/selector/query/evidence transfer only for reviewed synthetic/redacted input, Agent prompt and evaluation KB; run consent required; no DLP/zero-retention promise |
| H7 - API/UI | Approve five routes and minimal Evaluation Run administration UI, same Agent/System admin policy, safe errors and dry-run/simulation disclosure; no new dependencies/workers/frameworks |

AGENTS.md's High-Risk Changes gate requires explicit approval before migrations,
security-sensitive authorization reuse and architecture changes. The user's
Phase-A-only request also explicitly requires approval of the data-egress
boundary and waiting before Phase B. Approval of H1-H7 must refer to this
proposal revision/commit and authorize only scoped implementation and dedicated
test database verification. It never authorizes runtime DB migration, production
PII, real/read Tool adapter execution during evaluation, Approval creation,
policy expansion, new infrastructure, the next feature or merge into main.

## 18. Out of scope and tracking

No LLM-as-a-Judge, semantic answer/citation/retrieval scoring, multilingual
benchmarking, repeated-run stability, Bad Case Management, Agent Version
Comparison, automatic Agent/prompt changes, MCP, external evaluation framework,
real Tool writes, Approval creation, read adapters, scheduling/workers,
retention/purge, dataset import/export, generic executable assertions or APIs
removed. Existing offline EnterpriseRAG benchmark remains separate; its corpus
ground truth does not supply ground truth for arbitrary Feature 015 Cases.

Issue #36 closed after the verified implementation was independently reviewed
and human-merged in PR #37. Feature 016 is delivered. Subsequent features start
from the latest main in a new development thread under their own approved scope.


## 19. Phase B implementation and verification record

H1-H7 approval applies to proposal commit
`3792b32c3d964420d6d8aa43240251e5889f256c`; no additional high-risk scope
was introduced. Revision `0012` implements only the two approved tables.
The five APIs and administration UI use captured history, exact comparisons
and derived metrics. Tool evaluation uses read-only planning and permission
evaluation uses inert policy facts; neither executes adapters nor mutates
Approvals. Existing request authorization remains authoritative.

Measured attempts are persisted atomically with their terminal result.
`attempted=false` means no measured attempt was durably recorded; after a
process crash it does not prove that no provider request occurred. Stale
pending Cases become interrupted ERROR with null latency, avoiding invented
wall-clock latency. Terminal writes are fenced against reconciliation, and
latency excludes result-persistence waits.

Automated provider tests use fakes; no live OpenAI request is verification
evidence. Migration upgrade, downgrade/re-upgrade, schema parity, constraint
negatives and concurrent Sessions run only against the safety-checked dedicated
`enterprise_ai_workbench_test` database. Runtime/production migration remains
unexecuted and unauthorized. Verification results and independent review are
recorded below.


Verification on 2026-10-03:

- Feature 016 unit/PostgreSQL selection: **543 passed**, 608 unrelated tests
  deselected; no skips. Full backend `pytest backend/tests -q
  -p no:cacheprovider -x`: **1520 passed**, no skips.
- Backend Ruff: passed. Frontend `pnpm test`: **9 API + 89 UI tests passed**;
  `pnpm lint` and production `pnpm build`: passed.
- Migration `0011 -> 0012`, downgrade/re-upgrade, single head, metadata drift,
  prior migration byte comparisons, composite foreign keys, nullable-state
  constraints and real independent-Session concurrency: passed in the dedicated
  test database. No runtime migration or live OpenAI verification was performed.
- Self-review and `git diff --check`: passed. Existing unrelated local files
  are excluded from the implementation commit.
- Independent review completed with no remaining blocking findings after fixes
  for SQL NULL consistency, measured latency persistence, final GET/POST
  authorization checks and crash-attempt labeling; regression tests cover the
  fixes. Review was static code/test inspection, not live-provider validation.

Initial rerun encountered unavailable local PostgreSQL; after Docker/service
startup it passed. Full-suite ordering also exposed global-count test
assumptions; assertions now scope their own Workspace and the full rerun passed.
Existing Starlette/Alembic deprecation warnings remain (68 in the full suite).
Cooperative deadlines, plaintext confidential history and manually reviewed
synthetic/redacted provider input retain the limits described above. Issue #36
was closed when PR #37 merged into main on 2026-10-03. Feature 016 is delivered;
this repository state does not imply migration of any runtime database.
