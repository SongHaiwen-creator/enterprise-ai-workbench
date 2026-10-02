# Feature 014 - Execution Logs

Status: Implemented - merged/delivered into main (PR #33, 2026-10-01); Issue #32 closed; Phase A specification (revision 2, H1-H4) approved
Milestone: 4
Baseline: `main` at `ec55dd2` (Features 001-013 merged; Alembic head `0009`)
Risk class: High (`AGENTS.md` High-Risk Changes: new migration; security-sensitive
data handling; Workspace isolation of a new Workspace-owned table; new
role-gated read API)
Issue: #32 (https://github.com/SongHaiwen-creator/enterprise-ai-workbench/issues/32)

## 1. Goal

Make the Workbench's AI operations traceable. Every handled Agent request,
grounded knowledge answer, and human Approval decision produces one
Workspace-owned, append-only execution log record that says who did what,
through which Agent and Tool, what the outcome was, how long it took, and why
it failed, without storing the content of the request, the answer, Tool
arguments, Tool results, or any personal data beyond internal IDs.

```text
Authenticated, Workspace-authorized request
-> Feature 011 routing / Feature 009 answer / Feature 012 Tool / Feature 013 decision
   (behavior unchanged)
-> business transaction committed by its owner, or rolled back
-> Feature 014 recorder: classify outcome, measure latency,
   build allow-listed record
-> insert one execution_logs row in its own short transaction
   (best-effort: never changes the response)
-> agent_admin / system_admin read the Workspace's logs (API + minimal UI)
```

Feature 014 must prove:

1. Every request to an in-scope route whose handler body is entered yields
   exactly one log record, on success and on every failure raised inside the
   handler; a request rejected before the handler yields none (Section 6.1).
2. A log record never contains request text, prompts, answers, citations,
   Tool arguments or results, justifications, decision notes, names, emails,
   provider payloads, exception messages, or stack traces.
3. Logs are Workspace-isolated in storage (composite foreign keys) and in
   reads (only same-Workspace `agent_admin` and `system_admin`).
4. Recording a log never changes, delays past a bound, or breaks the business
   outcome or its transaction ownership as defined by Features 011-013.

It also closes the known gap recorded by Feature 013 Section 22.2: read-only
Tool executions are currently unlogged.

## 2. Phase A Status

Phase A is documentation only. No migration, model, service, route, frontend,
or test code is part of the Phase A change.

The human maintainer approved the Section 23 gate and decided H1-H4 as
recommended (Section 24). Migration `0010` is authorized for creation and for
execution against the dedicated test database `enterprise_ai_workbench_test`
only.

Revision 2 applies the two clarifications required with that approval:

- **Recording boundary.** The "exactly one record" invariant is defined by
  handler entry, not by "passed Workspace authorization" (Section 6.1,
  AC-002). The `knowledge_answer` embedding provider stays a FastAPI
  dependency, so its configuration `503` is a pre-handler rejection and is
  not recorded; existing tests and the external `503` are unchanged.
- **AC-005 wording.** There is no Approval-creation operation. Creation or
  deduplication is the `agent_route` outcome `tool_approval_required`;
  `approval_decision` and `approval_cancel` are separate operations (AC-005).

## 3. Scope

In scope (Phase B, subject to Section 23):

- Additive migration `0010` creating `execution_logs` (Section 14).
- A recorder used by the in-scope routes (Section 6) that classifies the
  outcome, measures latency, validates an allow-listed record, and writes it
  after the business transaction is finished (Section 10).
- Fixed, versioned enumerations for operation, outcome, and error category
  (Section 9).
- Read-only list and detail API for same-Workspace `agent_admin` and
  `system_admin` (Sections 11-13).
- A minimal read-only Execution Logs view in the frontend (Section 15, H3).
- Documentation updates to `DATABASE.md` Section 14, `ARCHITECTURE.md`, and
  `ROADMAP.md` in Phase B.

Not in scope: see Section 22.

## 4. Existing Foundation

Verified against `main` at `ec55dd2`.

- **No log infrastructure exists.** There is no `execution_logs` table, no
  model, and the backend emits no application log lines (Feature 013
  Section 22.3). `DATABASE.md` Section 14 is a planning sketch only.
- **Request session.** `get_db_session` yields one `Session` per request
  (`autoflush=False`, `expire_on_commit=False`) and rolls back on an
  unhandled exception. Isolation is PostgreSQL `READ COMMITTED`.
- **Transaction ownership (Features 012-013).** Services commit internally.
  `handle_tool_request` is read-only for read-only Tools; Approval creation
  commits inside `create_pending_approval`; the Approval decision service
  commits every state change (including `invalidated`, `expired`, and
  `approved/failed`) before raising `409`/`502` (`ApprovalOutcomeError`).
- **Row locks.** The decision service holds `SELECT ... FOR UPDATE` on the
  Approval row for the whole decision transaction, with
  `SET LOCAL lock_timeout = '5s'`.
- **Composite keys available.** `uq_agents_id_workspace_id`,
  `uq_tools_id_workspace_id`, `uq_approvals_id_workspace_id`,
  `uq_knowledge_bases_id_workspace_id`, and
  `uq_memberships_user_workspace` already exist, so `0010` can enforce
  same-Workspace references without changing any existing table.
- **No hard deletes.** Users, Memberships, Agents, Tools, Knowledge Bases,
  and Approvals are never deleted through the application (only
  `agent_tools` edges are), so `ON DELETE RESTRICT` references are safe.
- **Party references.** Feature 013 exposes people and Agents as
  `{id, name}` (`ApprovalPartyReference`) and Tools as
  `{tool_key, name}` (`PublicToolReference`); Feature 014 reuses these
  shapes.

### 4.1 Documentation discrepancies resolved by this spec

`DATABASE.md` Section 14 sketches `event_type` values
`rag / tool_call / approval / error`, free-form `input_data` / `output_data`
JSONB "summaries", and `status` values `success / failed`. This spec replaces
them because:

- `error` is a status, not an event type; one handled request is one record
  whose `status` is `succeeded` or `failed`.
- Free-form input/output summaries are the most likely path for request text,
  arguments, and personal data to leak into logs. They are replaced by
  explicit, typed columns and one allow-listed `details` object
  (Section 8).
- Status values follow the existing `succeeded` / `failed` vocabulary of
  Feature 013 execution status.

`DATABASE.md` Section 14 is rewritten in Phase B to match Section 14 of this
spec.

## 5. Terminology

| Term | Meaning |
|---|---|
| Operation | One handled API request of an in-scope kind (Section 6) |
| Execution log record | One `execution_logs` row describing one operation |
| Recorder | The backend component that classifies an operation and writes its record |
| Outcome | Product-level result of the operation, from a fixed enum (Section 9.1) |
| Error category | Sanitized failure class, from a fixed enum (Section 9.2) |
| Business transaction | The request-session transaction in which Features 009-013 read and commit |
| Log transaction | The short transaction in which the recorder inserts the record |

## 6. Recorded Operations (H4)

| Operation | Route |
|---|---|
| `agent_route` | `POST /api/workspaces/{workspace_id}/agents/{agent_id}/route` |
| `knowledge_answer` | `POST /api/workspaces/{workspace_id}/knowledge-bases/{knowledge_base_id}/answer` |
| `approval_decision` | `POST /api/workspaces/{workspace_id}/approvals/{approval_id}/decision` |
| `approval_cancel` | `POST /api/workspaces/{workspace_id}/approvals/{approval_id}/cancel` |

Approval creation is not a separate operation: creating or deduplicating a
pending Approval is the `agent_route` outcome `tool_approval_required`.

### 6.1 Recording boundary

A request to an in-scope route is recorded **if and only if FastAPI enters
the route handler body**, that is, after every declared dependency and
request validation has succeeded. From handler entry on, exactly one record
is written for the request, whether the handler returns or raises (subject
only to the best-effort write policy, Section 10.3).

Because FastAPI resolves dependencies and validates the request before the
handler runs, the following produce **no** record:

| Pre-handler rejection | Typical status |
|---|---|
| Missing or invalid bearer token (`CurrentUser`) | `401` |
| Workspace missing, disabled, or caller without active Membership (`ActiveWorkspaceMembership`) | `404` / `403` |
| Path, query, or body validation | `422` |
| `knowledge_answer` embedding configuration error (`ConfiguredEmbeddingProvider`) | `503` |

Consequences:

- Every record has a real, same-Workspace user whose Membership was active at
  handler entry.
- The `knowledge_answer` embedding provider remains a FastAPI dependency.
  Feature 014 does not move it into the handler, so the existing external
  `503` and the existing `get_embedding_provider` test overrides are
  unchanged. The `agent_route` already creates its embedding provider inside
  the handler, so the same condition there is recorded as
  `provider_unavailable`.
- Generation, routing, and selector providers are lazily configured and fail
  inside the handler, so their configuration errors are recorded on every
  in-scope route.
- Adding a new dependency to an in-scope route changes this boundary and
  must update this table.
- Security audit of pre-handler rejections is out of scope (Section 22).

### 6.2 Other rules

- Not recorded: retrieval search, document indexing, all configuration CRUD
  (Workspaces, Members, Knowledge Bases, Documents, Agents, Tools,
  assignments), Approval list/read, and execution log reads.
- One handled request produces at most one record. A client retry is a new
  request and a new record.

## 7. Business Rules

- **BR-01 Append-only.** The application never updates or deletes a record.
  There is no create, update, or delete API. All foreign keys use
  `ON DELETE RESTRICT`.
- **BR-02 Workspace-owned.** Every record has `workspace_id` equal to the
  route Workspace. Every referenced Agent, Tool, Approval, Knowledge Base,
  and user Membership belongs to the same Workspace, enforced by composite
  foreign keys.
- **BR-03 Reference only resolved objects.** A reference column is set only
  when the object was resolved inside the route Workspace during the
  operation (for example, `agent_id` is null when the Agent was not found).
  A client-supplied ID that did not resolve is never stored.
- **BR-04 Status.** `status = succeeded` if and only if the response is 2xx;
  otherwise `failed`. A product outcome such as `unsupported_request`,
  `tool_not_executed`, or `knowledge_unsupported` is a success of the
  operation; judging whether it was *correct* belongs to evaluation
  (Milestone 4, later feature).
- **BR-05 Error category.** `error_category` is set if and only if
  `status = failed`, and is chosen by exception type and known constant
  (Section 9.2), never by copying an exception message.
- **BR-06 Outcome on failure.** `outcome` may be set on a failed operation
  when the business state changed before the error (for example,
  `invalidated`, `expired`, `approved_execution_failed`).
- **BR-07 Latency.** `latency_ms` is the wall-clock duration of the route
  handler body, measured with a monotonic clock, from handler entry to
  outcome determination (before the log transaction), floored to whole
  milliseconds. It excludes authentication dependencies and the log write.
- **BR-08 Data minimization.** Only the fields in Section 8 are stored.
- **BR-09 Best-effort recording (H2).** A failure to record never changes the
  HTTP status, body, or committed business state (Section 10).
- **BR-10 Business behavior unchanged.** Responses, status codes, error
  bodies, commit points, and locks of Features 009-013 are unchanged.
- **BR-11 Historical accuracy.** A record keeps its references after the
  user's Membership, the Agent, or the Tool is later disabled; reads show
  current display names for those references.

## 8. Data Minimization

### 8.1 Stored

| Field | Source |
|---|---|
| `workspace_id` | route path, after authorization |
| `user_id` | authenticated user (`CurrentUser`) |
| `operation` | Section 6 |
| `routing_intent` | Feature 011 intent enum, `agent_route` only |
| `status`, `outcome`, `error_category`, `http_status` | Section 9 |
| `latency_ms` | BR-07 |
| `agent_id` | resolved Agent (route path, or the Approval's Agent) |
| `tool_id`, `tool_key` | resolved Tool row (never the selector's raw proposal) |
| `approval_id` | created or decided Approval |
| `knowledge_base_id` | resolved Knowledge Base |
| `details` | allow-listed object (Section 8.2) |
| `created_at` | database time |

### 8.2 `details` allow-list

`details` is a JSON object validated by a strict schema
(`extra = "forbid"`, strict types). Unknown keys make the record invalid and
it is not written (BR-09). All keys are optional.

| Key | Type | Allowed on | Meaning |
|---|---|---|---|
| `tool_not_executed_reason` | enum: `no_available_tool`, `no_matching_tool`, `missing_required_arguments` | `agent_route` | Feature 012 not-executed reason |
| `citation_count` | integer 0-100 | `agent_route`, `knowledge_answer` | number of citations returned |
| `generation_model` | string matching `^[A-Za-z0-9._:-]{1,64}$` | `agent_route`, `knowledge_answer` | server-configured model identifier |
| `prompt_version` | string matching `^[A-Za-z0-9._:-]{1,64}$` | `agent_route`, `knowledge_answer` | server-configured prompt version |
| `input_tokens`, `output_tokens`, `total_tokens` | integer >= 0 or null | `agent_route`, `knowledge_answer` | provider usage, when reported |
| `decision` | enum: `approve`, `reject` | `approval_decision` | requested decision |

String values come only from server configuration, never from request or
provider content.

### 8.3 Never stored

Request text or question; Agent system prompts; routing or selector
prompts; answers, citations, chunk text, document or file names; Tool
arguments (including `business_justification`), validated arguments, or
Tool results; Approval snapshots or digests; decision notes; user names,
emails, or any profile field; access tokens, passwords, API keys; provider
request or response payloads; exception messages, SQL, or stack traces;
client IP, user agent, or headers.

## 9. Outcome and Error Classification

### 9.1 Outcomes

| Outcome | Operation | When |
|---|---|---|
| `knowledge_answered` | `agent_route`, `knowledge_answer` | answer status `answered` |
| `knowledge_unsupported` | `agent_route`, `knowledge_answer` | answer status `unsupported` (insufficient grounded context) |
| `tool_executed` | `agent_route` | read-only Tool executed |
| `tool_approval_required` | `agent_route` | pending Approval created or deduplicated |
| `tool_not_executed` | `agent_route` | Feature 012 not-executed outcome |
| `unsupported_request` | `agent_route` | Feature 011 `unsupported` intent |
| `approved_execution_succeeded` | `approval_decision` | `approved/succeeded` |
| `approved_execution_failed` | `approval_decision` | `approved/failed` (`502`) |
| `rejected` | `approval_decision` | `rejected` |
| `invalidated` | `approval_decision` | `invalidated` committed (`409`) |
| `expired` | `approval_decision`, `approval_cancel` | lazy expiry committed (`409`) |
| `cancelled` | `approval_cancel` | `cancelled` |

`outcome` is null when the operation failed before any outcome existed. For
Approval operations the outcome is read from the committed Approval state
after the business transaction, so an idempotent `200` replay of an earlier
decision (Feature 013 Section 17.2) records that Approval's current outcome,
for example `approved_execution_failed` with `status = succeeded`.

### 9.2 Error categories

| Error category | HTTP | Condition (existing behavior) |
|---|---|---|
| `agent_not_found` | 404 | Agent missing or in another Workspace |
| `agent_inactive` | 409 | Agent not `active` |
| `knowledge_base_required` | 422 | knowledge intent without `knowledge_base_id` |
| `knowledge_base_not_found` | 404 | Knowledge Base missing or in another Workspace |
| `knowledge_base_inactive` | 409 | Knowledge Base not `active` |
| `input_too_large` | 422 | routing, selection, or generation input limit |
| `provider_unavailable` | 503 | routing, selector, embedding, or generation configuration error |
| `provider_error` | 502 | routing, selector, embedding, or generation provider failure |
| `tool_configuration_error` | 503 | Tool registry or Approval configuration mismatch |
| `tool_unavailable` | 409 | selected Tool no longer active or assigned; capability unavailable at Approval creation |
| `tool_execution_failed` | 502 | read-only Tool adapter or result validation failure |
| `access_denied` | 403 | fresh caller check or Approval action not permitted |
| `approval_not_found` | 404 | Approval missing, foreign, or invisible |
| `approval_not_pending` | 409 | Approval already decided |
| `approval_expired` | 409 | Approval expired |
| `approval_invalidated` | 409 | drift or requester/capability loss during approve |
| `approval_busy` | 409 | Approval lock timeout |
| `approval_execution_failed` | 502 | Mock adapter failure after approval |
| `internal_error` | 500 or the raised status | any other exception |

Classification is by exception type plus the existing module constants that
already select the HTTP status. The recorder never reads `str(exc)` into a
record. An unmapped exception is `internal_error` and is re-raised unchanged.

## 10. Write Path and Transaction Semantics

### 10.1 Ordering

1. The route handler runs its existing logic unchanged.
2. The outcome (response or exception) is determined and `latency_ms` is
   taken.
3. The recorder ends the business transaction: it rolls back whatever the
   handler left uncommitted. Business services own their commits
   (Section 4); anything they did not commit is not part of the outcome, so
   rolling back is equivalent to what `get_db_session` does on error and is
   a no-op for work already committed. Phase B mechanism: Section 10.4.
4. The recorder inserts the record on the same request session, with
   `SET LOCAL lock_timeout = '250ms'`, and commits. That transaction contains
   no business writes (step 3).
5. The route returns the already-built response, or re-raises the original
   exception unchanged.

Because the response model is built before step 3 and the session uses
`expire_on_commit=False`, no ORM attribute is read after the rollback.

### 10.2 Why after, and why the same session

- **No self-wait.** The insert's foreign-key checks take `FOR KEY SHARE` on
  referenced rows. Inside an open decision transaction the request itself
  holds `FOR UPDATE` on the Approval row; a second connection would wait on
  its own request. Writing after the business transaction avoids this.
- **No accidental commits.** Rolling back first guarantees the log commit can
  never commit a business write that its owning service did not commit.
- **No extra connection.** Using the request session keeps pool usage and
  test isolation as they are today.

### 10.4 Phase B mechanism for step 3

At handler exit, before building the record or issuing any log SQL, the
recorder unconditionally calls `session.rollback()`. This discards every
uncommitted request-session change, including pending or flushed ORM state,
Core/textual DML, connection-level DML, and an aborted transaction after a
database error. Work that a Feature 009-013 service already committed is not
affected. The recorder then starts a new short transaction to resolve safe
references, insert the log, and commit it.

No SAVEPOINT or Session-event write tracker is used as a safety boundary:
`Session.begin_nested()` flushes pending state before the savepoint, and DML
tracking cannot reliably observe textual, connection-level, or nested
transaction activity. Feature tests use committed setup data or a
production-like request Session; fixture preservation must never weaken the
production transaction boundary.

### 10.3 Failure policy (H2)

Recording is best-effort. If validation, the insert, the lock timeout, or
the commit fails, the recorder rolls back the log transaction, emits one
fixed warning line containing only the event name
`execution_log_write_failed`, the Workspace ID, and the operation, and
returns normally. The HTTP status, body, and all committed business state
are unchanged. The authoritative audit record for write-sensitive actions
remains the Feature 013 Approval row; execution logs are operational
traceability, not the system of record.

The log transaction uses a deliberately short `250ms` lock timeout. A
business Approval operation may already have consumed its `5s` lock timeout;
the recorder must not add another comparable wait. A log timeout simply drops
the record under this best-effort policy.

Consequence: a record can be missing if the database fails between the
business commit and the log commit. This is accepted for Feature 014 and
must be revisited before a real enterprise write is connected.

## 11. Authorization and Workspace Isolation (H1)

| Caller (active Membership in an active Workspace) | List | Read one |
|---|---|---|
| `system_admin` | all Workspace records | yes |
| `agent_admin` | all Workspace records | yes |
| `knowledge_admin` | `403` | `403` |
| `employee` | `403` | `403` |
| no active Membership, disabled Workspace | existing `403`/`404` | existing `403`/`404` |

- Authorization reuses the existing `require_agent_administrator`
  dependency (`agent_admin` or `system_admin`); no new role or policy.
- Every read filters by the route `workspace_id`. A record ID that is
  missing or belongs to another Workspace returns the same `404`
  (`"Execution log not found"`).
- Filters on `agent_id` or `user_id` from another Workspace simply match
  nothing.
- Log reads are not themselves logged.
- Hiding the frontend view is not authorization; the backend enforces.

## 12. API Contract

### 12.1 List

`GET /api/workspaces/{workspace_id}/execution-logs`

| Query parameter | Type | Default |
|---|---|---|
| `operation` | operation enum | none |
| `status` | `succeeded` / `failed` | none |
| `agent_id` | UUID | none |
| `user_id` | UUID | none |
| `tool_key` | registered Tool key | none |
| `created_after` | timezone-aware datetime (inclusive) | none |
| `created_before` | timezone-aware datetime (exclusive) | none |
| `limit` | 1-100 | 50 |
| `offset` | >= 0 | 0 |

Order: `created_at DESC, id DESC`. Invalid enum values, naive datetimes, or
out-of-range pagination return `422`.

Response `200`: `ExecutionLogListResponse`.

### 12.2 Read

`GET /api/workspaces/{workspace_id}/execution-logs/{log_id}`

Response `200`: `ExecutionLogResponse`.

### 12.3 Errors

`{"detail": "..."}` via the existing handlers: `401`, `403`, `404`, `422`.
No write methods exist; `POST`, `PATCH`, `PUT`, `DELETE` return `405`.

### 12.4 Existing routes

No request, response, status code, or error body of an existing route
changes.

## 13. Data Contract

### 13.1 `ExecutionLogResponse`

```json
{
  "id": "uuid",
  "workspace_id": "uuid",
  "operation": "agent_route",
  "routing_intent": "tool_request",
  "status": "succeeded",
  "outcome": "tool_approval_required",
  "error_category": null,
  "http_status": 200,
  "latency_ms": 842,
  "user": {"id": "uuid", "name": "Current display name"},
  "agent": {"id": "uuid", "name": "IT Support Assistant"},
  "tool": {"tool_key": "create_it_access_request", "name": "IT access request"},
  "approval_id": "uuid",
  "knowledge_base": null,
  "details": {},
  "created_at": "2026-09-29T08:00:00Z"
}
```

- `user`, `agent`, and `knowledge_base` are `{id, name}` references resolved
  from current rows at read time; `tool` is `{tool_key, name}`. Names are
  displayed to administrators who can already see them elsewhere in the
  Workspace; they are never stored in the log.
- `details` contains only the Section 8.2 keys that were recorded.
- The response schema is strict (`extra = "forbid"`) and validates
  `status`/`error_category`/`http_status` consistency.

### 13.2 `ExecutionLogListResponse`

```json
{"items": [ExecutionLogResponse], "limit": 50, "offset": 0}
```

Same shape as the Feature 013 Approval list.

## 14. Migration Proposal (not created in Phase A)

Additive revision `0010` (down revision `0009`). No change to `0001`-`0009`,
no change to any existing table, no backfill, no destructive operation.

Table `execution_logs`:

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | UUID | no | PK, `gen_random_uuid()` |
| `workspace_id` | UUID | no | FK `workspaces(id)` |
| `user_id` | UUID | no | FK `(user_id, workspace_id)` -> `memberships(user_id, workspace_id)` |
| `operation` | VARCHAR(32) | no | CHECK in Section 6 values |
| `routing_intent` | VARCHAR(32) | yes | CHECK `knowledge_qa`, `tool_request`, `unsupported` |
| `status` | VARCHAR(16) | no | CHECK `succeeded`, `failed` |
| `outcome` | VARCHAR(40) | yes | CHECK in Section 9.1 values |
| `error_category` | VARCHAR(40) | yes | CHECK in Section 9.2 values |
| `http_status` | SMALLINT | no | CHECK 100-599 |
| `latency_ms` | INTEGER | no | CHECK `>= 0` |
| `agent_id` | UUID | yes | FK `(agent_id, workspace_id)` -> `agents(id, workspace_id)` |
| `tool_id` | UUID | yes | FK `(tool_id, workspace_id)` -> `tools(id, workspace_id)` |
| `tool_key` | VARCHAR(64) | yes | denormalized from the Tool row for filtering |
| `approval_id` | UUID | yes | FK `(approval_id, workspace_id)` -> `approvals(id, workspace_id)` |
| `knowledge_base_id` | UUID | yes | FK `(knowledge_base_id, workspace_id)` -> `knowledge_bases(id, workspace_id)` |
| `details` | JSONB | no | default `'{}'` |
| `created_at` | TIMESTAMPTZ | no | default `now()` |

Additional CHECK constraints:

- `status_error_consistency`: `(status = 'failed') = (error_category IS NOT NULL)`
- `status_http_consistency`: `(status = 'succeeded') = (http_status BETWEEN 200 AND 299)`
- `routing_intent_agent_route_only`: `routing_intent IS NULL OR operation = 'agent_route'`
- `tool_reference_pair`: `(tool_id IS NULL) = (tool_key IS NULL)`
- `details_object`: `jsonb_typeof(details) = 'object'`

Indexes:

- `ix_execution_logs_workspace_created` on
  `(workspace_id, created_at, id)` (list order `created_at DESC, id DESC`
  via a backward index scan).
- `ix_execution_logs_workspace_agent_created` on
  `(workspace_id, agent_id, created_at)` (Agent filter).

Rules:

- All foreign keys `ON DELETE RESTRICT`. Composite foreign keys use the
  default `MATCH SIMPLE`, so a null reference is not checked and a non-null
  reference must belong to the same Workspace.
- Downgrade drops the table and its indexes; it is exercised only on the
  dedicated test database.
- No retention job, partitioning, or trigger in Feature 014.

## 15. Frontend Scope (H3)

A minimal read-only **Execution Logs** view:

- Navigation entry shown only when the selected Workspace role is
  `agent_admin` or `system_admin` (presentation only; the backend enforces).
- Table, newest first: time, operation, user, Agent, Tool, status, outcome or
  error category, latency.
- Filters: operation and status. "Load more" pagination via `offset`.
- Row expansion shows `routing_intent`, `http_status`, `approval_id`,
  Knowledge Base, and the recorded `details` keys with fixed labels.
- Empty, loading, `403`, and error states.
- No charts, dashboards, export, search, or editing.

## 16. Threat Model

| Threat | Mitigation |
|---|---|
| Request text, arguments, justifications, or notes leak into logs | Explicit columns plus strict `details` allow-list (Section 8); no free-form field; tests with sentinel strings scan every column |
| Personal data accumulates in logs | Only internal IDs stored; names resolved at read time for authorized administrators |
| Exception or provider messages leak | Classification by type and constants only; `str(exc)` never stored |
| Cross-Workspace reference or read | Composite foreign keys; every query filtered by `workspace_id`; uniform `404` |
| Employee reads colleagues' activity | Read requires `agent_admin` or `system_admin` |
| Log write commits unintended business state | Recorder rolls back the business transaction before its own insert |
| Log write deadlocks with the Approval row lock | Insert only after the business transaction ends; `lock_timeout` bound |
| Log failure blocks or alters business behavior | Best-effort; status, body, and commits unchanged |
| Log tampering through the application | No write API; append-only service; `ON DELETE RESTRICT` |
| Unbounded growth | Accepted for MVP; retention designed later (Section 22) |
| Log forging by a client | Every field is server-derived; no client-supplied log content |

## 17. Dependency and Open-Source Evaluation

| Candidate | Fit | Decision |
|---|---|---|
| Existing PostgreSQL + SQLAlchemy + Pydantic | Workspace-owned table, composite FKs, strict schemas | **Use.** Keeps logs inside Workbench tenant isolation and RBAC |
| Python standard library `time.perf_counter`, `logging` | latency, one fixed warning line | **Use** |
| OpenTelemetry SDK + collector | distributed tracing and metrics | Infrastructure telemetry, not a Workspace-scoped product record; needs a collector/backend; revisit for infra observability |
| Langfuse (self-hosted) | LLM traces, evaluation | v3 self-hosting needs ClickHouse, Redis, and object storage; stores prompts/completions by design; would own trace data outside Workbench RBAC |
| LangSmith, Helicone, Arize Phoenix | LLM observability SaaS or proxy | Send prompt and completion content to an external service; conflicts with Section 8 and Workspace ownership |
| structlog / stdout JSON logs | structured application logs | Not queryable per Workspace in the product; no RBAC |
| pgAudit | database statement audit | DBA-level SQL audit, not product-level AI operation records |

Conclusion: no new runtime or frontend dependency. `AGENTS.md` requires the
Workbench to keep ownership of Workspace, RBAC, and tenant isolation; an
external observability platform may be added later as an exporter from these
records, not as their owner.

## 18. Implementation Notes (non-normative)

- **Recorder shape.** A small context manager in
  `app/services/execution_logs.py`, used explicitly in the four route
  handlers, for example
  `with execution_log(session, workspace_id, user_id, Operation.AGENT_ROUTE) as trace:`.
  The handler sets resolved references and the outcome on `trace`. On exit
  the recorder classifies, rolls back, writes, and returns or re-raises.
  Middleware is not used because it lacks domain context; a `yield`
  dependency is not used because its exception and teardown ordering is
  harder to reason about.
- **Resolved references.** `agent_route` sets `agent_id` after
  `agent_service.get_agent` succeeds. `tool_id`/`tool_key` come from the
  freshly resolved Tool row; `handle_tool_request` may return them alongside
  the outcome, or the recorder looks the Tool up by
  `(workspace_id, tool_key)` from the outcome's public reference.
  `approval_decision`/`approval_cancel` set `approval_id` unless the result is
  `approval_not_found`, and read the Approval's `agent_id` and `tool_id`
  after the business transaction. `knowledge_answer` sets the path
  `knowledge_base_id` unless the result is `knowledge_base_not_found`,
  because the retrieval service resolves the Knowledge Base inside the
  Workspace before any other failure can occur.
- **Classification table.** A single mapping from exception type (and, for
  `ConflictError`/`HTTPException`, the existing detail constants and status
  code) to `(http_status, error_category)`, unit-tested exhaustively.
- **Details model.** A Pydantic model with `extra = "forbid"` and strict
  types, validated before insert; an operation-specific allow-set rejects
  keys not permitted for the operation.
- **Latency clock.** `time.perf_counter()` at handler entry and at outcome
  determination.
- **Tests and failure injection.** Best-effort behavior is tested by forcing
  the insert to fail (for example, a monkeypatched writer or a
  constraint-violating detail) and asserting the original response and
  committed business state are unchanged.

## 19. Acceptance Criteria

- **AC-001** Additive migration `0010` creates `execution_logs` exactly per
  Section 14; `0001`-`0009` unchanged; upgrade and downgrade pass on the test
  database.
- **AC-002** Every request to an in-scope route whose handler body is
  entered writes exactly one record, whether the handler returns or raises
  (best-effort policy aside). Every pre-handler rejection listed in Section
  6.1 (`401`, Workspace `403`/`404`, request validation `422`, and the
  `knowledge_answer` embedding configuration `503`) writes none, and its
  external response is unchanged.
- **AC-003** `agent_route` records `routing_intent` and the correct outcome
  for knowledge answered/unsupported, Tool executed, approval required, Tool
  not executed (with reason), and unsupported request.
- **AC-004** Read-only Tool executions are recorded with `tool_id` and
  `tool_key` (closes the Feature 013 Section 22.2 gap).
- **AC-005** Approval creation or deduplication is recorded only as an
  `agent_route` record with outcome `tool_approval_required` that references
  the created or deduplicated Approval, its Agent, and its Tool; no separate
  creation operation exists. `approval_decision` and `approval_cancel` are
  separate operations whose records reference the Approval, Agent, and Tool
  (except `approval_not_found`) and match the committed Approval state,
  including `rejected`, `cancelled`, `invalidated`, `expired`,
  `approved_execution_succeeded`, and `approved_execution_failed`.
- **AC-006** Every handled failure in Section 9.2 records `status = failed`,
  the correct `http_status` and `error_category`, and resolved references
  only.
- **AC-007** No record contains any Section 8.3 content (sentinel scan over
  all columns including `details`).
- **AC-008** `details` accepts only the Section 8.2 keys for the operation;
  anything else is not written.
- **AC-009** Database rejects cross-Workspace references and inconsistent
  `status`/`error_category`/`http_status`/`routing_intent`/tool pairs.
- **AC-010** Only same-Workspace `agent_admin` and `system_admin` can list and
  read; `employee` and `knowledge_admin` get `403`; foreign or missing IDs
  get identical `404`.
- **AC-011** List filters, ordering, and pagination behave per Section 12.1.
- **AC-012** A failed log write leaves the response status, body, and
  committed business state unchanged.
- **AC-013** Recording never commits uncommitted business work and never
  waits on the request's own Approval lock (decision paths complete without
  lock timeout).
- **AC-014** Responses, status codes, and error bodies of Features 009-013
  routes are unchanged (existing tests pass unmodified).
- **AC-015** `latency_ms` is non-negative and reflects the handler duration
  (fake provider delay test).
- **AC-016** Minimal Execution Logs UI per Section 15 (H3).
- **AC-017** Offline tests only; no network or real provider.
- **AC-018** No new dependency.

## 20. Test Requirements

### 20.1 Migration and model

- Upgrade `0009 -> 0010` and downgrade on the test database; earlier
  revisions unchanged.
- Each CHECK and composite FK rejects its invalid case (cross-Workspace
  Agent, Tool, Approval, Knowledge Base, Membership; illegal status pairs;
  non-object `details`).

### 20.2 Recorder unit tests

- Exhaustive classification table (every Section 9.2 row plus an unmapped
  exception).
- `details` allow-list: permitted keys per operation, rejected unknown keys,
  rejected non-matching strings and negative integers.
- Latency measurement with a controlled clock.

### 20.3 Integration (PostgreSQL)

- One record per operation for every Section 9.1 outcome and every Section
  9.2 category reachable through the four routes.
- Recording boundary: each Section 6.1 pre-handler rejection writes no
  record and keeps its existing response; a failure raised inside the
  handler writes exactly one.
- Sentinel test: request text, Tool arguments, `business_justification`,
  decision note, user name and email, Agent system prompt, and fake provider
  answer text never appear in any stored column.
- Approval decision paths (approve success, approve with drift, adapter
  failure, reject, expired, cancel, busy) record matching outcomes and do
  not time out.
- Forced log write failure: original status and body returned, business rows
  unchanged, no record.
- Business-transaction isolation: pending/flushed pre-entry state, Core/textual
  and connection-level DML, uncommitted handler work, post-commit DML, nested
  savepoint activity, and an aborted post-commit transaction never become
  committed by the recorder; an aborted transaction still records a sanitized
  `internal_error`.
- Read API authorization matrix, cross-Workspace `404`, filters,
  pagination, ordering, `405` for write methods.

### 20.4 Regression

- Full existing backend suite unchanged and passing.
- Frontend `pnpm lint`, `pnpm build`, and component tests for the Execution
  Logs view (role-gated entry, list, filters, load more, empty/error/`403`).

### 20.5 Verification in Phase B

Feature tests first, then the full suite: PostgreSQL integration tests,
`pytest`, `ruff`, `pnpm lint`, `pnpm build`, frontend tests.

## 21. Phase B Documentation Updates

- `DATABASE.md` Section 14 rewritten to match Section 14 of this spec.
- `ARCHITECTURE.md` Section 6 flow and Section 9 Auditability updated to
  describe the recorder and best-effort policy.
- `ROADMAP.md` Milestone 4 status and Milestone 3 tool-execution-log note.

## 22. Out of Scope

- Evaluation datasets, evaluation runs, metrics computation, dashboards,
  and charts (later Milestone 4 features).
- Bad case identification, classification, or version comparison.
- Security audit of rejected authentication or authorization attempts.
- Logging of retrieval search, document indexing, or configuration changes.
- Per-step traces (routing, retrieval, generation, and Tool as separate
  spans), conversation IDs, or request correlation IDs.
- Storing request text, answers, prompts, arguments, or results, even
  redacted or hashed.
- Retention, archival, partitioning, export, or deletion of records.
- Database triggers enforcing append-only at the SQL level.
- External observability platforms or exporters (OpenTelemetry, Langfuse,
  LangSmith, and similar).
- Changing Feature 009-013 behavior, transaction ownership, or error bodies.
- New roles; modifying migrations `0001`-`0009`.

## 23. Required Human Approval Gate

Before Phase B, a human must approve:

1. **Migration:** additive `0010` creating `execution_logs` exactly per
   Section 14; no change to `0001`-`0009` or existing tables; no backfill or
   destructive operation; execution only on the dedicated test database.
2. **Recorded operations:** Section 6 (H4).
3. **Data minimization:** Section 8 stored fields, `details` allow-list, and
   never-stored list; replacement of the `DATABASE.md` free-form
   `input_data`/`output_data` sketch (Section 4.1).
4. **Classification:** Section 9 outcome and error enums.
5. **Write path:** Section 10 ordering, same-session log transaction, and
   rollback-before-insert.
6. **Failure policy:** best-effort recording (H2) and its accepted gap.
7. **Read authorization:** `agent_admin` and `system_admin` only (H1).
8. **API and data contract:** Sections 12-13; no change to existing routes.
9. **Frontend:** minimal read-only view (H3).
10. **Dependencies:** none added (Section 17).

Approval authorizes scoped Phase B implementation and creation of migration
file `0010` with execution against the dedicated test database only. It does
not authorize a non-test migration, evaluation or bad-case features, an
external observability integration, merging to `main`, or any destructive
database operation.

## 24. Human Decisions

MVP defaults proposed by this spec (no decision needed unless the maintainer
disagrees): one record per handled request; no stored content; no
retention; no SQL triggers; latency excludes authentication and the log
write.

Decisions made by the human maintainer: H1-H4 approved as recommended.

| ID | Decision | Resolution (approved) | Alternative (rejected) |
|---|---|---|---|
| H1 | Who may read logs | `agent_admin` and `system_admin` (Product Spec: Agent Administrators "review execution results", System Administrators "view system logs") | `system_admin` only |
| H2 | Log write failure policy | Best-effort: never change the business outcome; Approval rows remain the authoritative audit for writes | Fail closed: return `500` after the business commit (misleading, business state already changed) or write inside business transactions (changes Feature 012-013 transaction ownership) |
| H3 | Frontend in Feature 014 | Minimal read-only Execution Logs view (Section 15) | API only; UI deferred to the evaluation dashboard |
| H4 | Recorded operations | `agent_route`, `knowledge_answer`, `approval_decision`, `approval_cancel` | Also retrieval search and document indexing |

## 25. Tracking

- Branch: `feat/execution-logs` from `origin/main` (`ec55dd2`).
- Issue: #32 - Feature 014 - Execution Logs.
- Pull Request: #33, merged into main on 2026-10-01 at
  `760d7fb315993b52835a5a5ff019adaa200dbe13`; related Issue #32 closed.
