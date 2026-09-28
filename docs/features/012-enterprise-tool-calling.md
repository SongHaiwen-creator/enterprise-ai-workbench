# Feature 012 - Enterprise Tool Calling

Status: Implemented - merged into main (PR #28)
Milestone: 3
Issue: #27

## 1. Goal

Turn the validated Feature 011 `tool_request` branch into a controlled,
Workspace-scoped enterprise Tool path:

```text
User request
-> authentication and active Workspace Membership
-> active Workspace-owned Agent
-> unchanged Feature 011 intent routing
-> tool_request
-> active Tools explicitly assigned to that Agent
-> model proposes one Tool and arguments
-> backend revalidates Tool, assignment, arguments, identity, and risk
-> approved low-risk read-only mock adapter executes
   OR sensitive/write-capable Tool remains unexecuted
-> strict server-owned Tool outcome
```

Feature 012 must demonstrate that business data comes from a backend-owned
enterprise capability rather than from a model. It does not implement human
approval persistence, execution after approval, or execution logs. Those
transitions belong to Feature 013.

## 2. Phase A Decision Summary

This proposal requires human approval before implementation because it adds:

- additive Alembic revision `0008`,
- Workspace-owned Tool persistence,
- a persisted Agent-to-Tool capability allowlist,
- Tool-management and assignment authorization,
- a new external-model Tool-selection and argument-proposal boundary, and
- immediate execution of two low-risk, read-only mock enterprise adapters.

The proposed implementation:

- retains the existing Feature 011 route and intent provider unchanged,
- uses a second, narrow, lazy selector only after a validated `tool_request`,
- uses native OpenAI function calling with strict schemas for selection and
  argument proposal,
- treats every model output as untrusted,
- resolves all executable behavior through a project-owned registry keyed by
  a stable `tool_key`,
- stores no endpoint or arbitrary URL,
- executes only registry-declared read-only adapters whose persisted risk is
  `low`,
- never executes `create_it_access_request` in Feature 012,
- makes no second model call with Tool results or employee data,
- introduces no new runtime dependency or broad Agent framework, and
- keeps Tool administration and Agent assignment API-only.

No migration or application implementation is authorized by this Phase A
document. The approval terms in Section 26 must be accepted first.

## 3. Scope

After approval, Feature 012 will:

- Add the minimum durable Tool and Agent-to-Tool persistence model described
  in Sections 6 and 7.
- Let active `agent_admin` and `system_admin` members create registered Tool
  configurations, inspect them, update display metadata, enable or disable
  them, and manage Agent-to-Tool assignments in their Workspace.
- Let every active Workspace role use Tools only through an active Agent.
- Make an Agent eligible to select only active Tools explicitly assigned to
  it in the same Workspace.
- Add a narrow selector provider that receives only the normalized request,
  the Agent routing scope, and canonical definitions for eligible Tools.
- Validate the selected stable key and exact Tool arguments through
  project-owned Pydantic models and additional business rules.
- Derive Workspace, authenticated User, Membership, Agent, and identity context
  on the backend; the selector cannot supply or override them.
- Execute deterministic project-owned mock adapters for
  `get_reimbursement_status` and `get_employee_information`.
- Return `approval_required` without execution for
  `create_it_access_request`.
- Evolve only the Feature 011 `tool_request` outcome while preserving its
  outer route and discriminated response contract.
- Update the Assistant UI to render executed read-only results and an explicit
  approval-required/not-executed state.
- Add migration, authorization, isolation, selector, validation, adapter,
  orchestration, API, and frontend tests without live OpenAI or enterprise
  network access.

## 4. Existing Foundation and Reuse

### 4.1 Feature 011 seam

Feature 011 already enforces this order on:

`POST /api/workspaces/{workspace_id}/agents/{agent_id}/route`

```text
request validation and dependencies
-> authenticated active User
-> active route Workspace and active Membership
-> Agent lookup by route Workspace ID and Agent ID
-> active Agent check
-> narrow intent router
-> knowledge_qa | tool_request | unsupported
```

Feature 012 replaces only the fixed Tool outcome after the validated
`tool_request` decision. It does not add Tool definitions to the Feature 011
intent call and does not broaden that provider's approved contract.

The `knowledge_qa` branch continues to require and resolve Knowledge Base
context only after intent routing and then calls the existing Feature 009
answer service. The `unsupported` branch remains unchanged. Neither branch
loads Tools or initializes the Tool selector.

### 4.2 Existing dependencies

The current backend already contains everything needed for this feature:

- FastAPI and existing dependency-based authentication/authorization,
- SQLAlchemy and Alembic,
- Pydantic strict models and discriminated unions,
- official `openai>=3.8,<4.0` SDK,
- `tiktoken` for deterministic local input-budget checks, and
- injectable provider/service patterns with deterministic test fakes.

No runtime package is added.

### 4.3 Infrastructure options

| Candidate | Fit | Security and testability | Decision |
|---|---|---|---|
| Existing FastAPI services, Pydantic, official OpenAI SDK, and a project-owned Tool registry | Covers one selection step, validation, policy, and adapter dispatch | Small, injectable boundaries; backend remains authoritative | Use |
| LangGraph or a broad Agent framework | Useful for durable multi-step workflows | Adds lifecycle and abstraction not needed for one guarded branch | Do not add |
| LangChain/LlamaIndex Tool Agent | Can expose Tools to a model | Duplicates routing/orchestration and expands the dependency surface | Do not add |
| Database-stored endpoint plus generic HTTP client | Appears configurable | Creates an SSRF/credential/exfiltration boundary and lets data choose execution targets | Reject |
| Separate mock HTTP service | Can imitate an enterprise API | Adds network failure and deployment complexity without improving the trust boundary | Reject |
| Local project-owned mock service/adapters | Demonstrates the same validated dispatch boundary without network access | Deterministic, fast, and testable | Use |

## 5. Trust Boundaries and Authority

### 5.1 Model authority limit

The Tool selector may propose exactly one eligible Tool call and its arguments,
or choose the server-defined no-match control outcome. It never decides:

- authentication or User status,
- Workspace or Membership authorization,
- Agent ownership or active status,
- which Tools are assigned or active,
- Tool risk or operation type,
- whether a Tool may execute immediately,
- authenticated identity or a target User ID,
- database identifiers,
- approval status,
- endpoint, host, URL, secret, or credential,
- adapter implementation,
- enterprise-system results, or
- public messages.

Model output is untrusted even when it conforms to a provider-enforced JSON
schema. The backend must revalidate all selection and argument invariants
before policy evaluation and again confirm effective capability state as close
as practical to adapter dispatch.

### 5.2 Backend-owned decisions

The backend owns:

- route Workspace and authenticated User context,
- active Membership and role resolution,
- scoped Agent lookup and active status,
- the persisted Tool allowlist query,
- the stable-key registry,
- canonical model-facing Tool descriptions and schemas,
- exact Pydantic argument and result models,
- business validation,
- risk and operation-effect policy,
- adapter lookup and invocation,
- mock business data,
- Feature 013 handoff data, and
- all public outcome messages.

### 5.3 No arbitrary outbound execution

Feature 012 stores no `endpoint` field and contains no generic URL executor.
The LLM, User, Tool row, Tool description, or other database value cannot make
the backend send an HTTP request. A stable `tool_key` can resolve only to a
definition compiled into the project-owned registry.

A future real connector requires a separate approved design for allowlisted
hosts, credentials, egress, timeouts, response validation, and secret
management. It must not reinterpret a database URL as executable authority.

## 6. Tool Persistence Model

### 6.1 Decision

Create one Tool configuration row per registered capability per Workspace.
The row enables Workspace-specific availability, display metadata, lifecycle,
assignment, and policy inspection. It does not contain executable code or a
network destination.

Table: `tools`

| Field | Type | Rules |
|---|---|---|
| `id` | UUID | Primary key; PostgreSQL-generated |
| `workspace_id` | UUID | Required FK to `workspaces.id`; `ON DELETE RESTRICT` |
| `tool_key` | VARCHAR(64) | Required stable registry key; immutable after creation |
| `name` | VARCHAR(255) | Required human-facing display name |
| `description` | TEXT | Required human-facing administrative description; API limit 5,000 characters |
| `risk_level` | VARCHAR(16) | Required; `low`, `medium`, or `high`; server-derived from registry in Feature 012 |
| `status` | VARCHAR(32) | Required; `active` or `disabled`; default `disabled` |
| `created_by` | UUID | Required FK to `users.id`; `ON DELETE RESTRICT` |
| `created_at` | TIMESTAMPTZ | Required; database current-timestamp default |
| `updated_at` | TIMESTAMPTZ | Required; database current-timestamp default and service update |

Constraints and indexes:

- primary key on `id`,
- unique `(workspace_id, tool_key)`,
- unique `(id, workspace_id)` for composite Workspace foreign keys,
- `tool_key` check `^[a-z][a-z0-9_]{0,63}$`,
- trimmed non-empty `name` and `description` checks,
- fixed `risk_level` value check,
- fixed `status` value check,
- index on `workspace_id`, and
- index on `created_by`.

New Tool rows default to `disabled`. Creation accepts only a key present in the
project registry. The service writes the registry-owned risk value; clients
cannot set or lower risk in Feature 012. A database/registry risk mismatch
fails closed as unavailable configuration.

`created_by` is justified because Tool availability is security-sensitive
Workspace configuration. It records the authenticated creator without
claiming to provide a complete configuration audit history.

### 6.2 Stable key

`tool_key` is the only dispatch key. It is:

- stable across environments,
- unique within a Workspace,
- restricted to a provider-compatible lowercase identifier,
- validated against the registry on creation and use, and
- never accepted as execution authority by itself.

The initial registered keys are exactly:

- `get_reimbursement_status`,
- `get_employee_information`, and
- `create_it_access_request`.

Unknown keys cannot be created through the API and cannot resolve to an
adapter.

### 6.3 Tool type decision

Do not persist the draft `tool_type = api | mock_api` field. Whether an
adapter is mock or later talks to a real enterprise service is an
implementation/deployment property, not authorization or dispatch authority.
A mutable database type would be redundant and could be mistaken for
permission to choose executable behavior.

The project registry instead owns immutable `operation_type` metadata:

- `read_only`, or
- `write_sensitive`.

Administration responses may expose this registry-derived value for clarity,
but the database does not control it. Every Feature 012 adapter is local and
mock; a later real adapter remains code-owned.

### 6.4 Description decision

The persisted `name` and `description` are administrative/UI copy. They are
treated as untrusted configuration and are not sent to the Tool-selection
model. The registry supplies the canonical selector description and argument
schema so database text cannot alter selector instructions.

### 6.5 Endpoint decision

Remove `endpoint` from the proposed MVP Tool model. It is unnecessary for
local mock adapters and unsafe as a generic execution target. Feature 012 must
not read or execute arbitrary database-stored URLs.

### 6.6 `DATABASE.md` refinement

After approval, `DATABASE.md` should be updated to:

- add Tool `id` and stable `tool_key`,
- replace the draft type/endpoint design with the registry boundary,
- add status, creator, and update timestamp details,
- document the resolved `agent_tools` relationship, and
- remove Agent-to-Tool many-to-many from open design questions.

This Phase A commit does not change `DATABASE.md`; the refinement is part of
the approved implementation scope so the source-of-truth schema and migration
land together.

## 7. Agent-to-Tool Capability Model

### 7.1 Decision

Use an explicit persisted many-to-many allowlist. Merely existing in the same
Workspace never grants an Agent access to a Tool.

Table: `agent_tools`

| Field | Type | Rules |
|---|---|---|
| `workspace_id` | UUID | Required FK to `workspaces.id`; `ON DELETE RESTRICT` |
| `agent_id` | UUID | Required component of same-Workspace Agent FK |
| `tool_id` | UUID | Required component of same-Workspace Tool FK |

Constraints and indexes:

- primary key `(agent_id, tool_id)` for one assignment per pair,
- composite FK `(agent_id, workspace_id)` to
  `agents(id, workspace_id)` with `ON DELETE RESTRICT`,
- composite FK `(tool_id, workspace_id)` to
  `tools(id, workspace_id)` with `ON DELETE RESTRICT`,
- index on `workspace_id`, and
- index on `tool_id` for reverse assignment lookup.

Revision `0008` must first add unique constraint
`uq_agents_id_workspace_id` on `agents(id, workspace_id)` so PostgreSQL can
enforce the composite Agent foreign key. The Agent UUID remains its primary
key.

No surrogate association ID, status, creator, or timestamp is needed for the
minimum durable capability edge. The authorized API operation and Tool/Agent
creator metadata do not constitute a full audit log; configuration-history
auditing is deferred rather than partially modeled here.

### 7.2 Same-Workspace enforcement

Both service and database layers enforce Workspace consistency:

- management routes resolve Agent and Tool by the route Workspace,
- assignment writes include the route Workspace,
- composite foreign keys reject cross-Workspace pairs,
- selector queries join by route Workspace, active Agent, assignment, and
  active Tool, and
- selected Tools are re-resolved through the same scoped relationship before
  policy or dispatch.

A missing ID and a foreign-Workspace ID produce the same scoped `404` on
management operations. Normal User outcomes do not expose Tool database IDs.

### 7.3 Lifecycle and deletion

- Assignments may be configured while an Agent or Tool is inactive.
- A `draft`/`disabled` Agent is never usable.
- A disabled Tool is never eligible, selected, or executed.
- Disabling an Agent or Tool retains its assignments.
- Re-enabling restores the assignment's eligibility only after all runtime
  checks pass.
- Feature 012 adds no hard-delete endpoint for Agent or Tool.
- Restrictive foreign keys mean any future hard deletion must explicitly
  remove assignments first.
- Explicit Tool unassignment deletes only the association row and is an
  authorized configuration operation.

Database constraints cannot enforce active status, active Membership, role,
registry availability, or risk policy. Those remain mandatory service checks.

## 8. Authorization Matrix

All operations require an authenticated active User, active route Workspace,
and active Membership in that Workspace.

| Operation | Employee | Knowledge admin | Agent admin | System admin |
|---|---:|---:|---:|---:|
| Use an active Agent and its eligible Tools | Yes | Yes | Yes | Yes |
| Read Tool results returned through own Agent request | Yes | Yes | Yes | Yes |
| List Tool configurations | No | No | Yes | Yes |
| Read full Tool configuration | No | No | Yes | Yes |
| Create registered Tool configuration | No | No | Yes | Yes |
| Update display metadata or status | No | No | Yes | Yes |
| List an Agent's Tool assignments | No | No | Yes | Yes |
| Assign or unassign a Tool | No | No | Yes | Yes |

Tool management reuses the existing `AgentAdministratorMembership` boundary.
It does not grant `agent_admin` any Knowledge Base mutation, Membership
administration, Workspace administration, or unrelated system permission.

There is no direct Tool-execution endpoint. All User execution goes through
the existing active Agent route so an employee cannot bypass Agent assignment
or selector policy by addressing a Tool directly.

## 9. Backend-Owned Registry and Adapter Boundary

### 9.1 Registry definition

The application contains an immutable mapping equivalent to:

```text
tool_key
-> canonical selector name and description
-> exact Pydantic argument model
-> exact Pydantic result model, if executable
-> operation_type
-> minimum/default risk
-> immediate-execution permission
-> backend-owned adapter, if Feature 012 may execute it
```

The database configures whether a known capability is available to a
Workspace and Agent. It never supplies an import path, class name, function
name, URL, HTTP method, schema, credential, or executable body.

Registry lookup occurs after the selected persisted Tool is revalidated. An
unknown registry key, risk mismatch, operation mismatch, or missing required
adapter fails closed and makes no enterprise call.

### 9.2 Execution context

Adapters receive a server-built context equivalent to:

```text
ToolExecutionContext(
  workspace_id = authorized route Workspace,
  user_id = authenticated User,
  user_name = authenticated User record,
  user_email = authenticated User record,
  agent_id = already authorized active Agent,
)
```

These values are not selector arguments. Argument models contain no
Workspace, User, Membership, Agent, role, approval, endpoint, or credential
fields.

### 9.3 Adapter result validation

Even project-owned adapter output is validated against the registry result
model before it becomes a public response. Invalid adapter output or adapter
failure returns a sanitized `502`; it is never repaired or completed by a
model.

## 10. Tool Selection Decision

### 10.1 Options compared

| Criterion | A. Native function calling | B. Strict structured output with `tool_key` and arguments |
|---|---|---|
| Safety | Strict per-function schemas; still requires all backend checks | Strict envelope; still requires all backend checks |
| Schema fit | Each eligible Tool has its own canonical argument schema | Heterogeneous arguments require a dynamic union or a generic object followed by validation |
| Simplicity | Small output-item parser plus existing SDK | Reuses existing text parsing, but dynamic per-request union construction is more complex |
| Testability | Narrow injectable provider can return one proposal/no-match | Also easily injectable |
| Current compatibility | Supported by installed official SDK; no dependency | Supported by installed official SDK; no dependency |
| Semantic fit | Explicitly represents a model proposal to call application functionality | Better suited to structured assistant responses or extraction envelopes |
| Portfolio value | Demonstrates native Tool calling while preserving backend policy | Demonstrates structured extraction but less directly the Tool protocol |

### 10.2 Decision

Use native function calling through the existing official OpenAI Responses
SDK, with strict schemas, for the second Tool-selection call.

Official OpenAI documentation distinguishes function calling as the form for
connecting a model to application functionality, while structured text output
is intended for formatting a response. It also documents strict schemas,
required Tool choice, and disabling parallel calls. Sources consulted on
2026-09-27:

- <https://developers.openai.com/api/docs/guides/function-calling>
- <https://developers.openai.com/api/docs/guides/structured-outputs>
- <https://developers.openai.com/api/docs/models/gpt-5.6-terra>

This is a proposal mechanism only. The SDK never invokes application code.
The backend does not send a function result back to the model and does not
continue a model-controlled Tool loop.

### 10.3 Candidate set

The backend supplies function definitions only for Tools that are:

- in the route Workspace,
- assigned to the already authorized Agent,
- active in persistence,
- present in the registry, and
- internally consistent with registry risk metadata.

Definitions use registry-owned descriptions and strict JSON schemas; they do
not use database descriptions. The only additional function is a reserved,
non-executable control function `decline_tool_selection` whose strict argument
is:

```json
{
  "reason": "no_matching_capability"
}
```

where `reason` is exactly one of:

- `no_matching_capability`, or
- `missing_required_arguments`.

This control outcome prevents the model from being forced to misselect a real
capability. Its reason can only reduce capability; it grants no authority and
maps to a stable server-owned `not_executed` response. The name is reserved
and cannot be created as a persisted Tool key.

If the Agent has no active assigned Tools, the backend returns the server-owned
`no_available_tool` outcome without initializing or calling the selector.

### 10.4 Provider call contract

The fixed production call will use:

- model `gpt-5.6-terra`, matching the approved routing tier,
- low reasoning effort,
- prompt version `enterprise-tool-selector-v1`,
- local complete-input budget of 8,000 tokens,
- maximum 512 output/reasoning tokens,
- `tool_choice = "required"`,
- `parallel_tool_calls = false`,
- strict function schemas with `additionalProperties = false`,
- no built-in, custom-text, web, file, computer, or remote MCP tools,
- `store = false`,
- `truncation = "disabled"`,
- no streaming, background mode, conversation, or previous response,
- existing 30-second timeout, and
- zero SDK retries.

Each authorized request makes at most one Feature 012 selector call, and makes
zero when no eligible Tool exists. A routed request with eligible Tools has at
most two model calls in total: the already-approved Feature 011 intent call
and this selector call. No Tool-result/final-response call follows.

Official pricing consulted on 2026-09-27 lists `gpt-5.6-terra` at $2.00 per
million input tokens and $12.00 per million output tokens. At the hard
8,000-input/512-output budgets, the incremental Feature 012 selector ceiling
is approximately $0.0222 per eligible `tool_request` before any caching
discount; typical calls should be lower. Pricing may change, so implementation
documentation must recheck the official model page without changing the
approved model or budgets silently.

The complete local input budget covers fixed instructions, delimited Agent
scope, normalized User request, all eligible registry descriptions/schemas,
the decline control, and relevant output protocol text. Over-budget input
returns sanitized `422` before a provider call.

The backend accepts exactly one completed function-call item. It rejects a
missing call, multiple calls, message text in place of a call, unknown or
duplicate output items, malformed JSON, wrong response/model state, refusal,
or incomplete response with sanitized `502`.

## 11. External-Model Data Boundary

Subject to approval, the Tool-selection request sends only:

- the normalized 1-to-2,000-character User request,
- the Agent `system_prompt` as delimited, untrusted routing-scope data,
- fixed selector instructions,
- stable keys, canonical descriptions, and strict argument schemas for active
  assigned registry Tools, and
- the non-executable decline control definition.

It does not send:

- Workspace, User, Membership, Agent, Tool, Document, or Knowledge Base UUIDs,
- User name, email, role, or authenticated identity,
- database Tool name/description text,
- risk level, approval status, or policy decisions,
- JWTs, API keys, credentials, endpoints, or secrets,
- retrieved Knowledge Base text or citations,
- mock enterprise records or adapter results,
- previous messages, conversation state, or Tool-call history.

Tool results and employee data are never sent to an external model. Feature
012 adds no synthesis call. This both narrows disclosure and prevents the
model from rewriting or fabricating the backend-owned result.

Provider input, raw response, errors, Agent prompt, User request, and proposed
arguments must not be persisted or logged. Sanitized operational logs may
contain only fixed event names and non-sensitive failure categories; Feature
012 does not add execution-log persistence.

## 12. Exact Argument Validation Strategy

### 12.1 Validation chain

Every real Tool proposal follows:

```text
provider function name and JSON arguments
-> exact one-call structural validation
-> selected key exists in the candidate allowlist
-> fresh PostgreSQL User + Workspace + Membership active-state authorization
-> fresh scoped Tool + assignment + active-state resolution
-> registry definition lookup and persisted-risk consistency
-> JSON parse with duplicate/invalid structure rejection
-> exact project-owned Pydantic argument model (`extra = "forbid"`)
-> field normalization and enum/length/range validation
-> Tool-specific business/security validation
-> backend risk/effect policy
-> typed adapter or approval-required handoff
```

The model does not supply the schema. Unknown, extra, missing, null where not
allowed, wrong-type, out-of-range, or invalid-enum values fail closed. There
is no arbitrary JSON pass-through.

### 12.2 Strictness and business validation

Provider strict mode improves structural conformance but is not treated as a
security guarantee. Pydantic validation is repeated locally. Business rules
that do not fit the provider's supported JSON Schema subset are enforced only
by backend code.

The selector is instructed to use `decline_tool_selection` with
`missing_required_arguments` rather than invent required action arguments.
The backend cannot prove that natural-language values were explicitly supplied
merely because a model returned them. Therefore even valid write arguments
remain an untrusted proposal and cannot execute in Feature 012. Feature 013
must present and persist the canonical proposal for human review rather than
treating model extraction as authorization.

## 13. Initial Tool Contracts

### 13.1 `get_reimbursement_status`

Purpose: return the authenticated User's own deterministic mock reimbursement
status.

Registry policy:

- operation type: `read_only`,
- persisted/default risk: `low`,
- immediate execution allowed: yes,
- adapter: project-owned mock reimbursement adapter.

Arguments:

```json
{}
```

`GetReimbursementStatusArguments` has no fields and forbids extras. There is
no User ID, email, employee number, reimbursement owner, Workspace, or request
reference argument. The adapter derives the subject from the authenticated
execution context, so model-supplied identity cannot access another User.

Result:

```json
{
  "type": "reimbursement_status",
  "reimbursement_reference": "REIM-2F40A831",
  "status": "under_review",
  "amount_minor": 12800,
  "currency": "CNY",
  "submitted_on": "2026-09-15",
  "last_updated_on": "2026-09-18"
}
```

Rules:

- `status` is one of `submitted`, `under_review`, `approved`, `rejected`, or
  `paid`.
- Money uses a non-negative integer in minor units, never a binary float.
- Currency is fixed to `CNY` for the MVP mock.
- Dates are validated ISO dates and `last_updated_on` is not before
  `submitted_on`.
- All values come from the mock adapter, never selector output.

### 13.2 `get_employee_information`

Purpose: return only the authenticated User's own deterministic mock employee
profile.

Registry policy:

- operation type: `read_only`,
- persisted/default risk: `low`,
- immediate execution allowed: yes,
- adapter: project-owned mock employee adapter.

Arguments:

```json
{
  "subject": "self"
}
```

`GetEmployeeInformationArguments` requires the literal `subject = "self"`
and forbids extras. This value is a self-service scope marker, not identity;
the adapter still derives the actual subject from authenticated backend
context. Feature 012 intentionally does not support search by name, email,
employee number, or User ID. There is no list or enumeration operation.

The canonical selector definition instructs the model to use
`decline_tool_selection` for a request about another employee. That semantic
choice is not an authorization control: if a faulty or malicious selector
nevertheless proposes `{ "subject": "self" }`, the adapter can return only
the caller's own profile. A foreign name/ID supplied as an argument is an
unknown field or invalid literal and fails before adapter activity.

Result:

```json
{
  "type": "employee_information",
  "name": "Authenticated User",
  "email": "user@example.com",
  "department": "Enterprise Operations",
  "job_title": "Employee",
  "employment_status": "active"
}
```

The adapter receives trusted identity from the backend context. It may use the
authenticated application's name/email as its mock source and supplies the
remaining deterministic profile fields. It cannot receive a foreign subject
from the selector.

### 13.3 `create_it_access_request`

Purpose: validate a proposed IT access request and demonstrate the Feature 013
approval boundary without creating or executing anything.

Registry policy:

- operation type: `write_sensitive`,
- persisted/default risk: `high`,
- immediate execution allowed: no,
- Feature 012 execution adapter: none.

Arguments:

```json
{
  "system": "production_database",
  "access_level": "read_only",
  "business_justification": "Investigate approved production incidents.",
  "duration_days": 14
}
```

Exact argument rules:

- `system`: `production_database`, `analytics_warehouse`, or
  `source_control`.
- `access_level`: `read_only` or `standard`.
- `business_justification`: trimmed 10-to-500-character string; control
  characters are rejected.
- `duration_days`: integer from 1 through 90.
- `production_database` permits only `read_only` in this MVP proposal.
- Unknown and extra fields are rejected.
- No requester, target User, approver, Workspace, credential, or endpoint
  field exists.

After validation, the response is `approval_required` and explicitly
`executed = false`. Feature 012:

- creates no access request in a mock system,
- creates no Approval row,
- produces no approval ID,
- calls no write adapter,
- persists no argument payload, and
- cannot execute later from a client replay.

## 14. Deterministic Mock Enterprise Service

The two executable read Tools call ordinary backend adapters with no network
access. The mock service is the authoritative source of demo business data.

The implementation uses this exact versioned deterministic source; it does not
choose fixture behavior during implementation:

1. Reimbursement bytes are
   `sha256(b"feature012-reimbursement-v1|" + workspace_id.bytes + user_id.bytes).digest()`.
2. `reimbursement_reference` is `REIM-` plus the uppercase hexadecimal form of
   bytes 0 through 3. It contains no literal UUID substring.
3. `status` is selected by `digest[4] % 5` from the ordered tuple
   `submitted`, `under_review`, `approved`, `rejected`, `paid`.
4. `amount_minor` is `10000 + (big_endian_uint16(digest[5:7]) % 50001)`,
   producing CNY 100.00 through 600.00.
5. `submitted_on` is 2026-09-01 plus `digest[7] % 15` days.
6. `last_updated_on` is `submitted_on` plus `1 + digest[8] % 7` days.
7. Every authenticated active User has exactly one latest mock reimbursement
   record; Feature 012 has no no-record branch.
8. Employee bytes are
   `sha256(b"feature012-employee-v1|" + workspace_id.bytes + user_id.bytes).digest()`.
9. Employee `name` and `email` come from the authenticated User record.
10. `digest[0] % 4` selects one paired department/title from, in order:
    `Enterprise Operations / Operations Specialist`,
    `Finance / Finance Analyst`,
    `People / People Coordinator`, and
    `Technology / Software Engineer`.
11. `employment_status` is `active`, because disabled Users are rejected
    before Tool routing.

The service has no clock dependency, randomness, environment-specific seed,
database fixture table, or network access. Raw identifiers are never returned
as business fields. Any change to this versioned mapping after approval is a
contract change requiring spec review.

The key property is provenance, not realism:

```text
validated Agent Tool request
-> typed backend execution context and arguments
-> project-owned mock adapter
-> validated project-owned result
-> public structured outcome
```

Tests inject deterministic recording fakes and assert the selector never
supplies result data. Automated tests need no real ERP, HR, IT, HTTP, DNS, or
OpenAI access.

## 15. Risk and Execution Policy

### 15.1 Fixed taxonomy

- `low`: may execute immediately only when the registry also declares the
  capability read-only and immediate-executable.
- `medium`: never executes in Feature 012; returns `approval_required`.
- `high`: never executes in Feature 012; returns `approval_required`.

Risk is persisted server-owned configuration initialized from the registry.
It is not sent by or accepted from the User or selector. Operation type and
the hard immediate-execution flag remain code-owned registry policy.

### 15.2 Immediate execution predicate

A Tool may execute only when every condition is true:

1. The authenticated User and active Membership were accepted initially and
   freshly revalidated from PostgreSQL after a real Tool proposal.
2. The route Workspace was accepted initially and is still active at that
   final authorization revalidation.
3. The route Agent is active and belongs to that Workspace.
4. The Tool belongs to that Workspace.
5. The Tool is active.
6. The exact Agent-to-Tool assignment still exists.
7. The stable key exists in the registry.
8. Persisted risk matches the registry's required risk.
9. Persisted risk is `low`.
10. Registry operation type is `read_only`.
11. Registry immediate execution is explicitly enabled.
12. Arguments pass exact schema and business validation.
13. A project-owned adapter exists for that key.

Failure of any condition prevents dispatch. In particular,
`create_it_access_request` has no Feature 012 write adapter and cannot execute
even if a database row is manually misconfigured as low risk.

### 15.3 Authorization and capability changes during selection

Tool selection is not a lock or authorization grant. After the external call
returns a real Tool proposal, the service first re-reads the authenticated
User, route Workspace, and User/Workspace Membership from PostgreSQL. The User,
Workspace, and Membership must each still be active. A missing or inactive
record returns the existing generic Workspace access-denied `403`; it does not
reveal which authorization state changed. This check occurs before argument
validation, read-only adapter dispatch, or returning validated
`approval_required` arguments. Adapter identity fields also come from this
fresh User query rather than the earlier FastAPI dependency object.

The service then freshly re-resolves the selected Agent, Tool, and assignment
by route Workspace and active state immediately before dispatch. A Tool found
disabled or unassigned at that final capability revalidation returns a safe
`409` and makes no adapter call.

These checks do not claim to close a state-change race after the final reads.
That residual race is accepted only for deterministic, side-effect-free local
read adapters in Feature 012. Tests simulate changes visible at final
revalidation. Feature 013 must design locking/idempotency and stronger
atomicity for approved writes; Feature 012 does not generalize its read-only
dispatch into a write executor.

## 16. Public Agent Tool Result Contract

The route remains:

`POST /api/workspaces/{workspace_id}/agents/{agent_id}/route`

The request remains unchanged:

```json
{
  "request": "What is the status of my reimbursement request?"
}
```

The browser does not send a Tool key, arguments, User identity, risk, endpoint,
or approval state. An optional `knowledge_base_id` remains syntactically valid
but is ignored without lookup on `tool_request`, exactly as in Feature 011.

### 16.1 Executed read-only result

```json
{
  "request": "What is the status of my reimbursement request?",
  "intent": "tool_request",
  "outcome": {
    "status": "executed",
    "tool": {
      "tool_key": "get_reimbursement_status",
      "name": "Get reimbursement status"
    },
    "executed": true,
    "approval_required": false,
    "validated_arguments": {},
    "result": {
      "type": "reimbursement_status",
      "reimbursement_reference": "REIM-2F40A831",
      "status": "under_review",
      "amount_minor": 12800,
      "currency": "CNY",
      "submitted_on": "2026-09-15",
      "last_updated_on": "2026-09-18"
    },
    "message": "The read-only enterprise capability completed successfully."
  }
}
```

`get_employee_information` uses the same outcome state with its own exact
result discriminator and fields.

### 16.2 Approval-required result

```json
{
  "request": "Request read-only production database access for 14 days to investigate approved incidents.",
  "intent": "tool_request",
  "outcome": {
    "status": "approval_required",
    "tool": {
      "tool_key": "create_it_access_request",
      "name": "Create IT access request"
    },
    "executed": false,
    "approval_required": true,
    "validated_arguments": {
      "system": "production_database",
      "access_level": "read_only",
      "business_justification": "Investigate approved production incidents.",
      "duration_days": 14
    },
    "result": null,
    "message": "This request requires human approval and was not executed."
  }
}
```

The arguments are canonical validated values, not raw provider JSON. They are
shown for transparency only. A later client submission of these values is not
trusted approval or execution authority.

### 16.3 Safe non-executed result

When there is no active assigned Tool or the selector uses the decline
control, return `200 OK`:

```json
{
  "request": "Cancel my corporate card.",
  "intent": "tool_request",
  "outcome": {
    "status": "not_executed",
    "tool": null,
    "executed": false,
    "approval_required": false,
    "reason": "no_matching_tool",
    "validated_arguments": null,
    "result": null,
    "message": "No permitted enterprise capability can safely handle this request."
  }
}
```

Allowed server-owned reasons are:

- `no_available_tool`,
- `no_matching_tool`, and
- `missing_required_arguments`.

Provider failures, malformed calls, authorization failures, stale capability
state, and adapter failures are HTTP errors rather than misleading
`not_executed` product outcomes.

### 16.4 Response invariants

The Tool outcome is a strict server-owned union with cross-field validation:

- `executed` requires `executed = true`, `approval_required = false`, a
  permitted read-only key, exact typed arguments, and matching typed result.
- `approval_required` requires `executed = false`,
  `approval_required = true`, a non-immediate key, canonical validated
  arguments, and `result = null`.
- `not_executed` requires no Tool, no arguments/result, and both booleans
  false.
- Tool/result discriminators must match.
- Unknown keys and result types are rejected.

Normal Users see stable key and display name, not Tool UUID, creator, endpoint,
provider payload, risk internals, or registry implementation details.

## 17. Tool Management API

All endpoints below require active `agent_admin` or `system_admin` Membership
in the route Workspace. Every request model uses `extra = "forbid"`.

The administrative response model is exactly:

```json
{
  "id": "tool-uuid",
  "workspace_id": "workspace-uuid",
  "tool_key": "get_reimbursement_status",
  "name": "Get reimbursement status",
  "description": "Returns the signed-in employee's mock reimbursement status.",
  "operation_type": "read_only",
  "risk_level": "low",
  "status": "disabled",
  "created_by": "user-uuid",
  "created_at": "2026-09-27T10:00:00Z",
  "updated_at": "2026-09-27T10:00:00Z"
}
```

`operation_type` is the registry-derived literal `read_only` or
`write_sensitive`; every other field is persisted. A missing registry
definition or a registry/persisted-risk mismatch returns sanitized `503`
rather than a partial or misleading configuration response.

Shared input rules:

- `tool_key` is not whitespace-normalized; it must already match
  `^[a-z][a-z0-9_]{0,63}$` and one registered non-reserved key.
- `name` is trimmed and contains 1 to 255 characters.
- `description` is trimmed and contains 1 to 5,000 characters.
- `status` is exactly `active` or `disabled`.
- null is rejected for every create/update field.

### 17.1 Create Tool configuration

`POST /api/workspaces/{workspace_id}/tools`

Request:

```json
{
  "tool_key": "get_reimbursement_status",
  "name": "Get reimbursement status",
  "description": "Returns the signed-in employee's mock reimbursement status."
}
```

The backend validates the key against the registry and derives immutable risk
and operation type. Status defaults to `disabled`. Duplicate Workspace/key
returns `409`.

Success: `201 Created` with the exact administrative Tool response above.
Expected errors are `401`, `403`, `409`, `422`, and `503`; a missing route
Workspace is the existing scoped `404`.

### 17.2 List and read Tool configurations

- `GET /api/workspaces/{workspace_id}/tools`
- `GET /api/workspaces/{workspace_id}/tools/{tool_id}`

Both return `200 OK`. The list response is
`list[ToolConfigurationResponse]`, includes active and disabled configurations,
and is ordered by `name` then `id`. The item endpoint returns exactly one
`ToolConfigurationResponse`. A missing or foreign Tool receives the same
scoped `404`. Expected errors are `401`, `403`, `404`, and `503`.

These are administration endpoints; active ordinary members do not need Tool
configuration discovery.

### 17.3 Update Tool configuration

`PATCH /api/workspaces/{workspace_id}/tools/{tool_id}`

Request may contain at least one of:

```json
{
  "name": "Reimbursement status",
  "description": "Updated administrative description.",
  "status": "active"
}
```

`tool_key`, `risk_level`, `operation_type`, Workspace, creator, and timestamps
are not client-settable. The request may contain only `name`, `description`,
and `status`; it must contain at least one, and supplied null is rejected.
Unknown fields, empty PATCH bodies, and shared-rule violations return `422`.

Success: `200 OK` with the exact updated `ToolConfigurationResponse`.
Expected errors are `401`, `403`, `404`, `422`, and `503`. There is no
hard-delete endpoint.

### 17.4 Manage Agent assignments

- `GET /api/workspaces/{workspace_id}/agents/{agent_id}/tools`
- `PUT /api/workspaces/{workspace_id}/agents/{agent_id}/tools/{tool_id}`
- `DELETE /api/workspaces/{workspace_id}/agents/{agent_id}/tools/{tool_id}`

`GET` returns `200 OK` with `list[ToolConfigurationResponse]`, includes active
and disabled assigned Tools, and orders them by `name` then `id`.

`PUT` has no request body. It is idempotent and returns `200 OK` with the exact
assigned `ToolConfigurationResponse` whether the edge was created or already
existed. Duplicate rows are impossible.

`DELETE` has no request body, removes only the relationship, and returns
`204 No Content` with an empty body. It is idempotent when both scoped parents
exist: an already-absent edge also returns `204`. A missing or foreign Agent or
Tool returns the same scoped `404` on `GET`, `PUT`, and `DELETE`.

Expected errors are `401`, `403`, `404`, `422` for malformed path UUIDs, and
`503` for inconsistent registry configuration. The service resolves both
parents within the route Workspace before writing. The database primary and
composite foreign keys enforce uniqueness and same-Workspace consistency.

Assignments may be staged for inactive objects but are effective only while
both Agent and Tool are active.

## 18. Error and Failure Contract

- `401 Unauthorized`: missing or invalid authentication.
- `403 Forbidden`: disabled User, missing/inactive Membership, disabled
  Workspace, or insufficient Tool-management role.
- `404 Not Found`: scoped Workspace, Agent, or administrative Tool resource
  not found; foreign IDs are indistinguishable.
- `409 Conflict`: inactive Agent; duplicate Tool configuration; or a Tool that
  became inactive/unassigned after selection.
- `422 Unprocessable Entity`: client request/management schema validation,
  unknown registry key at administrative creation, or selector input over the
  fixed local budget.
- `502 Bad Gateway`: sanitized selector failure/malformed output, including
  schema-valid proposals that fail Tool business validation; invalid adapter
  output; or mock adapter failure.
- `503 Service Unavailable`: missing selector configuration or inconsistent
  registry/database capability configuration.

No error includes User request text, Agent prompt, proposed arguments,
enterprise result, API key, raw provider body, stack trace, foreign resource
detail, endpoint, or credential.

All invalid model arguments are provider-output failures and return sanitized
`502` without adapter activity, whether they violate JSON/Pydantic structure
or a server-owned business rule. `422` is reserved for the authenticated
client envelope/management request and deterministic local input-budget
failure; it never blames the User for untrusted selector output.

## 19. Feature 011 Integration

The intended orchestration is:

```text
Feature 011 route
-> knowledge_qa
   -> unchanged Knowledge Base context rule
   -> unchanged Feature 009 answer service

-> unsupported
   -> unchanged explicit unsupported outcome

-> tool_request
   -> query active assigned same-Workspace Tool configurations
   -> no eligible Tool: server-owned not_executed; no selector
   -> lazy Feature 012 Tool selector
   -> real proposal: freshly revalidate User + Workspace + Membership access
   -> freshly revalidate selected Agent + Tool + assignment capability
   -> validate exact typed arguments and business rules
   -> low-risk registry read-only Tool: project-owned mock adapter
   -> medium/high/write-sensitive Tool: approval_required, no execution
```

The optional Knowledge Base ID remains unresolved and unqueried throughout
the Tool branch. Tool selection never invokes retrieval, embeddings, grounded
generation, citation handling, or Knowledge Base services.

The new Tool selector must have its own protocol and lazy dependency. It does
not modify or reuse the intent provider interface. Knowledge and unsupported
requests never require selector configuration.

## 20. Feature 013 Handoff

Feature 012 produces an internal typed candidate equivalent to:

```text
ApprovalCandidate(
  workspace_id = authorized route Workspace,
  requester_id = authenticated User,
  agent_id = authorized active Agent,
  tool_id = freshly authorized Tool row,
  tool_key = registry-validated stable key,
  arguments = canonical validated Pydantic model,
  risk_level = backend-owned persisted/registry-checked risk,
)
```

Feature 012 uses this candidate only to construct the public
`approval_required` response. It does not persist, sign, serialize for later
trust, enqueue, or execute it.

Feature 013 must consume the candidate inside the backend after repeating
authorization and capability checks, create its own Approval persistence and
state machine, snapshot canonical arguments and policy context, define
reviewer authorization, add idempotency/concurrency control, and execute only
after an approved decision. It must not trust a client replay of Feature 012
response fields.

Feature 012 does not pre-create an Approval ID or execution-log row.

## 21. Frontend Scope

### 21.1 Decision

Keep Tool administration and Agent assignment API-only. A management UI would
add CRUD forms, assignment state, role-specific navigation, and stale-update
behavior without strengthening the central authorization or execution proof.
The portfolio-critical UI is the existing Assistant showing a real
backend-owned read result versus an explicitly blocked sensitive action.

### 21.2 Assistant changes

Preserve the same:

- Agent route URL and request body,
- active Agent and optional Knowledge Base selectors,
- single-turn non-streaming interaction,
- pending lock and duplicate prevention,
- Workspace reset behavior,
- knowledge and unsupported rendering, and
- normalized HTTP error handling.

For `tool_request`, render typed states only:

- executed reimbursement: capability name, executed badge, reference, status,
  amount/currency, and dates;
- executed employee information: capability name, executed badge, and exact
  own-profile fields;
- IT access request: capability name, `Approval required - not executed`, and
  canonical validated request fields; no approve/reject control and no
  approval ID;
- no permitted match: server-owned non-executed guidance; and
- selector/adapter/configuration or stale-state errors: existing recoverable
  error surface with no stale Tool result.

The frontend never renders arbitrary result JSON or raw provider output and
never infers permission from displayed risk. It branches only on the strict
server contract. Tool outcomes have no citations panel.

Workspace switches clear Tool results. Product and Workspace controls remain
disabled while a route request is pending, and late responses from a previous
Workspace/Agent context cannot render in the new context.

No frontend dependency is added.

## 22. Migration Proposal

After approval, create additive Alembic revision `0008` with
`down_revision = "0007"`.

Upgrade order:

1. Add unique constraint `uq_agents_id_workspace_id` on
   `agents(id, workspace_id)`.
2. Create `tools` with the fields, checks, foreign keys, unique constraints,
   and indexes in Section 6.
3. Create `agent_tools` with the primary key, Workspace FK, composite parent
   FKs, and indexes in Section 7.

The migration:

- does not edit revisions `0001` through `0007`,
- performs no backfill or seed insertion,
- performs no existing-row rewrite,
- creates no endpoint or credential column,
- executes no Tool, and
- runs only against the dedicated test database during automated verification
  unless separately authorized by a human.

Workspace Tool configurations are created through the authorized API, not
seeded into every Workspace by migration.

Downgrade order:

1. Drop `agent_tools`.
2. Drop `tools` and its owned indexes/constraints.
3. Drop `uq_agents_id_workspace_id`.

Downgrade removes only Feature 012-owned schema. It is verified on the
dedicated test database and is not permission to downgrade a non-test
database.

## 23. Acceptance Criteria

### AC-001 - Durable safe Tool configuration

Revision `0008` creates Workspace-owned Tool configuration with stable key,
display metadata, risk, lifecycle, creator, and timestamps, but no endpoint,
URL, credential, import path, or executable database value.

### AC-002 - Explicit Agent capability allowlist

An Agent can use only an explicitly assigned Tool. Composite foreign keys and
service checks prevent cross-Workspace associations; one pair has at most one
assignment.

### AC-003 - Tool management RBAC

Only active `agent_admin` and `system_admin` members can manage Tool
configuration and assignments. Employees and knowledge administrators cannot.
Agent administrators gain no adjacent Knowledge Base, Membership, or
Workspace administration rights.

### AC-004 - Active-state enforcement

Only an active Agent with an active, assigned, same-Workspace Tool can reach
selection and dispatch. Disabled states retain configuration but have no
effective capability.

### AC-005 - Narrow validated selection

The second provider receives only eligible registry definitions and minimized
request/scope data. Exactly one strict function proposal or decline control is
accepted. Unknown, unassigned, inactive, cross-Workspace, malformed, or stale
selections fail closed.

### AC-006 - Exact argument ownership

Every Tool key maps to a project-owned Pydantic argument model and business
validator. Unknown/extra/missing/invalid values are never forwarded. Identity,
authorization, risk, endpoints, and secrets are not Tool arguments.

### AC-007 - Reimbursement result provenance

`get_reimbursement_status` uses authenticated identity and a backend-owned
read-only mock adapter. The model cannot choose another subject or fabricate
the returned business result.

### AC-008 - Employee self-service boundary

`get_employee_information` returns only the authenticated User's own mock
profile. Its only scope marker is the literal `subject = "self"`; actual
identity remains backend-derived. It cannot enumerate or retrieve another User
or Workspace. A third-party request is expected to decline, while even a
faulty selection can return only the caller's profile.

### AC-009 - Sensitive action remains blocked

`create_it_access_request` may be selected and validated but always returns
`approval_required` and `executed = false`. No Approval row, enterprise write,
write adapter call, approval ID, or execution log is created.

### AC-010 - Risk defense in depth

Only persisted low-risk plus registry-declared read-only and explicitly
immediate-enabled capabilities execute. Medium/high and every write-sensitive
capability remain unexecuted. Database misconfiguration cannot make the IT
request execute.

### AC-011 - Strict public contract

The Agent route preserves the top-level Feature 011 intent union and returns a
strict Tool outcome that distinguishes executed, approval-required, and safe
non-executed states without raw provider output or prominent internal IDs.

### AC-012 - No Tool-result model disclosure

Tool results and employee data are returned directly from validated adapters.
They are never sent to a second model and no model-generated prose can alter
them.

### AC-013 - Feature 011 regression safety

Knowledge and unsupported branches remain unchanged, do not initialize the
Tool selector, and do not query Tool persistence. Tool branches never query a
Knowledge Base even when a valid UUID is supplied.

### AC-014 - Minimal Assistant demonstration

The existing Assistant renders typed read-only results and an explicit
approval-required/not-executed state, preserves pending/reset/stale-response
protections, and adds no Tool administration or approval-review UI.

### AC-015 - Offline automated verification

Required backend and frontend tests use fake selector providers and mock or
recording adapters. They require no live OpenAI call, enterprise system, DNS,
or network.

## 24. Test Requirements

### 24.1 Migration and model

- Upgrade `0007 -> 0008`, downgrade, re-upgrade, single Alembic head, and
  schema-drift checks.
- Exact Tool fields, defaults, checks, indexes, unique constraints, and FKs.
- Added Agent composite unique constraint.
- `agent_tools` primary key and both composite same-Workspace FKs.
- Cross-Workspace association rejected at database level.
- Duplicate Workspace/key and duplicate Agent/Tool assignment rejected.
- Invalid key, blank name/description, invalid risk/status rejected.
- No `endpoint` or persisted executable `tool_type` column.
- No changes to migrations `0001` through `0007`.
- Downgrade removes only Feature 012-owned objects.

### 24.2 Tool management and RBAC

- `401` for missing/invalid authentication.
- Disabled User, Workspace, and inactive/missing Membership denial.
- Employee and knowledge-admin denial for every management/assignment route.
- Agent-admin and system-admin create/list/read/update/assign/unassign success.
- Per-Workspace role resolution for one User with different roles.
- Regression proof that `agent_admin` cannot mutate Knowledge Bases or manage
  Memberships.
- Creator is authenticated User and cannot be client-supplied.
- Unknown registry key rejected; risk and operation type cannot be client-set.
- New Tool defaults disabled; activation/disable/re-enable behavior.
- Exact administrative response keys, registry-derived operation type, and
  list ordering by name then ID.
- Name/description trimming and 1-to-255/1-to-5,000 length limits; null,
  unknown fields, immutable-field writes, and empty PATCH rejection.
- Scoped indistinguishable missing/foreign Agent and Tool responses.
- Same-Workspace assignment, exact assigned-list contents/order, idempotent
  bodyless PUT, uniqueness, and bodyless unassign.
- DELETE returns empty `204` both for an existing edge and an already-absent
  edge when both scoped parents exist; missing/foreign parents return `404`.
- Assignments retained while Agent or Tool is inactive.
- Exact documented success and error status codes for every management route.
- No hard-delete or direct-execute route.

### 24.3 Ordering, isolation, and effective capability

- Workspace/Membership/Agent/request checks occur before selector or adapter
  initialization/calls.
- Agent `draft`/`disabled` returns `409` before Tool query/selector activity.
- Tool must be same-Workspace, active, and assigned.
- No active assigned Tools returns `no_available_tool` with no selector call.
- Cross-Workspace Agent/Tool combinations fail closed in service and database.
- Disabled Tool is excluded and cannot execute.
- Unassigned Tool is never supplied to the selector.
- Tool disabled/unassigned and visible as such at final post-selection
  revalidation returns `409` and no adapter call; tests do not claim to close
  a state change after that final read.
- A real proposal triggers a fresh PostgreSQL read of authenticated User,
  route Workspace, and Membership state before capability revalidation,
  argument disclosure, or adapter dispatch.
- User, Workspace, or Membership revocation while selection is in flight
  returns the same generic Workspace access-denied `403`, with active Agent,
  Tool, and assignment controls proving caller authorization caused denial.
- Caller authorization loss blocks both read adapter execution and the
  `approval_required` response, so validated sensitive arguments are not
  returned after access is revoked.
- Foreign IDs are never disclosed in normal User outcomes.
- Knowledge and unsupported intents make no Tool query, selector, adapter,
  approval, or mock-service call.
- Tool intent makes no Knowledge Base, retrieval, embedding, or grounded
  generation call with omitted, valid, missing, foreign, or disabled
  Knowledge Base UUID.

### 24.4 Selector provider

- Specific selection for each of the three registered Tools.
- Candidate definitions contain only active assigned registry Tools plus the
  decline control.
- Provider input contains only approved external-boundary fields.
- Provider input excludes all IDs, identity, roles, risk, endpoints, secrets,
  database descriptions, Knowledge Base data, and enterprise results.
- `store=false`, required choice, no parallel calls, strict schemas, no
  streaming/background/conversation/retries, fixed model/limits.
- At most one Feature 012 selector call for a routed request with eligible
  Tools, zero when none are eligible, and no post-result synthesis call.
- Hard-budget cost-ceiling calculation matches the documented official
  per-token rates; tests assert budgets/call count, not a mutable dollar price.
- Local complete-input budget enforced before provider call.
- Decline for no match and missing required arguments maps to stable
  non-executed outcomes.
- Malformed, missing, extra, duplicate, multiple, unknown, refusal, incomplete,
  wrong-model, and non-function provider outputs return sanitized `502`.
- Provider timeout/rate/unavailable failure returns sanitized `502`.
- Missing provider configuration returns `503`.
- Unknown Tool key, inactive Tool, and unassigned Tool fail closed.
- Provider errors/logs contain no request, prompt, arguments, secrets, or raw
  response body.

### 24.5 Arguments, policy, and adapters

- Each Tool uses its exact server-owned Pydantic argument model.
- Extra, missing, null, wrong-type, invalid-enum, overlength, and out-of-range
  arguments fail closed with sanitized `502` before adapter activity.
- Business validation rejects invalid date/order or prohibited IT access
  combinations with sanitized `502` before adapter activity.
- Model-supplied Workspace/User/employee/requester/endpoint/secret fields are
  rejected as extras.
- `get_reimbursement_status` succeeds read-only using authenticated identity.
- No model-supplied identity can access another User's status.
- `get_employee_information` accepts only `subject = "self"` and succeeds for
  the authenticated profile only.
- A normal fake selector declines explicit third-party employee requests; a
  malicious fake selecting `subject = "self"` still returns only the caller's
  profile; a foreign name/ID argument is rejected and no path can enumerate
  records.
- Exact reimbursement digest/status/amount/date mapping and employee
  department/title mapping are deterministic across calls, have no
  clock/randomness/network dependency, and expose no raw identifier substring.
- Both read Tools use only the backend-owned adapter selected by registry.
- Adapter receives authorized context and typed args, not raw provider JSON.
- Adapter output is validated; malformed output and exceptions return
  sanitized `502`.
- Tool output is never accepted from or fabricated by the model.
- Persisted/registry risk mismatch returns `503` without dispatch.
- Medium/high and write-sensitive capabilities never execute.
- `create_it_access_request` returns validated arguments and
  `approval_required`, but creates no row/log/ID and makes no adapter call.
- No Tool output or employee data is sent to a model.
- No arbitrary URL/HTTP execution is reachable.

### 24.6 Public API schemas

- Strict executed reimbursement and employee variants.
- Strict approval-required IT variant.
- Strict no-available/no-match/missing-arguments variants.
- Cross-field rejection for mismatched status, booleans, Tool key, arguments,
  and result discriminator.
- Responses expose no Tool UUID or raw provider content to normal Users.
- Existing knowledge and unsupported response contracts regress unchanged.

### 24.7 Frontend

- Route URL, Bearer header, and request bodies remain exact with and without
  `knowledge_base_id`.
- Browser never supplies Tool key, arguments, identity, risk, endpoint, or
  approval fields.
- Successful reimbursement result renders selected capability, executed state,
  and exact structured fields.
- Successful employee result renders only own-profile fields.
- IT access result renders `Approval required - not executed`, canonical
  fields, no success state, no approval ID, and no review action.
- Safe no-match/no-available/missing-argument outcomes render server guidance.
- Provider/adapter/configuration/network errors show no stale Tool result and
  retain the request for retry where authentication remains valid.
- Disabled/stale Agent/Tool `409` state is explicit and recoverable.
- `401`, `403`, `404`, `409`, `422`, `502`, and `503` behavior remains
  distinguished.
- Pending state disables request, Agent, Knowledge Base, Workspace, and
  product-area controls and prevents duplicate submit.
- Workspace switch after completion clears Agent/Knowledge Base selection,
  request, Tool result, and errors.
- Late Tool response from a forced old-Workspace remount cannot render in the
  new Workspace.
- Knowledge and unsupported UI regress unchanged.

### 24.8 Verification after approval

- Feature-specific PostgreSQL integration tests.
- Full backend `pytest` against the dedicated PostgreSQL test database with no
  skipped required tests.
- Backend Ruff checks.
- Alembic head, upgrade/downgrade, and schema-drift checks.
- Full frontend tests, lint, and production build.
- `git diff --check`.
- Independent review before merge because the feature changes schema,
  authorization, tenant isolation, external model data, and Tool execution.

## 25. Out of Scope

- Approval table or Approval row creation.
- Approver assignment, approval decisions, cancellation, or review UI.
- Execution after approval.
- Execution-log persistence or audit dashboard.
- Real ERP, HR, IT, database, SaaS, HTTP, webhook, or MCP integrations.
- Arbitrary URL, host, endpoint, method, header, credential, or secret config.
- Any real write operation, including a mock IT request record.
- Generic Tool marketplace or user-authored executable Tools.
- Tool administration or Agent-assignment frontend.
- A second LLM synthesis call over Tool output.
- Conversation/message persistence, history, streaming, or multi-turn memory.
- Parameter-collection dialogue or workflow UI.
- Workflow engine, queue, scheduler, or background execution.
- Multi-Agent collaboration.
- RAG changes, retrieval tuning, or Knowledge Base/Tool coupling.
- LangGraph or another broad Agent framework.
- Feature 014 evaluation/log dashboard.
- Deployment work.
- Hard deletion of Tools or Agents.
- New roles or changes to existing Membership role values.

## 26. Required Human Approval Gate

Before implementation, a human must approve all of the following:

1. **Migration:** create additive revision `0008`, add
   `uq_agents_id_workspace_id`, and create the `tools` and `agent_tools`
   objects exactly within Sections 6, 7, and 22. Do not modify revisions
   `0001` through `0007`, execute destructive operations, seed Workspaces, or
   migrate a non-test database.
2. **Persistence boundary:** omit `endpoint` and persisted executable
   `tool_type`; use stable `tool_key` only as lookup input to a fixed
   project-owned registry. Update `DATABASE.md` to replace its draft Tool
   model and resolve the Agent-to-Tool open question.
3. **Capability relationship:** require the explicit persisted same-Workspace
   Agent-to-Tool assignment and preserve assignments across disabled states;
   add no implicit every-Tool access.
4. **Authorization:** reuse `agent_admin`/`system_admin` for Tool and assignment
   management; allow all active roles to use eligible Tools through active
   Agents; grant no adjacent administrative privilege and add no direct
   execute endpoint.
5. **Selector:** add a second lazy OpenAI Responses call only after validated
   `tool_request`; use native strict function calling, required single choice,
   disabled parallel calls, eligible registry definitions plus the reserved
   decline control, and the fixed configuration in Section 10. Permit at most
   one Feature 012 selector call, zero SDK retries, and no post-Tool call. At
   pricing checked 2026-09-27, approve the approximately $0.0222 incremental
   ceiling at the 8,000-input/512-output hard budgets; recheck official pricing
   before implementation without silently changing model or limits.
6. **External data:** send only normalized request, delimited Agent scope,
   fixed instructions, and canonical definitions/schemas for active assigned
   Tools. Send no identities, IDs, roles, risk, secrets, database descriptions,
   Knowledge Base data, or enterprise results. Use `store=false`, zero retries,
   and no conversation state.
7. **Arguments and identity:** use exact project-owned Pydantic schemas and
   business rules; derive all identity/authorization context from the backend;
   reject arbitrary JSON and unknown/extra fields.
8. **Registry and adapters:** resolve only the three approved stable keys to
   project-owned definitions. Add no generic HTTP executor or external
   service. Use the exact versioned deterministic mock mapping in Section 14
   and validate adapter output before response.
9. **Risk/execution:** immediately execute only low-risk, registry-declared
   read-only `get_reimbursement_status` and `get_employee_information` mock
   adapters. Medium/high/write-sensitive Tools never execute.
10. **Sensitive action:** permit `create_it_access_request` selection and
    validation only; return `approval_required` and create no Approval row,
    external/mock write, write-adapter call, execution log, or approval ID.
11. **Result boundary:** return strict structured server-owned results without
    a second model call; never send Tool output or employee data back to a
    model.
12. **Frontend:** update only the Assistant Tool outcome presentation and
    typed client/tests; keep administration API-only and add no Feature 013
    review UI.
13. **Dependencies/framework:** add no runtime dependency, LangGraph, broad
    Agent framework, remote mock service, queue, or workflow engine.

Approval of this proposal authorizes scoped implementation and creation of
migration file `0008` plus execution against the dedicated test database only.
It does not authorize a non-test migration, real external integration, real or
mock write execution, Feature 013 work, merge to `main`, or any destructive
database operation.

Approval recorded 2026-09-27: the human maintainer approved all thirteen
items above against Issue #27 and Phase A baseline commit `743f3b9`. The
authorization remains limited to this Feature 012 scope and the dedicated
test database.

Independent-review remediation recorded 2026-09-27: after a real selector
proposal, Feature 012 now freshly revalidates active User, Workspace, and
Membership state from PostgreSQL before capability revalidation, argument
disclosure, or read-only dispatch. This closes the reported selector-flight
authorization window without adding locks, long-running transactions, write
execution, or Feature 013 behavior. The documented residual race after the
final reads remains accepted only for deterministic side-effect-free adapters.
