# Feature 013 - Human Approval

Status: Proposed - Phase A specification (revision 3, human decisions H1-H3 applied; Phase A code-review corrections applied) awaiting human approval; not implemented
Milestone: 3
Baseline: `main` at `f57cb8e` (Features 001-012 merged; Alembic head `0008`)
Risk class: High (`AGENTS.md` Review Policy: authorization, tenant isolation,
new migration, write-capable Tool, human approval policy)
Issue: #30 (https://github.com/SongHaiwen-creator/enterprise-ai-workbench/issues/30)

## 1. Goal

Close the Milestone 3 human-in-the-loop path that Feature 012 intentionally
left open. A write-sensitive Tool proposal must become a server-owned
Approval that an authorized human reviews, and only an approved, still-valid,
server-held execution snapshot may produce a single business write.

```text
User request
-> Feature 011 intent routing (unchanged) -> tool_request
-> Feature 012 selection, fresh revalidation, exact arguments (unchanged)
-> write-sensitive Tool (create_it_access_request)
-> Feature 013 creation authorization
-> persist pending Approval + immutable execution snapshot
-> reviewer decision authorization -> reject | approve
   (or requester cancel, or system expiry)
-> on approve, before the approval commits:
   execution authorization + configuration-drift check
   -> fails: Approval invalidated, 409, nothing approved, nothing executed
   -> passes: approved, then at most one project-owned Mock write
-> durable decision fact + separate execution fact
```

Feature 013 must prove:

1. No write-sensitive Tool executes without a recorded approval by an
   authorized reviewer who is not the requester.
2. What executes is exactly the server-held snapshot that was reviewed; a
   client replay or later configuration cannot change it.
3. Creation, decision, and execution are three separately authorized
   boundaries.
4. One Approval produces at most one business write, under any concurrency or
   retry.
5. The approval decision and the execution result are distinct, durable facts.

## 2. Phase A Status and Revision Summary

Phase A is documentation only. No migration, model, service, route, frontend,
or test code is part of this change. Implementation (Phase B) may start only
after the gate in Section 31 is approved.

Revision 2 changes relative to the first draft:

- Separates **decision status** (`pending`, `approved`, `rejected`,
  `cancelled`, `expired`) from **execution status** (`not_started`,
  `succeeded`, `failed`). `approved + failed` is a legal, explainable state.
  (Revision 3 adds `invalidated` and narrows `approved + failed`; see below.)
- Replaces the argument-only snapshot with an **execution-critical capability
  snapshot** and defines configuration-drift handling.
- Defines concrete, versioned **canonicalization and hashing** rules.
- States the three **fresh authorization** boundaries as business rules and
  moves locking detail to non-normative implementation notes.
- Makes the **minimum security audit facts** mandatory and draws the
  Feature 013 / Feature 014 boundary.
- Converges most open questions into MVP defaults; three human decisions
  remain (Section 32).

Revision 3 applies the human decisions recorded in Section 32:

- **H1:** Phase B implements a minimal Approvals UI (list, detail, approve,
  reject, decision and execution status) and nothing more (Section 27).
- **H2:** no `agent_tools` version in Feature 013; the remove/re-add detection
  gap is a documented limitation (Section 16.3).
- **H3:** drift or requester/capability loss found during approve is **not** an
  execution failure. The approval is never persisted as `approved`; the
  Approval becomes terminal `invalidated`, the API returns `409`, and nothing
  executes. `approved + failed` is reserved for a legitimately committed
  approval whose Mock adapter execution then fails.
- Defines "identical request" for pending deduplication precisely
  (Section 17.5).
- States that Workspace authority for requesters and reviewers comes from
  Membership; Users are global identities, not Workspace-owned resources
  (Section 8.1).

Phase A review corrections (checked against `main` at `f57cb8e`; no H1-H3
decision changed):

- Documents the Phase B transaction boundaries the existing session and
  service code require (Section 26.1).
- Defines `decided_at` for expiry and restricts `decision_note` to
  `approved`/`rejected`, with a matching CHECK (Sections 12, 20.1, 23.1).
- Aligns the replay table with the error contract and states that replays
  still pass decision authorization (Sections 15.2, 17.2).
- Adds acceptance and test coverage for H2 and for commit-before-`409`
  ordering; fixes Acceptance Criteria ordering (Sections 28, 29).
- Records where the minimal Approvals UI lives in the frontend (Section 27).

## 3. Scope

Phase B, once approved, will:

- Add additive Alembic revision `0009` with `approvals` and
  `mock_it_access_requests` (Section 23).
- Add a code-owned approval policy and execution-critical version constants to
  the Tool registry entry for `create_it_access_request`.
- Replace the Feature 012 non-persistent `approval_required` return with
  server-side Approval creation (or deduplication) and return its reference.
- Add Workspace-scoped Approval list, read, decision (approve/reject), and
  cancel APIs.
- On approve, run decision authorization, then execution authorization and
  drift checks before the approval commits; on success record `approved` and
  invoke the single local Mock write adapter at most once; on failure record
  `invalidated` and return `409`.
- Add a minimal Approvals UI: list, detail, approve, reject, and decision /
  execution status display (Section 27).
- Update `DATABASE.md` Section 12, `ARCHITECTURE.md` Section 8, and
  `ROADMAP.md` Milestone 3 status in the implementation change.
- Add migration, authorization, isolation, snapshot, drift, state, concurrency,
  execution, API, and frontend tests with no live model, enterprise system, or
  network access.

## 4. Existing Foundation

### 4.1 Feature 012 seam

`backend/app/services/tools.py::handle_tool_request` already:

1. loads active, assigned, same-Workspace Tools;
2. calls the selector once;
3. freshly re-reads User, Workspace, and Membership
   (`_fresh_authorized_caller_identity`);
4. freshly re-resolves Agent, Tool, and assignment (`_fresh_effective_tool`);
5. validates arguments with the registry Pydantic model; and
6. for a non-immediate Tool, returns `ToolApprovalRequiredOutcome` without
   persistence.

Feature 013 changes only step 6. The read-only immediate branch, the
knowledge branch, and the unsupported branch are unchanged. The Feature 012
"ApprovalCandidate" (012 Section 20) is not a code type: it is the freshly
resolved `tool`, the validated `arguments`, and the caller/Agent/Workspace
identifiers held as locals inside `handle_tool_request`. Feature 013 consumes
those in-process values and never serializes them to the client as a trust
token.

### 4.2 Registry facts relied on

`create_it_access_request` is registered with `operation_type =
write_sensitive`, `risk = high`, `immediate_execution = False`, and
`adapter = None`. Feature 013 keeps these values. The Mock write adapter is
attached to a separate approval policy and is unreachable from the Feature 012
dispatch branch.

### 4.3 Documentation discrepancies resolved by this spec

| Source | Current text | Feature 013 resolution |
|---|---|---|
| `DATABASE.md` Section 12 | single `status` with `pending/approved/rejected/cancelled` | split into `decision_status` and `execution_status`; add `expired` and `invalidated` |
| `DATABASE.md` Section 12 | `approver_id` | `decided_by` (no pre-assigned approver in MVP) |
| `DATABASE.md` Section 12 | `request_payload` JSONB | `canonical_arguments` + `capability_snapshot` + `policy_snapshot` |
| `ROADMAP.md` Milestone 3 | "Tool execution creates logs" | write-sensitive executions are recorded by Feature 013 lifecycle facts; generic execution logs remain Feature 014 (Section 22) |

These documents are updated in Phase B, not in this Phase A commit.

## 5. User / System Flow

### 5.1 Requester

1. An active member sends an Agent request (unchanged route).
2. The backend routes, selects, and validates as in Feature 012.
3. For `create_it_access_request`, the backend performs creation
   authorization, builds the snapshot, and persists a `pending` Approval (or
   returns the identical pending one).
4. The response shows `approval_required`, `executed = false`, the Approval ID,
   and its expiry. Nothing is executed.
5. The requester may view the Approval or cancel it while `pending`.

### 5.2 Reviewer

1. An active `system_admin` of the same Workspace opens the review queue.
2. The reviewer sees requester name, Agent and Tool names, canonical argument
   values, creation time, and expiry.
3. The reviewer approves or rejects with an optional note. The request body
   carries only the decision and note.
4. On approve, the backend first runs execution authorization and drift
   checks. If they fail, the Approval becomes `invalidated`, the reviewer
   receives `409`, and nothing is approved or executed; the requester must
   submit a new request. If they pass, the backend records `approved`,
   executes the Mock write once, and records `succeeded`, or `failed` only if
   the Mock adapter itself fails.

### 5.3 System

- A `pending` Approval past `expires_at` becomes `expired` when next touched;
  there is no scheduler.
- No model is called after the Feature 012 selector proposal.

## 6. Terminology

- **Requester**: authenticated User whose Agent request produced the proposal.
- **Reviewer**: User eligible under the approval policy to decide an Approval.
- **Execution snapshot**: immutable, server-generated record of everything
  that determines what would execute (Section 10).
- **Decision**: reviewer `approve`/`reject`, requester `cancel`, or system
  `expire` / `invalidate`.
- **Execution**: the single Mock write attempt for an approved Approval.
- **Configuration drift**: any difference between the execution snapshot and
  the current execution-critical state (Section 16).

## 7. Business Rules

These are normative invariants. Mechanisms appear in later sections and in the
non-normative Section 26.

- **BR-001 Approval-required Tools only.** An Approval is created only for a
  registry definition with `immediate_execution = false` and a non-null
  approval policy. In Feature 013 this is exactly `create_it_access_request`.
  Read-only Tools never create Approvals.
- **BR-002 Server-originated creation.** There is no endpoint that creates an
  Approval from client input. Approvals are created only inside the Agent
  route from the in-process Feature 012 candidate.
- **BR-003 Client replay is untrusted.** Feature 012 `validated_arguments`, and
  every other response field, is display-only. No Approval endpoint accepts
  Tool ID, Tool key, Agent ID, arguments, hashes, risk, policy, executor, or
  requester. Unknown body fields are rejected with `422`. Execution reads
  arguments only from the persisted snapshot.
- **BR-004 Snapshot immutability.** Snapshot fields are written once at
  creation and never updated, repaired, or refreshed.
- **BR-005 Three authorization boundaries.** Creation, decision, and
  execution each re-establish authorization from current persisted state.
  Success at one boundary is never reused as a grant at another.
- **BR-006 Separation of duties.** The reviewer must differ from the
  requester. The MVP reviewer role is `system_admin` only.
- **BR-007 Decision and execution are separate facts.** A committed decision
  is never rewritten by an execution outcome. `approved + failed` means the
  approval was legitimately committed and the Mock adapter execution then
  failed; it is used for nothing else.
- **BR-008 At most one business write.** An Approval produces at most one Mock
  write, regardless of concurrent decisions, duplicate clicks, HTTP retries,
  or server failure around commit.
- **BR-009 No approval and no execution on drift.** If, during approve, any
  execution-critical value differs from the snapshot, or the requester or
  capability is no longer authorized, `approved` is never persisted, nothing
  executes, the API returns `409`, the snapshot is not refreshed, and the
  Approval becomes terminal `invalidated`. It can never be used for
  execution; the requester must create a new Approval through a new Agent
  request.
- **BR-010 No automatic retry.** A failed execution is terminal for that
  Approval. It never returns to `pending` and is never retried automatically.
- **BR-011 Duplicate pending suppression.** While a non-expired `pending`
  Approval exists for an identical request (same Workspace, requester,
  capability and policy snapshot, and canonical arguments; Section 17.5), a
  repeated request returns it instead of creating another. Only `pending`
  Approvals are constrained; once an Approval is terminal, the same business
  request can be submitted again and creates a new Approval.
- **BR-012 Expiry.** `expires_at = created_at + 72 hours`, set by the server.
  Expiry is evaluated with database time. A `pending` Approval past expiry can
  never be approved.
- **BR-013 Reviewers cannot edit.** Reviewers approve or reject the snapshot as
  is. There is no partial approval or argument edit.
- **BR-014 Workspace isolation.** Every Approval and Mock record belongs to one
  Workspace and is only reachable through that Workspace's route.
- **BR-015 Minimum audit facts.** The lifecycle facts in Section 22.1 must be
  durably recorded for every Approval.
- **BR-016 No model after proposal.** Creation, decision, and execution make
  no model call, and Approval data is never sent to a model.
- **BR-017 Membership is the Workspace authority.** A User is a global
  identity. A requester's or reviewer's authority in a Workspace comes only
  from their Membership in that Workspace (status and role), read fresh at
  each boundary. Users are never treated as Workspace-owned resources.

## 8. Authorization

All operations require an authenticated active User, an active route
Workspace, and an active Membership in it, read fresh for the request.

### 8.1 Identity versus Workspace authority

`users` is a global table without `workspace_id`; a User may belong to many
Workspaces with different roles (Feature 001). Feature 013 therefore:

- never scopes a User lookup by Workspace or treats a User row as Workspace
  data;
- derives every requester and reviewer permission from the `memberships` row
  `(user_id, workspace_id)` of the route Workspace: `status = active` and, for
  reviewers, `role = system_admin`;
- requires the User row itself to be `active` as a global precondition;
- stores `requester_id` and `decided_by` as User identities, but binds each to
  the Workspace through a composite foreign key to
  `memberships(user_id, workspace_id)` (Section 23), so a row can only name a
  User who has a Membership in that Workspace;
- snapshots `requester_membership_id` so a replaced Membership is detected.

A Membership in another Workspace, or a global User attribute, never grants
Approval authority.

### 8.2 Requester authorization

A requester is any active Workspace member who may use the active Agent
(Feature 011 BR-004: every active role) and whose request passes Feature 012
Tool eligibility. No additional role is required to *request*.

### 8.3 Reviewer authorization

MVP reviewer policy for `create_it_access_request`:

- active User, active Membership, same Workspace as the Approval;
- Membership role `system_admin` (policy `it-access-approval-v1`);
- `reviewer_id != requester_id`.

`agent_admin` is intentionally excluded. Agent administrators create Tool
configurations, activate them, and assign them to Agents. If the same role
could also approve high-risk use of those capabilities, one person could both
define and authorize a sensitive action, defeating separation of duties.
Configurable approval policy is out of Feature 013 scope.

The reviewer role set is code-owned registry policy, copied into the
Approval's `policy_snapshot`. At decision time the reviewer must satisfy both
the snapshot policy and the current registry policy; a policy change can only
narrow who may decide an existing Approval.

If the only `system_admin` is the requester, the Approval cannot be approved
and ends as `expired` or `cancelled`. This is a safe failure.

Cancel is available to the requester through the API; per H1 the Phase B UI
does not include a cancel control.

### 8.4 Matrix

| Operation | Employee | Knowledge admin | Agent admin | System admin |
|---|---:|---:|---:|---:|
| Cause Approval creation via an active Agent | Yes | Yes | Yes | Yes |
| List / read own Approvals | Yes | Yes | Yes | Yes |
| Cancel own `pending` Approval | Yes | Yes | Yes | Yes |
| List / read all Workspace Approvals | No | No | No | Yes |
| Approve / reject another member's Approval | No | No | No | Yes |
| Approve / reject own Approval | No | No | No | No |

No new role is introduced, and no role gains Knowledge Base, Membership,
Workspace, Agent, or Tool administration rights.

## 9. Workspace Isolation

- Every Approval query filters by route `workspace_id` and Approval ID.
  Missing, foreign-Workspace, and not-visible Approvals return the identical
  `404`.
- Composite foreign keys bind `approvals(agent_id, workspace_id)` to
  `agents(id, workspace_id)` and `approvals(tool_id, workspace_id)` to
  `tools(id, workspace_id)`; `mock_it_access_requests(approval_id,
  workspace_id)` references `approvals(id, workspace_id)`.
- Requester, decider, and invalidation-trigger User IDs are bound to the
  Approval's Workspace through composite foreign keys to
  `memberships(user_id, workspace_id)`; Users themselves stay global.
- Reviewer eligibility uses the reviewer's Membership in the route Workspace
  only; a `system_admin` elsewhere has no authority.
- The snapshot's `workspace_id` must equal the route Workspace at every
  boundary; a mismatch is treated as drift and never executes.
- Lists never include or count foreign rows.

## 10. Execution Snapshot

A Human Approval approves a server-generated **execution snapshot**, not only
arguments. The snapshot has three parts, each stored at creation and never
modified.

### 10.1 Canonical arguments

Source: the `CreateITAccessRequestArguments` instance that already passed
Feature 012 validation. Raw provider JSON is never stored.

Canonicalization rules (server-only):

1. The server produces a JSON-compatible value with
   `model.model_dump(mode="json")`. Types come from the Pydantic model, not
   from the client or provider: integers stay JSON integers (strict model
   rejects booleans and numeric strings), booleans stay booleans, `null`
   stays `null`, dates become ISO-8601 strings, strings are the validated,
   trimmed values.
2. Object keys are sorted by Unicode code point (`sort_keys=True`).
3. Separators are compact: `","` and `":"`, no insignificant whitespace.
4. Non-ASCII characters are emitted as literal characters
   (`ensure_ascii=False`) and the result is encoded as UTF-8. Strings are not
   Unicode-normalized; the exact validated code points are hashed. A string
   that cannot be encoded as UTF-8 (for example a lone surrogate) fails
   closed.
5. `NaN`, `Infinity`, and `-Infinity` are rejected (`allow_nan=False`). The
   current schema has no floating-point fields; adding one requires a new
   schema version that defines its representation.
6. Arrays keep their order. (The current schema has none.)
7. The canonical representation is versioned by the hash prefix below.

Implementation sketch (non-normative, standard library only):

```text
canonical_bytes = json.dumps(
    value, sort_keys=True, separators=(",", ":"),
    ensure_ascii=False, allow_nan=False,
).encode("utf-8")
canonical_arguments_sha256 = sha256(
    b"eaw.approval.arguments.v1\n" + canonical_bytes
).hexdigest()
```

Stored: `canonical_arguments` (JSONB object) and `canonical_arguments_sha256`
(64 lowercase hex). JSONB storage may reorder keys; the hash is always
recomputed from the stored value through the same canonicalization, so JSONB
key order is irrelevant.

Cross-language interoperability (for example RFC 8785 / JCS) is not required
because only this Python backend produces and verifies hashes. It can be
evaluated if another runtime must verify snapshots; Feature 013 adds no
dependency for it.

### 10.2 Capability snapshot

Execution-critical identity and configuration at creation:

| Field | Source | Why it matters |
|---|---|---|
| `workspace_id` | route Workspace | tenant boundary |
| `requester_id` | authenticated User | the write acts for this User |
| `requester_membership_id` | active Membership row | detects a replaced Membership |
| `agent_id` | authorized active Agent | capability path |
| `tool_id` | freshly resolved Tool row | exact Tool configuration |
| `tool_key` | Tool row = registry key | dispatch identity |
| `tool_risk_level` | persisted Tool risk (must equal registry) | risk policy |
| `assignment` | `{agent_id, tool_id}` edge in `agent_tools` | Agent may use the Tool |
| `action_type` | registry, `it_access_request.create` | business action |
| `operation_type` | registry, `write_sensitive` | effect class |
| `tool_definition_version` | registry constant, `create_it_access_request.v1` | argument schema and semantics |
| `executor_key` | registry constant, `mock_it_access_request.v1` | which adapter runs |
| `executor_type` | registry constant, `local_mock` | no external system |
| `canonical_arguments_sha256` | Section 10.1 | binds arguments to capability |

`tool_definition_version` and `executor_key` are explicit constants in the
registry. Any change to the argument model, business validation, adapter
behavior, or result model must bump the relevant constant. Tool display
`name` and `description` are not execution-critical and are excluded.

### 10.3 Policy snapshot

| Field | Value in MVP |
|---|---|
| `approval_policy_version` | `it-access-approval-v1` |
| `required_reviewer_roles` | `["system_admin"]` |
| `self_approval_allowed` | `false` |
| `ttl_hours` | `72` |

### 10.4 Snapshot digest

`snapshot_sha256 = sha256(b"eaw.approval.snapshot.v1\n" +
canonical_json({"arguments_sha256": ..., "capability": ..., "policy": ...}))`
using the Section 10.1 rules. It is stored and recomputed at execution.

### 10.5 Client replay is untrusted

- Approval creation never reads client-supplied Tool, Agent, argument,
  policy, or executor values.
- The decision request accepts only `decision` and an optional `note`
  (Section 19). Any other field, including a replayed `validated_arguments`,
  `tool_id`, `agent_id`, `risk_level`, `policy`, or executor setting, is a
  `422` validation error and is never evaluated.
- Execution input is rebuilt from `canonical_arguments` by re-validating it
  through the current registry argument model; the client never supplies it.

## 11. Approval Persistence Model

One `approvals` row per Approval holds:

- identity and tenancy: `id`, `workspace_id`, `requester_id`, `agent_id`,
  `tool_id`, `action_type`;
- the execution snapshot: `canonical_arguments`, `canonical_arguments_sha256`,
  `capability_snapshot`, `policy_snapshot`, `snapshot_sha256`;
- the decision fact: `decision_status`, `decided_by`, `decided_at`,
  `decision_note`, `expires_at`, and, for invalidation, `invalidation_reason`
  and `invalidation_triggered_by`;
- the execution fact: `execution_status`, `executed_at`,
  `execution_failure_category`;
- timestamps: `created_at`, `updated_at`.

Decision and execution are separate columns with separate value sets. A
single row is sufficient for the MVP because each Approval has exactly one
decision and at most one execution attempt (BR-010). A separate
`approval_executions` table is not needed unless multiple attempts are
introduced later.

The Mock enterprise system's record lives in `mock_it_access_requests`, a
distinct mock domain object with `UNIQUE(approval_id)`.

Not persisted: natural-language request text, Agent system prompt, selector
input/output, raw provider JSON, model names, tokens.

## 12. Decision State Model

| `decision_status` | Set by | Meaning | Terminal |
|---|---|---|---|
| `pending` | creation | awaiting decision | No |
| `approved` | eligible reviewer | reviewer approved this snapshot and execution authorization passed | Yes |
| `rejected` | eligible reviewer | reviewer rejected | Yes |
| `cancelled` | requester | requester withdrew while pending | Yes |
| `expired` | system (lazy) | `now() >= expires_at` while pending | Yes |
| `invalidated` | system, during an approve attempt | execution authorization or drift check failed; the snapshot can never be executed | Yes |

`invalidated` is required by H3. Leaving the Approval `pending` after a failed
approve would let a later approve execute it once the configuration changed
back, which would reuse an old Approval; persisting `approved` would
misrepresent a decision that never took effect. `invalidated` records that the
system, not a human, closed the Approval.

Only `pending` can transition. `decided_by` is the reviewer for `approved` /
`rejected`, the requester for `cancelled`, and `NULL` for `expired` and
`invalidated`. For `invalidated`, `invalidation_triggered_by` records the
reviewer whose approve attempt detected the problem, and
`invalidation_reason` is one of:

- `requester_ineligible` - requester User inactive, or requester Membership
  inactive, missing, or replaced;
- `capability_unavailable` - Agent, Tool, or assignment inactive or missing;
- `configuration_drift` - any other difference between the snapshot and the
  current execution-critical state, registry versions, policy, or argument
  validation (Section 16).

`decided_at` is set on every transition out of `pending`. For `expired` it is
the Approval's `expires_at` (the moment it became unusable), so an Approval
read as effectively expired before the lazy write and after it reports the
same value. For the other transitions it is the database time of the
transition.

`decision_note` is stored only for `approved` and `rejected`. A note sent with
an approve attempt that ends `invalidated` is discarded, because that decision
never took effect.

## 13. Execution State Model

| `execution_status` | Meaning |
|---|---|
| `not_started` | no execution attempted |
| `succeeded` | Mock write committed |
| `failed` | a legitimately approved execution was attempted and the Mock adapter failed; no Mock write committed |

`execution_failure_category` (only when `failed`) has exactly one MVP value:

- `adapter_error` - the Mock adapter raised or returned an invalid result.

Authorization loss and configuration drift are never execution failures; they
are detected before the approval commits and produce `invalidated` (H3).

`executing` is **not persisted in the MVP**. The Mock write runs inside the
approve request's database transaction while the Approval row is locked, so
no other transaction can observe an in-flight execution. A future external
connector that executes outside that transaction must add a persisted
`executing` (or `dispatched`) state, an outbox, reconciliation, and its own
rules for authorization lost after approval, through a new approved spec and
migration.

## 14. Combined State Machine

Legal `(decision_status, execution_status)` pairs:

| Decision | Execution | Legal | Notes |
|---|---|---|---|
| `pending` | `not_started` | Yes | initial |
| `rejected` | `not_started` | Yes | |
| `cancelled` | `not_started` | Yes | |
| `expired` | `not_started` | Yes | |
| `invalidated` | `not_started` | Yes | approve attempt found drift or lost authorization |
| `approved` | `succeeded` | Yes | exactly one Mock record exists |
| `approved` | `failed` | Yes | only `adapter_error`; decision stands; no Mock record |
| `approved` | `not_started` | No in MVP | approval and execution attempt commit together |
| any other | `succeeded`/`failed` | No | |

Transitions:

```text
pending/not_started --cancel (requester)---------------------> cancelled/not_started
pending/not_started --reject (reviewer)----------------------> rejected/not_started
pending/not_started --now() >= expires_at (lazy)-------------> expired/not_started
pending/not_started --approve (reviewer, decision auth ok)
   -> execution authorization + drift check (before approval commits)
      -> fail ------------------------------------------------> invalidated/not_started  (409)
      -> pass -> record approved -> Mock adapter
               -> ok ------------------------------------------> approved/succeeded     (200)
               -> error ---------------------------------------> approved/failed        (502, adapter_error)
```

All other transitions are rejected. Terminal pairs never change.

## 15. Fresh Authorization Boundaries

Each boundary reads current persisted state within the transaction that makes
its state change. A boundary never trusts values carried from a previous
request, from the client, or from an earlier boundary. Workspace authority is
always resolved through Membership (Section 8.1).

### 15.1 Creation authorization (inside the Agent route)

Re-check immediately before inserting:

1. requester User active;
2. route Workspace active;
3. requester Membership in the route Workspace active;
4. requester may use the Agent (active member; Feature 011);
5. Agent active and owned by the route Workspace;
6. Tool active and owned by the route Workspace;
7. `agent_tools` edge `(agent_id, tool_id)` exists in the route Workspace;
8. persisted Tool risk equals registry risk;
9. current registry policy requires approval (non-immediate with approval
   policy).

Failures create nothing: caller access loss -> generic Workspace access-denied
`403` (and validated arguments are not returned, as in Feature 012);
capability loss -> `409`; registry inconsistency -> `503`.

### 15.2 Decision authorization (approve, reject)

Re-check:

1. reviewer User active;
2. route Workspace active;
3. reviewer Membership in the route Workspace active;
4. Approval belongs to the route Workspace;
5. reviewer Membership role in snapshot `required_reviewer_roles` and in
   current registry reviewer roles;
6. reviewer is not the requester;
7. `decision_status = pending` and not expired.

Cancel re-checks 1-4, requires the caller to be the requester, and requires 7.

A failure of checks 1-6 changes nothing. Only a caller who passes checks 1-6
(cancel: 1-4 and requester) and then fails check 7 because the Approval is past
expiry causes the lazy `expired` write. Reviewer-side failures never
invalidate the Approval, because another eligible reviewer may still decide
it.

### 15.3 Execution authorization (approve only, before the approval commits)

Execution authorization is a separate security boundary, run after decision
authorization succeeds and before `approved` is persisted. Re-check:

1. the Approval is `pending/not_started` under the current lock;
2. route Workspace active and equal to snapshot `workspace_id`;
3. requester User active, and requester Membership in the route Workspace
   active with the same Membership ID as the snapshot;
4. Agent active, same Workspace, same ID;
5. Tool active, same Workspace, same ID and `tool_key`, persisted risk equal to
   snapshot risk and to registry risk;
6. `agent_tools` edge `(agent_id, tool_id)` still present;
7. current registry `action_type`, `operation_type`,
   `tool_definition_version`, `executor_key`, `executor_type`, and approval
   `policy_version` equal the snapshot;
8. stored `canonical_arguments` re-validate through the current argument model
   and re-canonicalize to `canonical_arguments_sha256`;
9. recomputed `snapshot_sha256` equals the stored digest.

Any failure: `approved` is not persisted, nothing executes, the Approval
becomes `invalidated` with the matching reason, that state is committed, and
only then does the API return `409`. One exception: if the route Workspace is
no longer active (item 2), that is loss of the reviewer's own access, so the
generic `403` applies and the Approval is unchanged. A snapshot
`workspace_id` that differs from the route Workspace is `configuration_drift`.

Only after all checks pass does the service record `approved` and invoke the
adapter. In the MVP the checks, the decision, and the adapter call share one
transaction and the relevant rows stay locked (Section 26), so nothing can
change between the checks and the write. This single-transaction execution is
an MVP implementation choice for a local Mock system; it does not allow a
future real enterprise executor to skip execution-time authorization.

## 16. Configuration Drift Handling

### 16.1 What counts as drift

Any mismatch detected by Section 15.3 items 2-9. Examples: Agent disabled;
Tool disabled; assignment removed; Tool risk changed; registry argument
schema, adapter, or executor version bumped; approval policy version changed;
requester Membership disabled or replaced.

### 16.2 Rules (H3)

- `approved` is never persisted.
- Nothing executes.
- The snapshot is never refreshed or rewritten.
- The Approval becomes terminal `invalidated/not_started` with a reason and
  can never be used for execution.
- The API returns `409 Conflict` with a sanitized message.
- The requester must create a new Approval through a new Agent request, which
  takes a fresh snapshot and requires a fresh review.

Configuration drift and authorization failures that occur before the approval
commits are not execution failures and never produce `approved/failed`.

### 16.3 Known limitation: assignment remove/re-add (H2)

`agent_tools` has no version or revision column, and Feature 013 does not add
one. Removing an assignment and re-adding the same `(agent_id, tool_id)` pair
between creation and approve is therefore indistinguishable from never
removing it. The re-added edge grants the identical capability, and every
other snapshot field is still verified. Feature 013 does not enlarge its data
model to close this gap. An assignment revision or version must be designed
before any real enterprise system is connected.

## 17. Idempotency and Concurrency

### 17.1 Required invariants

- Competing decisions on one Approval are serialized; exactly one wins.
- A decision transition is atomic: status, actor, time, and note change
  together or not at all.
- A duplicate decision is safe: it causes no second side effect.
- Duplicate execution is impossible, including with direct database access.
- The Mock side effect and `execution_status = succeeded` commit together;
  neither exists without the other.
- `approved` is never committed unless execution authorization passed in the
  same transaction.

### 17.2 Decision replay rules

| Current state | Incoming | Caller | Result |
|---|---|---|---|
| `pending` (not expired) | permitted action | permitted | perform it |
| `approved/*` | approve | same reviewer | `200`, current representation, no re-execution |
| `rejected` | reject | same reviewer | `200`, current representation |
| `cancelled` | cancel | requester | `200`, current representation |
| `invalidated` | any | permitted | `409` `Approval is no longer pending` |
| any terminal | any other combination | permitted | `409` `Approval is no longer pending` |
| `pending` past expiry | any | permitted | record `expired`, `409` `Approval has expired` |

"Permitted" and "same reviewer"/"requester" mean the caller passes decision
authorization checks 1-6 now (cancel: checks 1-4 and requester). A replay is
never served to a caller who has since lost access; that caller gets the
Section 19.6 `403`/`404` like any other request. `detail` strings are those of
Section 19.6.

A replayed old decision request, a double click, and an HTTP retry are all
covered by this table. No `Idempotency-Key` header is used; idempotency is a
property of the Approval resource, which has exactly one decision.

### 17.3 Scenarios

| Scenario | Outcome |
|---|---|
| Two reviewers approve simultaneously | first serialized decision executes once; second gets `409` |
| Approve races reject or cancel | first serialized wins; the other gets `409` |
| Reviewer double-clicks approve | second is a same-reviewer replay: `200`, no second write |
| Client retries after timeout | replay returns the committed state, or performs the decision if the first attempt rolled back |
| Crash before commit | whole transaction rolls back; still `pending`; no Mock record |
| Crash after commit, before response | committed state is authoritative; retry is a replay |
| Two identical Agent requests | pending dedupe returns one Approval |
| Drift found during approve | `invalidated`, `409`; new request required |
| Expired Approval | `expired`, `409` |

### 17.4 Database guards (proposal)

- `UNIQUE (approval_id)` on `mock_it_access_requests`.
- Conditional transition `WHERE decision_status = 'pending'`.
- CHECK constraints on legal status pairs (Section 23).
- Partial unique index for pending dedupe (Section 17.5).

Locking mechanism is described in Section 26.

### 17.5 Definition of an identical request

Two requests are identical when all of the following are equal:

- `workspace_id`;
- `requester_id` (and, through the snapshot, `requester_membership_id`);
- the capability snapshot and policy snapshot (Agent, Tool, assignment, action,
  versions, executor, reviewer policy);
- the canonical arguments.

The stable key is `(workspace_id, requester_id, snapshot_sha256)`, because
`snapshot_sha256` already covers the capability snapshot, policy snapshot, and
`canonical_arguments_sha256` (Section 10.4). A partial unique index constrains
this key **only while `decision_status = 'pending'`**. Consequences:

- repeating an identical request while one is pending returns that Approval;
- once the Approval is approved, rejected, cancelled, expired, or invalidated,
  the same business request can be submitted again and creates a new
  Approval with a new review;
- a request that differs in any argument, or is made after a capability or
  policy change, has a different digest and creates a separate Approval;
- a pending row already past expiry is first marked `expired`, so it does not
  block a new identical request.

## 18. Mock Write Execution Boundary

Phase B may implement exactly one write adapter:

- `mock_it_access_request.v1`, statically registered in code for
  `create_it_access_request` only;
- executes in-process, writing one `mock_it_access_requests` row in the same
  PostgreSQL transaction as the Approval execution state;
- Workspace-bound: the row's `workspace_id` equals the Approval's;
- receives only an execution context built from freshly read rows
  (`workspace_id`, `approval_id`, `requester_id`, `reviewer_id`, `agent_id`,
  `tool_id`) and the re-validated argument model;
- deterministic reference `ITAR-` + upper hex of the first 6 bytes of
  `sha256(b"eaw.mock-it-access.v1\n" + approval_id.bytes)`;
- stores `system`, `access_level`, `duration_days`, fixed `status =
  'recorded'`, `created_at` (database time); does not copy
  `business_justification`;
- returns a strict `ITAccessRequestExecutionResult`.

It must never:

- make any network, HTTP, DNS, file, subprocess, or dynamic-import call;
- read a URL, endpoint, host, credential, or code reference from the database
  or from input;
- accept user-configurable code;
- modify Workbench Users, Memberships, roles, Workspaces, Agents, Tools, or
  Knowledge Bases;
- contact any real ERP, IAM, HR, finance, database, SaaS, webhook, or MCP
  system;
- be reachable from the Feature 012 immediate branch or any route other than
  the approve decision.

No generic HTTP executor exists, and no database value can become an
executable network target.

## 19. API Contract

All routes are under `/api/workspaces/{workspace_id}`, require Bearer
authentication and an active Membership in an active Workspace, and use
request models with `extra = "forbid"`.

### 19.1 Agent route: `approval_required` outcome (additive change)

`POST /agents/{agent_id}/route` keeps its request body and top-level union.
The `approval_required` Tool outcome gains an `approval` object and is
returned only after the Approval is persisted:

```json
{
  "request": "Request read-only production database access for 14 days to investigate approved incidents.",
  "intent": "tool_request",
  "outcome": {
    "status": "approval_required",
    "tool": { "tool_key": "create_it_access_request", "name": "Create IT access request" },
    "executed": false,
    "approval_required": true,
    "validated_arguments": {
      "system": "production_database",
      "access_level": "read_only",
      "business_justification": "Investigate approved production incidents.",
      "duration_days": 14
    },
    "approval": {
      "id": "approval-uuid",
      "decision_status": "pending",
      "execution_status": "not_started",
      "created_at": "2026-09-28T10:00:00Z",
      "expires_at": "2026-10-01T10:00:00Z"
    },
    "result": null,
    "message": "An approval request was submitted for human review. Nothing was executed."
  }
}
```

`validated_arguments` remains display-only (BR-003). A deduplicated request
returns the existing Approval's values.

Contract changes to note: `ToolApprovalRequiredOutcome` uses
`extra = "forbid"`, so Phase B adds `approval` to the model itself (required),
and the `message` text changes from the Feature 012 wording to the one above.
The Approval is committed before this response is built (Section 26.1).

### 19.2 List

`GET /approvals?scope=mine|review&decision_status=&execution_status=&limit=50&offset=0`

- `scope=mine` (default): Approvals where the caller is requester.
- `scope=review`: all Workspace Approvals; reviewers only, else `403`.
- `decision_status`: effective status filter (a past-expiry `pending` is
  reported and filtered as `expired`).
- `limit` 1-100 (default 50); `offset` >= 0.
- Order: `created_at` desc, then `id` desc.
- `200`: `{"items": [ApprovalResponse], "limit": 50, "offset": 0}`.

### 19.3 Read

`GET /approvals/{approval_id}` -> `200 ApprovalResponse` for the requester or
an eligible reviewer; otherwise `404`.

### 19.4 Decide

`POST /approvals/{approval_id}/decision`

```json
{ "decision": "approve", "note": "Approved for incident INC-1042." }
```

- `decision`: `approve` or `reject`.
- `note`: optional; `null`/omitted means none; trimmed; 1-1,000 characters;
  control characters other than newline and tab rejected.
- No other field is accepted.

Responses:

- reject: `200` with `rejected/not_started`;
- approve, execution authorization passes, Mock write succeeds: `200` with
  `approved/succeeded`;
- approve, execution authorization or drift check fails: `approved` is not
  persisted; the Approval is committed as `invalidated/not_started`; `409`
  with body `{"detail": "<fixed message>", "approval_id": "<id>"}`;
- approve, checks pass, Mock adapter fails: committed as `approved/failed`
  (`adapter_error`); `502` with the same body shape.

### 19.5 Cancel

`POST /approvals/{approval_id}/cancel` with `{}` or no body. Requester only.
`200` with `cancelled/not_started`.

### 19.6 Error contract

| Status | Condition | `detail` |
|---|---|---|
| `401` | missing/invalid authentication | existing |
| `403` | disabled User/Workspace, missing/inactive Membership | existing generic Workspace access denied |
| `403` | visible Approval but caller may not take this action (self-review, non-reviewer decision, non-requester cancel) | `Approval action not permitted` |
| `403` | `scope=review` by non-reviewer | `Approval review not permitted` |
| `404` | missing, foreign, or not-visible Approval | `Approval not found` |
| `409` | not pending (non-replay) | `Approval is no longer pending` |
| `409` | expired | `Approval has expired` |
| `409` | approve found drift or requester/capability loss; Approval invalidated, nothing approved | `Approval is no longer valid; submit a new request` |
| `409` | lock contention timeout | `Approval is being processed; retry` |
| `422` | body/query/path validation, including any replayed execution field | existing validation shape |
| `502` | Mock adapter failure / invalid result | `Enterprise Tool request failed` |
| `503` | registry/approval-policy inconsistency | `Tool configuration is unavailable` |

Error bodies never contain arguments, justification, note, request text,
names, emails, foreign IDs, SQL, or stack traces. The specific failure
category is visible only through `ApprovalResponse.execution` to authorized
viewers.

## 20. Data Contract

### 20.1 `ApprovalResponse`

```json
{
  "id": "approval-uuid",
  "workspace_id": "workspace-uuid",
  "decision_status": "approved",
  "execution_status": "succeeded",
  "action_type": "it_access_request.create",
  "tool": { "tool_key": "create_it_access_request", "name": "Create IT access request" },
  "agent": { "id": "agent-uuid", "name": "Employee Service Assistant" },
  "requester": { "id": "user-uuid", "name": "Employee One" },
  "arguments": {
    "system": "production_database",
    "access_level": "read_only",
    "business_justification": "Investigate approved production incidents.",
    "duration_days": 14
  },
  "created_at": "2026-09-28T10:00:00Z",
  "expires_at": "2026-10-01T10:00:00Z",
  "decision": {
    "decided_by": { "id": "reviewer-uuid", "name": "Admin One" },
    "decided_at": "2026-09-28T11:00:00Z",
    "note": "Approved for incident INC-1042.",
    "invalidation_reason": null
  },
  "execution": {
    "executed_at": "2026-09-28T11:00:00Z",
    "failure_category": null,
    "result": {
      "type": "it_access_request",
      "reference": "ITAR-3FA91C07B2D4",
      "system": "production_database",
      "access_level": "read_only",
      "duration_days": 14,
      "status": "recorded"
    }
  }
}
```

Strict cross-field invariants:

- `decision` is `null` only for `pending`; for `expired` and `invalidated` it
  has `decided_by = null` and `note = null`; for `invalidated` it also carries
  `invalidation_reason`; for `expired` (persisted or effective) `decided_at`
  equals `expires_at`.
- `execution` is `null` when `execution_status = not_started`.
- `succeeded` requires `result` and `failure_category = null`.
- `failed` requires `failure_category = "adapter_error"`, `result = null`, and
  `decision_status = approved`.
- Only the legal pairs in Section 14 validate.
- `arguments` uses the typed model selected by `tool.tool_key`.

The response never exposes `tool_id`, hashes, raw snapshots, policy internals,
Agent `system_prompt`, User email, raw provider content, or the original
request text. `tool.name` is the current Workspace display name; `tool_key`
and `arguments` come from the snapshot.

### 20.2 `ITAccessRequestExecutionResult`

`type = "it_access_request"`, `reference` matching `^ITAR-[0-9A-F]{12}$`,
`system`, `access_level`, `duration_days` (1-90), `status = "recorded"`;
`extra = "forbid"`.

## 21. Failure Semantics

| Failure point | Decision | Execution | Mock row | Response |
|---|---|---|---|---|
| Creation: caller access lost | none created | - | none | `403` |
| Creation: capability lost | none created | - | none | `409` |
| Creation: registry inconsistent | none created | - | none | `503` |
| Decision authorization fails (reviewer side) | unchanged | unchanged | none | `403`/`404`/`409` |
| Expired at decision | `expired` | `not_started` | none | `409` |
| Approve: requester ineligible | `invalidated` / `requester_ineligible` | `not_started` | none | `409` |
| Approve: capability unavailable | `invalidated` / `capability_unavailable` | `not_started` | none | `409` |
| Approve: configuration drift | `invalidated` / `configuration_drift` | `not_started` | none | `409` |
| Approve: checks pass, adapter raises or returns invalid result | `approved` | `failed` / `adapter_error` | rolled back | `502` |
| DB error or crash before commit | unchanged `pending` | `not_started` | none | sanitized `500`/`503` |
| Crash after commit | committed state | committed state | consistent | client re-reads |

No failure is converted into success, retried automatically, or returned to
`pending`. `approved/failed` never results from authorization loss or drift.

## 22. Audit and Logging Boundary

### 22.1 Feature 013 owns (mandatory)

Durable, queryable facts for every Approval:

| Fact | Where |
|---|---|
| approval created, when | `approvals.id`, `created_at` |
| requester | `requester_id` |
| workspace | `workspace_id` |
| capability snapshot and digest | `capability_snapshot`, `policy_snapshot`, `canonical_arguments`, `canonical_arguments_sha256`, `snapshot_sha256` |
| decision | `decision_status` |
| reviewer / canceller | `decided_by` |
| decision time | `decided_at` |
| decision note | `decision_note` |
| cancellation / expiry | `decision_status`, `decided_at` (`decided_by` null for expiry) |
| invalidation during approve | `decision_status = invalidated`, `invalidation_reason`, `invalidation_triggered_by`, `decided_at` |
| execution attempted | `execution_status != not_started`, `executed_at` |
| execution result | `execution_status`, linked `mock_it_access_requests` row |
| sanitized failure category | `execution_failure_category` |

Because each Approval has one decision and at most one execution attempt,
these columns form a complete lifecycle record without an event table.
Records are never deleted through the application; `ON DELETE RESTRICT`
preserves them.

### 22.2 Feature 014 owns (not started here)

Generic execution-log infrastructure: unified execution events across RAG,
routing, read-only and write Tools; latency; search and filtering;
dashboards; bad-case linkage; evaluation integration; observability
expansion. Feature 013 creates no `execution_logs` table and no dashboard.
Read-only Tool executions remain unlogged until Feature 014 (known gap).

### 22.3 Logging rules

- The backend currently emits no application logs; Feature 013 adds none by
  default.
- If a log line is ever added, it may contain only a fixed event name,
  Workspace ID, Approval ID, statuses, and failure category.
- Never log or return in errors: arguments, `business_justification`,
  decision notes, request text, Agent prompts, names, emails, passwords,
  tokens, API keys, SQL, stack traces, or raw adapter exceptions.
- The raw user prompt is not stored in the Approval.

## 23. Migration Proposal (not created in Phase A)

Future additive revision `0009`, `down_revision = "0008"`. Revisions
`0001`-`0008` stay byte-for-byte unchanged. No existing table is altered.

### 23.1 `approvals`

| Column | Type | Null | Rules |
|---|---|---|---|
| `id` | UUID | no | PK, `gen_random_uuid()` |
| `workspace_id` | UUID | no | FK `workspaces.id` RESTRICT |
| `requester_id` | UUID | no | composite FK `(requester_id, workspace_id)` -> `memberships(user_id, workspace_id)` RESTRICT |
| `agent_id` | UUID | no | composite FK `(agent_id, workspace_id)` -> `agents(id, workspace_id)` RESTRICT |
| `tool_id` | UUID | no | composite FK `(tool_id, workspace_id)` -> `tools(id, workspace_id)` RESTRICT |
| `action_type` | VARCHAR(64) | no | `IN ('it_access_request.create')` |
| `canonical_arguments` | JSONB | no | `jsonb_typeof = 'object'` |
| `canonical_arguments_sha256` | CHAR(64) | no | `^[0-9a-f]{64}$` |
| `capability_snapshot` | JSONB | no | object |
| `policy_snapshot` | JSONB | no | object |
| `snapshot_sha256` | CHAR(64) | no | `^[0-9a-f]{64}$` |
| `decision_status` | VARCHAR(16) | no | default `pending`; six values |
| `decided_by` | UUID | yes | composite FK `(decided_by, workspace_id)` -> `memberships(user_id, workspace_id)` RESTRICT |
| `decided_at` | TIMESTAMPTZ | yes | |
| `decision_note` | TEXT | yes | length 1-1000 when present |
| `invalidation_reason` | VARCHAR(32) | yes | three values |
| `invalidation_triggered_by` | UUID | yes | composite FK `(invalidation_triggered_by, workspace_id)` -> `memberships(user_id, workspace_id)` RESTRICT |
| `execution_status` | VARCHAR(16) | no | default `not_started`; three values |
| `executed_at` | TIMESTAMPTZ | yes | |
| `execution_failure_category` | VARCHAR(32) | yes | `IN ('adapter_error')` |
| `expires_at` | TIMESTAMPTZ | no | `> created_at` |
| `created_at` | TIMESTAMPTZ | no | default `CURRENT_TIMESTAMP` |
| `updated_at` | TIMESTAMPTZ | no | default `CURRENT_TIMESTAMP` |

CHECK constraints:

- value sets for `decision_status`, `execution_status`,
  `execution_failure_category`, `invalidation_reason`, `action_type`;
- legal pairs: `decision_status <> 'approved'` implies
  `execution_status = 'not_started'`; `decision_status = 'approved'` implies
  `execution_status IN ('succeeded','failed')`;
- `decided_at IS NULL` iff `decision_status = 'pending'`;
- `decided_by IS NOT NULL` iff `decision_status IN
  ('approved','rejected','cancelled')`;
- `decision_status IN ('approved','rejected')` implies
  `decided_by <> requester_id`;
- `decision_status = 'cancelled'` implies `decided_by = requester_id`;
- `executed_at IS NOT NULL` iff `execution_status <> 'not_started'`;
- `execution_failure_category IS NOT NULL` iff `execution_status = 'failed'`;
- `invalidation_reason IS NOT NULL` and `invalidation_triggered_by IS NOT NULL`
  iff `decision_status = 'invalidated'`;
- `decision_status = 'invalidated'` implies
  `invalidation_triggered_by <> requester_id`;
- `decision_note IS NULL OR decision_status IN ('approved','rejected')`;
- `decision_status = 'expired'` implies `decided_at = expires_at`.

The database cannot verify Membership status or the reviewer's role; the
service does. The composite Membership foreign keys guarantee that
`requester_id`, `decided_by`, and `invalidation_triggered_by` name Users who
have a Membership in the Approval's Workspace, using the existing unique
constraint `uq_memberships_user_workspace (user_id, workspace_id)`; no User
is treated as Workspace-owned. The `decided_by <> requester_id` check is kept
because it is cheap and blocks self-approval even if service code or a manual
SQL path is wrong.

Unique and indexes:

- `uq_approvals_id_workspace_id (id, workspace_id)` for the Mock FK;
- partial unique `uq_approvals_pending_dedupe (workspace_id, requester_id,
  snapshot_sha256) WHERE decision_status = 'pending'` (Section 17.5);
- `ix_approvals_ws_decision_created (workspace_id, decision_status, created_at)`;
- `ix_approvals_ws_requester_created (workspace_id, requester_id, created_at)`;
- `ix_approvals_agent_id`, `ix_approvals_tool_id`, `ix_approvals_decided_by`.

### 23.2 `mock_it_access_requests`

| Column | Type | Null | Rules |
|---|---|---|---|
| `id` | UUID | no | PK |
| `workspace_id` | UUID | no | FK `workspaces.id` RESTRICT |
| `approval_id` | UUID | no | UNIQUE; composite FK `(approval_id, workspace_id)` -> `approvals(id, workspace_id)` RESTRICT |
| `requester_id` | UUID | no | composite FK `(requester_id, workspace_id)` -> `memberships(user_id, workspace_id)` RESTRICT |
| `reference` | VARCHAR(32) | no | UNIQUE, `^ITAR-[0-9A-F]{12}$` |
| `system` | VARCHAR(32) | no | three allowed values |
| `access_level` | VARCHAR(16) | no | `read_only`/`standard`; `production_database` requires `read_only` |
| `duration_days` | INTEGER | no | 1-90 |
| `status` | VARCHAR(16) | no | `IN ('recorded')` |
| `created_at` | TIMESTAMPTZ | no | default `CURRENT_TIMESTAMP` |

### 23.3 Rules

- Existing data: none; both tables are new. No backfill, seed, or rewrite.
- Upgrade: create `approvals`, then `mock_it_access_requests`.
- Downgrade: drop `mock_it_access_requests`, then `approvals`, with only their
  owned constraints and indexes. Downgrade destroys audit records, so it is
  exercised only on the dedicated `_test` database; any other environment
  needs separate authorization and a backup.
- `RESTRICT` foreign keys mean a future hard delete of a User, Membership,
  Agent, Tool, or Workspace must handle Approvals explicitly; no hard-delete
  API exists today (Memberships are disabled, not deleted).
- Migration execution is authorized only against the dedicated test database.

## 24. Threat Model

Adversaries: malicious or compromised member, member of another Workspace,
prompt-injected or faulty selector, stale browser tab, concurrent reviewers,
operator error.

### 24.1 Approval integrity

| Threat | Invariant | Mitigation | MVP limitation |
|---|---|---|---|
| Payload tampering in transit or UI | executed values equal reviewed snapshot | no endpoint accepts execution values; snapshot read under lock | none |
| Client replay of `validated_arguments` | client input never becomes execution input | `extra = "forbid"`; only `decision`/`note` accepted | none |
| Forged arguments via direct DB edit | tampered snapshot never executes | hash recomputation and re-validation; `invalidated/configuration_drift` | DB superuser can alter both value and hash; out of app threat scope |
| Stale Approval | expired or drifted Approval never executes and is never reused | DB-time expiry; Section 15.3 checks; terminal `invalidated` | none |
| Prompt-injected harmful but valid proposal | human sees canonical values before any write | enum-bounded arguments, business rules, mandatory review | reviewer attention cannot be enforced |

### 24.2 Authorization

| Threat | Invariant | Mitigation | MVP limitation |
|---|---|---|---|
| Requester loses Membership | no approval or write for a non-member | execution check 3 -> `invalidated/requester_ineligible`, `409` | re-enabled Membership cannot revive the invalidated Approval (by design) |
| Reviewer loses `system_admin` | only a current reviewer decides | fresh decision check 3, 5 | none |
| Cross-Workspace approval | no cross-tenant read or decision | scoped queries, uniform `404`, composite FKs to Agents, Tools, and Memberships | none |
| Global User treated as Workspace resource | authority only from same-Workspace Membership | Membership-based checks; composite Membership FKs | none |
| Self-approval | reviewer != requester | service check + DB CHECK | sole admin cannot approve own request (safe) |
| Disabled Workspace | no activity in disabled Workspace | fresh Workspace check at every boundary | none |
| `agent_admin` defines and approves | separation of duties | reviewer role `system_admin` only | none |

### 24.3 Capability drift

| Threat | Invariant | Mitigation | MVP limitation |
|---|---|---|---|
| Agent disabled | no execution through inactive Agent | execution check 4 | none |
| Tool disabled | no execution of inactive Tool | execution check 5 | none |
| Assignment removed | Agent must still hold the capability | execution check 6 -> `invalidated` | remove-then-re-add undetectable; accepted per H2, revisit before real systems |
| Tool schema changed | old snapshot not run under new semantics | `tool_definition_version` + re-validation | relies on developers bumping the version; tests pin it |
| Risk level changed | risk at execution equals reviewed risk | persisted/registry/snapshot risk equality | none |
| Executor changed | reviewed executor is the one that runs | `executor_key`, `executor_type` equality | same versioning discipline |
| Approval policy changed | old Approval invalid under new policy | `approval_policy_version` equality; reviewer-role intersection | none |

### 24.4 Concurrency

| Threat | Invariant | Mitigation | MVP limitation |
|---|---|---|---|
| Double approval | one decision, one write | row serialization, conditional transition, `UNIQUE(approval_id)` | none |
| Approve / reject race | exactly one terminal decision | same serialization | loser sees `409` |
| Duplicate HTTP retry | no second side effect | replay table (Section 17.2) | none |
| Duplicate execution | at most one Mock row | DB unique + legal-pair CHECK | none |
| Lock contention | no indefinite blocking | `lock_timeout` -> `409` | user retries manually |

### 24.5 Persistence

| Threat | Invariant | Mitigation | MVP limitation |
|---|---|---|---|
| Partial transaction | all-or-nothing | single transaction for checks, decision, execution state, Mock row | valid only for local Mock (Section 13) |
| Decision saved, execution state not saved | never `approved/not_started` | same transaction + CHECK forbids the pair | future async executor needs new design |
| `approved` saved despite drift | approval commits only after execution authorization | checks precede the `approved` update; failures commit `invalidated` instead | none |
| Side effect saved, state not updated | Mock row implies `succeeded` | same transaction; savepoint rollback on adapter error | none |

### 24.6 Logging and secrets

| Threat | Invariant | Mitigation | MVP limitation |
|---|---|---|---|
| Arguments in logs | no sensitive values in logs | no new logs; fixed categories only | none |
| Secrets typed into justification | never logged or sent to models | not logged; UI warns; not sent to models | stored and shown to reviewers; cannot be reliably detected |
| Raw prompt storage | request text not persisted | snapshot excludes request text | Feature 012 response still echoes request to the caller |
| Error leakage | errors reveal no internals | fixed messages; categories only for authorized viewers | none |
| Stored XSS via note/justification | rendered as text | React text rendering; control characters rejected | none |

### 24.7 Migration

| Threat | Invariant | Mitigation | MVP limitation |
|---|---|---|---|
| Bad enum / transition values | illegal states unrepresentable | value-set and pair CHECKs | transition order enforced by service, not DB |
| Inconsistent Workspace FK | no cross-Workspace rows | composite FKs | none |
| Downgrade loses data | no accidental audit loss | test-DB-only execution; backup required elsewhere | downgrade is destructive by nature |
| Existing data handling | no impact on existing rows | new tables only; no backfill | none |
| Editing applied migrations | history immutable | new `0009` only; test asserts `0001`-`0008` unchanged | none |

## 25. Dependency and Open-Source Evaluation

| Candidate | Fit | Why not needed in Feature 013 |
|---|---|---|
| Python standard library (`json`, `hashlib`) | canonical JSON and SHA-256 | **Use.** Sufficient for single-runtime canonicalization |
| Existing SQLAlchemy + PostgreSQL | transactions, row locks, CHECK/UNIQUE, partial indexes | **Use.** Provides serialization and DB-level invariants |
| `transitions` / `python-statemachine` | declarative state machines | six decision and three execution states; in-memory library adds no cross-request or DB guarantees |
| Casbin | policy engine | two-role rule already expressed by existing FastAPI dependencies; new policy language and store |
| OPA | external policy service | extra service and deployment for a rule of a few lines; Workbench must own approval policy |
| Temporal | durable workflows and human tasks | synchronous local Mock write needs no worker, queue, or workflow service |
| LangGraph (`interrupt`) | human-in-the-loop graphs | would move approval state and policy into a graph runtime and checkpointer; `AGENTS.md` reserves approval policy to the Workbench |
| RFC 8785 / JCS library | cross-language canonical JSON | only one runtime verifies hashes; revisit if another runtime must |

Conclusion: no new runtime or frontend dependency.

## 26. Implementation Notes (non-normative)

These notes describe the recommended Phase B mechanism. Business invariants
are in Sections 7, 15, and 17.

- **Approval row lock.** Every decision and cancel path loads the Approval
  with `SELECT ... FOR UPDATE` filtered by ID and Workspace, then applies a
  conditional `UPDATE ... WHERE decision_status = 'pending'`. This serializes
  competing decisions.
- **Capability row locks.** During the approve transaction, reading the
  requester Membership, Agent, Tool, and `agent_tools` edge with
  `FOR SHARE` is recommended: a concurrent disable or unassign then waits
  until the approve transaction commits, so execution authorization cannot be
  invalidated between the check and the write. Lock order: Approval,
  Workspace, Users (by id), Memberships (by user_id), Agent, Tool,
  `agent_tools`. `SET LOCAL lock_timeout = '5s'` bounds waiting. No I/O
  happens under lock.
- **Approve sequence in one transaction.** Lock Approval -> decision
  authorization -> lazy expiry -> execution authorization (a separate,
  independently tested function). On failure: update to `invalidated` with
  reason, commit, raise `409`. On success: update to `approved`, open a
  savepoint, call the adapter; on adapter error roll back to the savepoint and
  set `failed/adapter_error`, commit, raise `502`; on success set
  `succeeded`, commit, return `200`.
- **Creation dedupe.** Lazily expire a matching past-expiry pending row, then
  `INSERT ... ON CONFLICT DO NOTHING` on the partial index and re-select on
  conflict.
- **Lazy expiry.** Decision paths compare `expires_at` with `now()` under the
  row lock; reads report effective `expired` without writing.
- **Registry constants.** Add `action_type`, `tool_definition_version`,
  `executor_key`, `executor_type`, and an `ApprovalPolicy` to the
  `create_it_access_request` definition; keep `immediate_execution = False`
  and `adapter = None`.

### 26.1 Transaction boundaries in the existing code

Verified against `main` at `f57cb8e`. Phase B must work with these facts:

- **One request-scoped session and transaction.** `get_db_session`
  (`backend/app/db/session.py`) yields one `Session` per request
  (`autoflush=False`, `expire_on_commit=False`) and rolls back on an unhandled
  exception. SQLAlchemy 2 autobegins the transaction on the first read, which
  is the `ActiveWorkspaceMembership` dependency
  (`api/dependencies/authorization.py`). No isolation level is configured, so
  PostgreSQL's default `READ COMMITTED` applies: every statement sees the
  latest committed data, which is what the fresh re-reads rely on. Phase B
  must not raise the isolation level on these paths.
- **Services commit internally.** Existing services (`tools.py`, `agents.py`,
  `workspaces.py`) call `session.commit()` inside the service function.
  `handle_tool_request` is read-only today and the Agent route never commits.
  Phase B therefore changes transaction ownership in two places:
  - *Creation:* the creation service inserts or deduplicates the Approval and
    commits it before the Agent route builds the `approval_required`
    response. Model calls (router, selector) happen earlier in the same
    request transaction; they hold no row locks because plain `SELECT`s take
    none. Creation must take no row lock and do no insert before the selector
    returns.
  - *Decision:* the decision service owns the whole approve/reject/cancel
    transaction. It commits explicitly on every outcome that changes state,
    including `invalidated` and `approved/failed`, and only then raises the
    `409`/`502` error. The session rollback in `get_db_session` then has
    nothing to undo. Raising before committing would silently lose the
    `invalidated` or `failed` fact.
- **Identity map versus fresh reads.** The dependency has already loaded the
  caller's `Membership` and `Workspace` into the session identity map.
  Re-selecting those entities in the same session does not refresh loaded
  attributes by default. Fresh checks must either select columns (as
  `_fresh_authorized_caller_identity` already does) or use
  `execution_options(populate_existing=True)` together with
  `with_for_update(...)`. A test must prove that a change committed by
  another connection after the dependency ran is seen.
- **Locks.** SQLAlchemy supports the proposed locks:
  `select(...).with_for_update()` for the Approval row and
  `with_for_update(read=True, of=...)` (`FOR SHARE OF`) for joined capability
  rows. `SET LOCAL lock_timeout` is issued as a statement inside the already
  open transaction. A lock timeout raises `OperationalError` (SQLSTATE
  `55P03`) and aborts the transaction; the service must roll back and then
  raise the contention `409`, leaving no change.
- **Savepoint.** `session.begin_nested()` wraps the adapter call and the Mock
  row flush. On adapter error the savepoint rolls back, the outer transaction
  keeps `approved`, and the service sets `failed/adapter_error` and commits.
- **Error body.** The existing `ConflictError` handler (`api/errors.py`)
  returns only `{"detail"}`. The `{"detail", "approval_id"}` body of Section
  19.4 needs a dedicated exception and handler (or route-level response).
  Existing handlers are not changed.
- **Pending dedupe insert.** `insert(...).on_conflict_do_nothing(
  index_elements=[...], index_where=...)` targets the partial unique index.
  Under `READ COMMITTED`, the re-select after a conflict sees the row that the
  competing transaction committed.

## 27. Frontend Scope (Phase B, H1)

Phase B implements a minimal Approvals UI with exactly:

- **Approval list:** `My requests` for every member and `Review queue` for
  `system_admin` (visibility hint only; the backend enforces).
- **Approval detail:** requester name, Agent and Tool names, canonical
  arguments as plain text, created and expiry times, decision fields, and the
  execution result or failure category.
- **Approve** and **reject** with an optional note, shown only for other
  members' pending Approvals.
- **Decision status and execution status** shown as two separate labels, so
  `approved + failed` and `invalidated` are clearly distinguishable.

Required behavior: pending lock during a request, re-fetch after any action or
`409`, distinct handling of `401`/`403`/`404`/`409`/`422`/`502`/`503`,
Workspace-switch reset, and rejection of late responses.

Not included: cancel control (API only), bulk actions, filters beyond the two
lists, polling, notifications, workflow builder, argument editing, and any
Feature 014 dashboard or log view.

Because the Feature 012 `approval_required` outcome now carries an Approval
reference, the existing Assistant card displays the Approval ID and status as
text, with no decision controls.

Placement in the current frontend: `frontend/app/page.tsx` switches product
areas through `ProductArea = "assistant" | "knowledge-qa" | "workspace"` and
the sidebar `product-nav`. Phase B adds an `"approvals"` area and nav button
that render a new `frontend/app/components/approvals.tsx`. Workspace reset,
pending lock, and error handling follow the existing `assistant.tsx` and
`knowledge-qa.tsx` patterns. Approval types and calls go in
`frontend/utils/api.ts`, and tests go in `frontend/tests/approvals.test.tsx`
next to the updated `assistant.test.tsx`. No routing library or dependency is
added.

## 28. Acceptance Criteria

- **AC-001** Revision `0009` creates only the Section 23 objects; `0001`-`0008`
  unchanged; single head; no drift.
- **AC-002** A validated `create_it_access_request` proposal creates or
  deduplicates exactly one `pending/not_started` Approval after creation
  authorization; nothing executes.
- **AC-003** No Approval endpoint accepts execution-determining client input;
  replayed fields are rejected with `422`.
- **AC-004** The capability, policy, and argument snapshot is complete,
  canonical, hashed, and immutable.
- **AC-005** Decision status and execution status are independent;
  `approved/failed` occurs only for Mock adapter failure after a committed
  approval; illegal pairs are rejected by the database.
- **AC-006** Only a fresh, same-Workspace, active `system_admin` other than the
  requester can approve or reject.
- **AC-007** Requesters can list, read, and cancel their own pending
  Approvals and cannot decide them.
- **AC-008** Missing, foreign, and invisible Approvals return identical `404`.
- **AC-009** Creation, decision, and execution each pass their Section 15
  checks with fresh state; failures behave per Section 21.
- **AC-010** Drift or requester/capability loss found during approve returns
  `409`, never persists `approved`, executes nothing, commits
  `invalidated/not_started` with the reason before responding, and never
  refreshes or reuses the snapshot; a new request creates a new Approval.
  Loss of the reviewer's own access returns `403` and leaves the Approval
  `pending`.
- **AC-011** One Approval yields at most one Mock row and one execution
  result under concurrent decisions, double clicks, and retries.
- **AC-012** Only the registered local Mock adapter executes, only after
  approval, with no network or Workbench-authorization side effect.
- **AC-013** Expired Approvals cannot be approved.
- **AC-014** All Section 22.1 facts are recorded; logs and errors contain no
  sensitive content.
- **AC-015** Feature 011 and Feature 012 non-approval behavior is unchanged.
- **AC-016** Minimal Approvals UI (list, detail, approve, reject, separate
  decision and execution status) and nothing beyond Section 27.
- **AC-017** All tests run offline with fake providers.
- **AC-018** Pending deduplication uses the Section 17.5 identity and never
  blocks resubmission after an Approval is terminal.
- **AC-019** Requester and reviewer authority is resolved from same-Workspace
  Membership; composite Membership foreign keys reject rows naming a User
  without a Membership in that Workspace.
- **AC-020** No `agent_tools` schema change (H2); the remove/re-add limitation
  of Section 16.3 is documented and its current behavior is pinned by a test.
- **AC-021** Fresh checks at every boundary observe state committed by other
  connections after the request's authorization dependency ran (Section
  26.1).

## 29. Test Requirements

### 29.1 Migration

- Upgrade `0008 -> 0009`, downgrade, re-upgrade, single head, drift check.
- Column types, defaults, nullability, FKs (including composite), unique and
  partial unique indexes.
- Direct-SQL rejection of each illegal status pair, self-decision,
  non-requester cancel, missing `executed_at`, missing failure category,
  malformed hashes, cross-Workspace references, a second Mock row per
  Approval, duplicate pending tuple, a `decision_note` on a non-approved /
  non-rejected row, an `expired` row whose `decided_at` differs from
  `expires_at`.
- Migrations `0001`-`0008` unchanged.

### 29.2 Snapshot and canonicalization

- Fixed input produces a pinned canonical byte string and pinned hashes.
- Key order, whitespace, Unicode, integer/boolean/null handling, NaN/Infinity
  rejection, lone-surrogate rejection.
- JSONB round-trip reproduces the same hash.
- Snapshot contains every Section 10.2/10.3 field and excludes request text,
  prompts, and provider output.

### 29.3 Creation

- Pending creation with correct snapshot, TTL, requester, Agent, Tool.
- Identical request (Section 17.5) dedupes while pending; different
  arguments, or a capability/policy change, create a new Approval; after each
  terminal status (`approved`, `rejected`, `cancelled`, `expired`,
  `invalidated`) the same request creates a new Approval; a past-expiry pending
  row is expired then replaced.
- Direct-SQL insert naming a requester or decider without a Membership in the
  Approval's Workspace is rejected.
- Two parallel identical requests (separate DB connections) produce one row.
- Caller revoked during selection: `403`, no row, no arguments disclosed.
- Agent/Tool/assignment inactive at creation: `409`, no row.
- Missing approval policy or risk mismatch: `503`, no row.
- Read-only Tools, knowledge, and unsupported intents create no Approval.

### 29.4 Decision authorization

- Role matrix across four roles; `agent_admin` cannot decide.
- Self-review denied for a `system_admin` requester.
- Reviewer disabled, demoted, Membership disabled, Workspace disabled before
  decision: denied, no change.
- Same User `system_admin` in Workspace A and employee in B.
- Replay table (Section 17.2) exactly, including a replay by a reviewer who
  has since been demoted (`403`); replayed `validated_arguments`, `tool_id`,
  `agent_id`, `risk_level`, `policy` fields rejected with `422`.
- Expiry: a past-expiry Approval reads as `expired` with
  `decided_at = expires_at` before and after the lazy write.

### 29.5 Execution authorization and drift

- Execution-authorization function unit-tested independently of the decision
  path.
- Each drift or authorization source -> `invalidated/not_started` with the
  right reason, `409`, `approved` never persisted, no Mock row, no adapter
  call: requester disabled, Membership disabled or replaced, Agent disabled,
  Tool disabled, assignment removed, Tool risk changed, registry
  `tool_definition_version`, `executor_key`, or policy version changed,
  stored arguments tampered, snapshot digest mismatch.
- The `invalidated` state is committed although the request ends in `409`
  (verified from a separate connection), and the approve note is not stored.
- An `invalidated` Approval cannot be approved later, even after the
  configuration is restored.
- H2 limitation pinned: removing and re-adding the same assignment between
  creation and approve does not invalidate the Approval; the test is named and
  commented as the documented Section 16.3 limitation.
- Fresh-read test: a Membership, Agent, or Tool change committed by another
  connection after the request's authorization dependency ran is detected
  (Section 26.1).
- Snapshot never rewritten after drift; a new request creates a new Approval.
- Reviewer-side failures (reviewer disabled or demoted) leave the Approval
  `pending`.
- Adapter exception and invalid result -> `approved/failed/adapter_error`,
  `502`, no Mock row.
- Success -> `approved/succeeded`, one Mock row with deterministic reference.
- Mock adapter changes no Workbench tables other than its own.
- Feature 012 immediate path still cannot invoke the write adapter, even with
  a Tool row misconfigured as `low`.

### 29.6 Concurrency

- Parallel approve/approve, approve/reject, approve/cancel with separate
  connections: one winner, at most one Mock row.
- Concurrent Tool disable during approve waits and does not break the
  invariant (recommended lock implementation).
- Lock timeout -> `409`, no change.
- Simulated failure before commit leaves `pending/not_started`.

### 29.7 API and disclosure

- Strict response invariants for every legal pair.
- No `tool_id`, hashes, snapshots, email, prompt, or request text in
  responses; error bodies and captured logs contain no sensitive values.
- No model/provider call in any Approval path.

### 29.8 Frontend (H1)

- Approval list (both scopes), detail, approve and reject request bodies,
  separate decision and execution status labels including `approved + failed`
  and `invalidated`, no controls on own Approvals, no cancel control, error
  classes, Workspace reset, late responses, literal rendering of markup.
- Assistant card shows the Approval reference with no decision controls.

### 29.9 Verification in Phase B

Feature-specific PostgreSQL tests, full backend `pytest` on the dedicated test
database with no skipped required tests, Ruff, Alembic head/upgrade/downgrade/
drift, frontend tests, `pnpm lint`, `pnpm build`, `git diff --check`, and
independent review before merge.

## 30. Out of Scope

- Feature 014 and all Milestone 4 execution-log, evaluation, or dashboard work.
- Generic `execution_logs`; logging for read-only Tools.
- Real ERP, IAM, HR, finance, database, SaaS, HTTP, webhook, or MCP
  integrations; generic HTTP executor; dynamic URL execution.
- Any write other than the Mock IT access record.
- LangGraph, Temporal, workflow engines, queues, schedulers, background
  workers, threads, cron-based expiry.
- Multi-level or quorum approvals, delegation, escalation, notifications,
  polling.
- Configurable approval policy, per-Workspace policy, policy UI.
- Reviewer argument editing, partial approval, bulk decisions.
- Execution retry or re-approval of a failed Approval.
- Persisting request text, prompts, or provider payloads.
- New roles; hard deletion; deployment changes.
- Changing Feature 012 behavior other than the `approval_required` outcome.
- Modifying migrations `0001`-`0008`.

## 31. Required Human Approval Gate

Before Phase B, a human must approve:

1. **Migration:** additive `0009` with `approvals` and
   `mock_it_access_requests` exactly per Section 23; no change to
   `0001`-`0008`; no backfill or destructive operation; execution only on the
   dedicated test database.
2. **State model:** separate decision and execution statuses and the legal
   pairs in Section 14.
3. **Execution snapshot:** Section 10 contents, canonicalization, hashing, and
   immutability.
4. **Client replay rule:** Section 10.5 and the minimal decision body.
5. **Authorization:** requester rule, `system_admin`-only reviewer, no
   self-approval (service and DB).
6. **Three boundaries:** Section 15 checks at creation, decision, and
   execution.
7. **Drift handling (H3):** Section 16; no `approved` persisted, terminal
   `invalidated`, `409`, no reuse; `approved/failed` only for adapter failure.
8. **Concurrency and idempotency:** Section 17 invariants and replay table.
9. **Mock execution boundary:** Section 18; same-transaction execution as an
   MVP choice only.
10. **API and data contract:** Sections 19-20, including the additive change
    to the Feature 012 `approval_required` outcome.
11. **Audit boundary:** Section 22; Feature 014 boundary respected.
12. **Dependencies:** none added.
13. **Human decisions:** H1-H3 as recorded in Section 32; pending-dedupe
    identity (Section 17.5); Membership-based authority (Section 8.1).
14. **Transaction boundaries:** Section 26.1. The Agent route commits the
    created Approval, and the decision service owns and commits its
    transaction before raising `409`/`502`. This is the only change to
    existing transaction ownership.

Approval authorizes scoped Phase B implementation and creation of migration
file `0009` with execution against the dedicated test database only. It does
not authorize a non-test migration, a real integration, Feature 014, merging
to `main`, or any destructive database operation.

## 32. Human Decisions

MVP defaults adopted: `system_admin` reviewer; self-approval forbidden;
automatic `pending` creation in the Agent route; 72-hour expiry; optional
rejection note; raw prompt not stored; client replay untrusted; no automatic
retry; duplicate-request control only (no quota); full execution logs deferred
to Feature 014.

Decisions made by the human maintainer and applied in revision 3:

| ID | Decision | Resolution |
|---|---|---|
| H1 | Frontend in Phase B | Minimal Approvals UI: list, detail, approve, reject, decision and execution status. No workflow builder or Feature 014 dashboard (Section 27). |
| H2 | Assignment version | No `agent_tools.version` in Feature 013. The remove/re-add detection gap is a documented limitation; an assignment revision is designed before any real enterprise system is connected (Section 16.3). |
| H3 | Drift found during approve | Do not persist `approved`, do not execute, return `409`, do not refresh the snapshot; the Approval becomes terminal `invalidated` and a new Approval is required. `approved + failed` only for Mock adapter failure after a committed approval (Sections 12-16). |

Clarifications confirmed with this revision:

- "Identical request" for pending deduplication means same Workspace,
  requester, capability and policy snapshot, and canonical arguments, and it
  constrains only `pending` Approvals (Section 17.5).
- Requester and reviewer Workspace authority is based on Membership; Users are
  global identities (Section 8.1).

No human decision remains open for Phase A.

## 33. Tracking

- Branch: `feat/human-approval` from `origin/main` (`f57cb8e`).
- Issue: #30 - Feature 013 - Human Approval (Phase A).
- Pull Request: Phase A only, high-risk, spec and approval proposal only, no
  implementation, no migration; not to be merged until the Section 31 gate is
  approved and Phase B passes independent review.
