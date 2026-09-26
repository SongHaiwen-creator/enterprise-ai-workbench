# Feature 011 - Agent and Intent Routing

Status: Proposed - awaiting human approval
Milestone: 3

## 1. Goal

Move the product from a dedicated Knowledge Q&A experience toward a
Workspace-scoped enterprise Agent that determines how a User request should be
handled:

```text
User request
-> authenticated active Workspace Membership
-> active Agent
-> validated intent routing
-> knowledge_qa | tool_request | unsupported
```

Feature 011 introduces Agent configuration and routing, but it never selects or
executes an enterprise tool. A `knowledge_qa` request reuses the Feature 009
grounded-answer capability. A `tool_request` returns a fixed, non-executed
outcome. A request outside the configured Agent scope returns an explicit
`unsupported` outcome.

## 2. Phase A Decision Summary

This proposal requires human approval before implementation because it adds:

- Alembic revision `0007` and the new `agents` table,
- an additive Agent-management authorization policy, and
- a new external-model data boundary for intent classification.

The proposed implementation adds no new runtime dependency and no broad Agent
framework. It reuses the existing official OpenAI Python SDK, Pydantic,
`tiktoken`, FastAPI service structure, Workspace authorization dependencies,
and Feature 009 grounded-answer service.

Implementation, migration creation, and application-code changes must not
begin until the approval terms in Section 18 are accepted.

## 3. Scope

After approval, this feature will:

- Add the Workspace-owned Agent persistence model through Alembic revision
  `0007`.
- Let `agent_admin` and `system_admin` members create Agent configurations,
  update their name, description, system prompt, and status, and enable or
  disable them.
- Let any active Workspace member list Agent summaries and submit a request to
  an active Agent.
- Accept exactly one authorized Knowledge Base as runtime context for each
  Agent request.
- Classify each accepted request into the closed taxonomy `knowledge_qa`,
  `tool_request`, or `unsupported` through a narrow routing provider.
- Validate the provider result against a strict server-owned schema before it
  influences control flow.
- Route `knowledge_qa` through the existing Feature 009
  `answer_question` service without duplicating retrieval, generation, or
  citation logic.
- Return a fixed `tool_request` result that states an enterprise capability is
  required and that nothing was executed.
- Return a fixed explicit result for requests outside the configured Agent
  scope.
- Add a separate Assistant frontend surface for the three outcomes while
  preserving the Feature 010 Knowledge Q&A specialist interface.
- Add unit, PostgreSQL integration, and mocked frontend tests that make no live
  OpenAI calls.

## 4. Existing Foundation and Reuse Decision

### 4.1 Components reused

Feature 011 reuses:

- `ActiveWorkspaceMembership` for authentication, active Workspace checks,
  active Membership checks, and per-Workspace role resolution.
- The existing Workspace-scoped Knowledge Base service and authorization
  rules.
- `answers.answer_question` as the only knowledge-answer orchestration path.
- Feature 008 retrieval eligibility and isolation rules.
- Feature 009 grounded generation, unsupported-evidence behavior, and
  server-verifiable citations.
- The existing official `openai>=3.8,<4.0` SDK, Pydantic, and `tiktoken`.
- The frontend's in-memory Bearer session, Workspace selector, API error
  normalization, and citation presentation patterns.

The Agent route must not query Chunks or Documents directly and must not call
the answer HTTP endpoint internally. It invokes the existing answer service in
the same backend process after routing and authorization.

### 4.2 Infrastructure evaluation

| Candidate | Functional fit | License / maintenance | Integration and deployment | Decision |
|---|---|---|---|---|
| Existing FastAPI services plus official OpenAI SDK structured parsing | The feature needs one classification step followed by one existing service call | Existing active Apache-2.0 SDK; no added package | Small, testable boundary that preserves backend-owned authorization and routing | Use |
| LangGraph | Useful for durable, branching, multi-step Agent workflows | Active MIT project, but introduces another framework lifecycle | Unnecessary for a three-value classification with no tool execution, memory, checkpointing, or workflow graph | Do not add |
| Full LangChain or LlamaIndex Agent stack | Can model routing and tools | Active MIT projects with a broad dependency surface for this requirement | Would duplicate project-owned retrieval and introduce Feature 012 concepts early | Do not add |
| Raw provider HTTP client | Can request structured classification | Project-owned commodity integration | Reimplements authentication, timeout, errors, retries, and response parsing already supplied by the SDK | Reject |
| Keyword or regular-expression router | Has no external call | Project-owned | Cannot robustly distinguish enterprise knowledge, personalized business-system state, and out-of-scope requests | Reject |

No new significant runtime framework or dependency is justified. Feature 012
may reassess orchestration needs only if concrete tool execution introduces a
requirement the current service structure cannot meet.

Repository metadata consulted on 2026-09-26:

- <https://github.com/openai/openai-python>
- <https://github.com/langchain-ai/langgraph>
- <https://github.com/langchain-ai/langchain>
- <https://github.com/run-llama/llama_index>

## 5. Product Behavior

### 5.1 Request flow

```text
Assistant request
-> authenticate User
-> require active Membership in active route Workspace
-> load Agent by both route Workspace ID and Agent ID
-> require Agent status active
-> validate one active, route-Workspace Knowledge Base supplied as context
-> classify normalized request through validated routing provider
   -> knowledge_qa: call existing grounded-answer service with request Knowledge Base
   -> tool_request: return fixed not-executed outcome
   -> unsupported: return fixed unsupported outcome
```

Authorization and tenant checks happen before any provider request. The model
never decides whether a User is allowed to access a Workspace, Agent, Knowledge
Base, Document, or future Tool.

### 5.2 Routing taxonomy

- `knowledge_qa`: a policy, procedure, or enterprise-knowledge question that
  should be answered from the request's authorized Knowledge Base context.
- `tool_request`: a request that needs current or personalized business-system
  data, or asks for an enterprise action, and therefore requires a future
  enterprise Tool.
- `unsupported`: a request outside the Agent's configured enterprise scope or
  outside the three supported Feature 011 behaviors.

The router does not fall back to `knowledge_qa` for every unrecognized request.
The public API exposes no model-generated confidence score or probability.
"Deterministic" describes the closed schema, validation, and server-owned
branch behavior; it does not present model classification as perfectly
repeatable or probabilistically calibrated.

### 5.3 Distinct unsupported meanings

The following states remain distinct:

- Top-level `intent = unsupported`: the request is outside the configured
  Agent capability.
- Top-level `intent = knowledge_qa` with nested Feature 009
  `status = unsupported`: the request is a knowledge question, but authorized
  retrieval did not provide sufficient evidence.
- Provider or application failure: an error response, never mislabeled as an
  unsupported product outcome.

### 5.4 No tool execution

For `tool_request`, the backend returns a server-owned response containing:

- `status = not_executed`,
- `required_capability = enterprise_tool`, and
- a stable message explaining that Feature 011 did not execute an action.

No Tool table, registry, schema, provider tool definition, tool name, tool ID,
arguments, business result, approval, or execution log is created. The routing
provider returns only an intent and cannot fabricate reimbursement status,
employee information, request state, or other business data.

## 6. Agent Knowledge Context Decision

### 6.1 Options considered

| Option | Benefits | Costs / risks |
|---|---|---|
| A. Associate each Agent with one authorized Knowledge Base | Stable context and a request containing only User text | Invents a relationship absent from `DATABASE.md`; adds a column, composite constraint, and lifecycle rules; couples future tool-only Agents to knowledge |
| B. Accept one Knowledge Base ID at request time | Matches the existing Agent data model and answer-service signature; reuses the authorized Feature 010 selector; adds no extra relationship | Every caller must choose one context and tool/unsupported requests carry an unused context ID |
| Multi-Knowledge-Base retrieval | Broader coverage | Requires selection/ranking/permission semantics not demonstrated by the MVP |

### 6.2 Decision

Use option B: every Feature 011 request carries exactly one
`knowledge_base_id` selected from the current Workspace's authorized Knowledge
Base list.

The backend resolves the ID with the route `workspace_id` and requires the
Knowledge Base to be active before routing. The ID is never sent to the
routing provider. A `knowledge_qa` result passes the same server-validated ID
to Feature 009; `tool_request` and `unsupported` do not query it further.

This matches the Agent table already planned in `DATABASE.md`, reuses the
existing answer-service boundary, and avoids inventing a persisted association
or multi-Knowledge-Base retrieval. Requiring one context in Feature 011 keeps
the API strict; making it optional for future tool-only Agents can be a
backward-compatible change when Feature 012 defines that need.

## 7. Business Rules

### BR-001 - Workspace ownership and isolation

An Agent belongs to exactly one Workspace. Every Agent lookup must include both
the route `workspace_id` and `agent_id`. Every runtime Knowledge Base lookup
must include the same route `workspace_id` and the request's
`knowledge_base_id`.

Cross-Workspace Agent and Knowledge Base identifiers return the scoped
not-found response and must not disclose foreign resource details.

### BR-002 - Agent status

Supported statuses are:

- `draft`: configurable but not usable,
- `active`: usable by active Workspace members, and
- `disabled`: retained and configurable but not usable.

New Agents default to `draft`. Enabling means changing status to `active`;
disabling means changing it to `disabled`. Hard deletion is not supported.

Submitting a request to a `draft` or `disabled` Agent returns `409 Conflict`
without calling any AI provider.

### BR-003 - Management access

Creating, reading full configuration, or updating an Agent requires an active
Membership with role:

- `agent_admin`, or
- `system_admin`.

Employees and knowledge administrators cannot manage Agent configuration.
Agent administrators do not gain Knowledge Base mutation, Membership
administration, or system-administration permissions.

### BR-004 - Use access

Any authenticated User with an active Membership in an active Workspace may:

- list active Agent summaries in that Workspace, and
- submit a request to an active Agent with one active, same-Workspace
  Knowledge Base as runtime context.

`agent_admin` and `system_admin` may additionally request inactive summaries
for configuration management. Employees and knowledge administrators cannot
use that management view.

Summary responses do not expose `system_prompt`. Frontend visibility is only a
usability control; every management and use permission is enforced by the
backend.

### BR-005 - Creator and validation

`created_by` is always the authenticated User and cannot be supplied by the
client.

- `name` is trimmed and contains 1 to 255 characters.
- `description` is optional, trimmed, and contains at most 5,000 characters.
- PATCH may set `description` to `null` to clear it; `name`, `system_prompt`,
  and `status` cannot be set to `null`.
- `system_prompt` is trimmed and contains 1 to 8,000 characters.
- Unknown fields are rejected.
- A PATCH body must contain at least one supported field.
- Agent names need not be unique in the MVP.

System prompts are configuration, not secret storage. They must not contain
API keys, credentials, or protected business records.

### BR-006 - Routing provider boundary

The routing provider accepts only:

- the normalized User request,
- the configured Agent system prompt, and
- fixed server-owned routing instructions and output schema.

It returns only one of the three intent enum values. It receives no Workspace,
User, Membership, role, Knowledge Base, Document, Chunk, or future Tool IDs; no
JWT, API key, filename, citation, retrieved text, or business-system data; and
no previous message or conversation state.

Provider output is untrusted. Pydantic parsing and explicit enum validation
must complete before control flow branches. The provider cannot return or
control authorization decisions, database identifiers, Tool selection,
arguments, public messages, or business results.

Fixed server instructions delimit both the system prompt and User request as
data. Neither value can replace the taxonomy, enable tools, broaden provider
access, or authorize a resource.

### BR-007 - Knowledge route reuse

After a validated `knowledge_qa` result, the Agent service calls the existing
Feature 009 `answer_question` service with:

- the authorized route Workspace ID,
- the request's already validated Knowledge Base ID,
- the normalized User request,
- the existing embedding provider, and
- the existing grounded-generation provider.

Feature 011 does not change Top-K, retrieval filters, generation prompts,
grounding rules, citation validation, or unsupported-evidence behavior. The
Agent system prompt is not inserted into Feature 009 grounded generation.

### BR-008 - External request behavior

The routing request uses the existing official OpenAI SDK with:

- fixed model `gpt-5.6-terra`,
- strict structured parsing,
- `store = false`,
- no tools, web search, file search, streaming, background mode, or previous
  response,
- disabled truncation,
- low reasoning effort,
- a hard 8,000-token locally counted input budget covering the complete fixed
  instructions, delimited Agent prompt, delimited User request, and strict
  output schema before the call,
- at most 64 output tokens,
- the existing 30-second timeout, and
- zero SDK retries.

No caller can override the model, prompt version, budgets, or provider
settings.

### BR-009 - Failure behavior

- Missing routing configuration returns `503 Service Unavailable`.
- Provider timeout, rate limit, refusal, incomplete output, model mismatch, or
  malformed output returns sanitized `502 Bad Gateway`.
- Input above the local routing budget returns `422 Unprocessable Entity`
  without a provider call.
- No routing failure is converted to `unsupported`.
- Errors and logs must not contain the User request, Agent system prompt, API
  key, raw provider response, provider error body, or stack trace.
- No automatic retry is added.

Feature 008 embedding and Feature 009 generation errors retain their existing
status codes and sanitized behavior on the knowledge path.

## 8. Authorization Matrix

| Operation | Employee | Knowledge admin | Agent admin | System admin |
|---|---:|---:|---:|---:|
| List active Agent summaries | Yes | Yes | Yes | Yes |
| Include draft/disabled summaries | No | No | Yes | Yes |
| Use an active Agent | Yes | Yes | Yes | Yes |
| Read full Agent configuration | No | No | Yes | Yes |
| Create Agent | No | No | Yes | Yes |
| Update prompt or status | No | No | Yes | Yes |

All entries also require an active User, active Workspace, and active
Membership in the route Workspace.

## 9. Database and Migration Proposal

Alembic revision `0007` will have `down_revision = "0006"`. Revisions `0001`
through `0006` remain unchanged.

Table: `agents`

| Field | Type | Rules |
|---|---|---|
| `id` | UUID | Primary key, generated by PostgreSQL |
| `workspace_id` | UUID | Required FK to `workspaces.id`, `ON DELETE RESTRICT` |
| `name` | VARCHAR(255) | Required, non-empty after trimming |
| `description` | TEXT | Nullable |
| `system_prompt` | TEXT | Required, non-empty after trimming |
| `status` | VARCHAR(32) | Required; `draft`, `active`, or `disabled`; default `draft` |
| `created_by` | UUID | Required FK to `users.id`, `ON DELETE RESTRICT` |
| `created_at` | TIMESTAMPTZ | Required, database default current timestamp |
| `updated_at` | TIMESTAMPTZ | Required, database default current timestamp |

Indexes and constraints:

- primary key on `id`,
- index `ix_agents_workspace_id`,
- index `ix_agents_created_by`,
- status-value check constraint,
- non-empty `name` and `system_prompt` check constraints,
- foreign keys for `workspace_id` and `created_by`.

The migration creates only Feature 011-owned objects. It performs no backfill,
data rewrite, destructive operation, or cascade deletion. Downgrade drops only
the `agents` table and its owned constraints/indexes.

## 10. API / Data Contract

### 10.1 Create Agent

`POST /api/workspaces/{workspace_id}/agents`

Authorization: active `agent_admin` or `system_admin`.

Request:

```json
{
  "name": "Employee Service Assistant",
  "description": "Routes policy questions and enterprise service requests.",
  "system_prompt": "Support employees with approved policy and service topics."
}
```

Success: `201 Created` with `AgentConfigurationResponse`. Status is
server-owned and defaults to `draft`.

### 10.2 List Agent summaries

`GET /api/workspaces/{workspace_id}/agents?include_inactive=false`

Authorization: any active Workspace member.

Success: `200 OK` with `list[AgentSummaryResponse]`.

`include_inactive` defaults to `false`, returning active Agents only. Setting
it to `true` returns active, draft, and disabled summaries and requires an
active `agent_admin` or `system_admin`; other roles receive `403`.

Results are ordered by `name` and then `id`. A summary contains:

```json
{
  "id": "agent-uuid",
  "workspace_id": "workspace-uuid",
  "name": "Employee Service Assistant",
  "description": "Routes policy questions and enterprise service requests.",
  "status": "active",
  "created_by": "user-uuid",
  "created_at": "2026-09-25T10:00:00Z",
  "updated_at": "2026-09-25T10:00:00Z"
}
```

The summary never includes `system_prompt`.

### 10.3 Read full Agent configuration

`GET /api/workspaces/{workspace_id}/agents/{agent_id}`

Authorization: active `agent_admin` or `system_admin`.

Success: `200 OK` with `AgentConfigurationResponse`, containing every summary
field plus `system_prompt`:

```json
{
  "id": "agent-uuid",
  "workspace_id": "workspace-uuid",
  "name": "Employee Service Assistant",
  "description": "Routes policy questions and enterprise service requests.",
  "system_prompt": "Support employees with approved policy and service topics.",
  "status": "draft",
  "created_by": "user-uuid",
  "created_at": "2026-09-25T10:00:00Z",
  "updated_at": "2026-09-25T10:00:00Z"
}
```

### 10.4 Update Agent

`PATCH /api/workspaces/{workspace_id}/agents/{agent_id}`

Authorization: active `agent_admin` or `system_admin`.

Any subset of the following may be supplied, with at least one field required:

```json
{
  "name": "Employee Operations Assistant",
  "description": "Updated scope",
  "system_prompt": "Updated routing scope and behavior.",
  "status": "active"
}
```

`description: null` clears the optional description. The other fields cannot
be null. Success: `200 OK` with `AgentConfigurationResponse`.

### 10.5 Submit an Agent request

`POST /api/workspaces/{workspace_id}/agents/{agent_id}/route`

Authorization: any active Workspace member. The Agent must be active.

Request:

```json
{
  "request": "What is the travel reimbursement limit?",
  "knowledge_base_id": "knowledge-base-uuid"
}
```

`request` is trimmed and contains 1 to 2,000 characters.
`knowledge_base_id` is required and must identify an active Knowledge Base in
the route Workspace. Unknown fields are rejected. Context validation occurs
before the routing provider call, but the identifier is not included in model
input.

Knowledge route response: `200 OK`

```json
{
  "request": "What is the travel reimbursement limit?",
  "intent": "knowledge_qa",
  "outcome": {
    "question": "What is the travel reimbursement limit?",
    "status": "answered",
    "answer": "The travel reimbursement limit is ...",
    "message": null,
    "citations": [
      {
        "document_id": "document-uuid",
        "file_name": "travel-policy.md",
        "document_version": 1,
        "chunk_id": "chunk-uuid",
        "chunk_index": 3,
        "excerpt": "...verified excerpt..."
      }
    ],
    "generation": {
      "model": "gpt-5.6-terra",
      "reasoning_effort": "low",
      "retrieval_limit": 5,
      "prompt_version": "grounded-answer-v1",
      "max_input_tokens": 12000,
      "max_output_tokens": 1200,
      "input_tokens": 1540,
      "output_tokens": 210,
      "total_tokens": 1750
    }
  }
}
```

The nested outcome is the existing Feature 009 response contract. It may have
`status = unsupported` when evidence is insufficient while the top-level
intent remains `knowledge_qa`.

Tool route response: `200 OK`

```json
{
  "request": "What is the status of my reimbursement request?",
  "intent": "tool_request",
  "outcome": {
    "status": "not_executed",
    "required_capability": "enterprise_tool",
    "message": "This request requires an enterprise tool. No action was executed."
  }
}
```

Unsupported route response: `200 OK`

```json
{
  "request": "Write a wedding speech for me.",
  "intent": "unsupported",
  "outcome": {
    "status": "unsupported",
    "message": "This request is outside the configured Agent capabilities."
  }
}
```

The three public response variants are a strict Pydantic discriminated union.
Cross-field validators prevent an intent from carrying another intent's
outcome shape.

### 10.6 Error contract

- `401 Unauthorized`: missing or invalid authentication.
- `403 Forbidden`: missing/inactive Workspace Membership or insufficient
  Agent-management role.
- `404 Not Found`: scoped Workspace, Agent, or runtime Knowledge Base not
  found.
- `409 Conflict`: Agent or runtime Knowledge Base is not active.
- `422 Unprocessable Entity`: request/configuration validation failure or
  routing input above the fixed local budget.
- `502 Bad Gateway`: sanitized routing, embedding, or generation provider
  failure or invalid provider output.
- `503 Service Unavailable`: a required provider is not configured.

## 11. Internal Routing Contract

The model-facing structured output is exactly equivalent to:

```json
{
  "intent": "knowledge_qa"
}
```

where `intent` is an enum of:

- `knowledge_qa`,
- `tool_request`, or
- `unsupported`.

The schema rejects extra fields. It contains no rationale, confidence,
capability name, Tool name, Tool ID, arguments, database identifier, answer,
or public message. Stable public messages and all downstream behavior are
server-owned.

The project-owned routing protocol accepts the normalized request and system
prompt and returns the validated intent. Automated tests inject fake routing
providers. Production wiring uses a lazy OpenAI provider so routes that fail
authorization or Agent status checks make no provider request.

## 12. Application Structure

```text
Agent management request
-> current User
-> active Workspace Membership
-> Agent Administrator dependency
-> Agent service
-> SQLAlchemy
-> PostgreSQL

Agent use request
-> current User
-> active Workspace Membership
-> Workspace-scoped active Agent lookup
-> narrow routing provider
-> strict output validation
   -> knowledge_qa
      -> existing Feature 009 answer service
      -> existing retrieval / grounded generation / citations
   -> tool_request
      -> fixed non-executed response
   -> unsupported
      -> fixed unsupported response
```

No workflow engine, graph runtime, repository layer, queue, or persistence for
requests/responses is introduced.

## 13. Configuration and Dependencies

Proposed fixed configuration:

- `ROUTING_MODEL=gpt-5.6-terra`
- `ROUTING_REASONING_EFFORT=low`
- `ROUTING_PROMPT_VERSION=agent-intent-routing-v1`
- `ROUTING_MAX_INPUT_TOKENS=8000`
- `ROUTING_MAX_OUTPUT_TOKENS=64`

The existing `OPENAI_API_KEY` and `OPENAI_TIMEOUT_SECONDS` are reused. A routed
request incurs one classification call; a `knowledge_qa` request then incurs
the already-approved Feature 008/009 embedding and generation calls.

No runtime dependency is added. Tests do not require these environment values
or a live provider.

## 14. Frontend Scope

Add `Assistant` as a separate product area in the authenticated Workspace
shell and retain both existing areas:

- `Assistant`,
- `Knowledge Q&A`, and
- `Workspace`.

The Assistant surface will:

- load Agent summaries for the selected Workspace,
- let the User select only an active Agent,
- reuse the selected Workspace's authorized Knowledge Base list and let the
  User select exactly one active Knowledge Base as runtime context,
- show an empty state when no active Agent exists,
- show a knowledge-context empty state when no active Knowledge Base exists,
- accept one validated 1-to-2,000-character request,
- prevent duplicate submission and context switching while pending,
- render a grounded answer and citations for `knowledge_qa` using the existing
  Feature 010 response types and visual patterns without refactoring or
  changing the Feature 010 component,
- render a clear non-executed enterprise-capability state for `tool_request`,
- render an explicit out-of-scope state for top-level `unsupported`, and
- distinguish `401` session expiry, `403` access denial, `404` stale/missing
  scoped resources, `409` unavailable Agent/Knowledge Base, recoverable `422`
  validation or budget failure, `502`/`503` service failure, and network
  failure.

The typed API client adds:

- `AgentSummary`,
- the three-variant discriminated `AgentRouteResponse` union,
- `listAgents(workspaceId, accessToken)` using the active-only default, and
- `routeAgentRequest(workspaceId, agentId, request, knowledgeBaseId, token)`.

API utility tests verify the exact paths, JSON body, Bearer header, and typed
response handling. The new Assistant component must call only the Agent route;
it must not call the Feature 009 answer endpoint directly.

Workspace switching clears Agent selection, Knowledge Base selection, and all
Assistant request/result state before loading the new Workspace's scoped
resources. Agent-list failure is isolated from the existing Workspace and
Knowledge Q&A loads so the new surface cannot make those product areas
unavailable. A `401` clears the in-memory session. The browser never calls
OpenAI or performs routing.

Agent configuration management remains API-only in Feature 011. A frontend
administration form is not needed to demonstrate routing and would duplicate
existing form patterns without changing the authorization boundary. The UI
may hide management affordances from unauthorized roles, but backend denial is
required and tested.

No conversation layout, saved history, multiple messages, streaming, or
multi-turn memory is added.

## 15. Acceptance Criteria

### AC-001 - Workspace-scoped Agent model

Revision `0007` creates the proposed Agent table and enforces same-Workspace
Agent ownership without changing previous migrations.

### AC-002 - Agent management authorization

Active `agent_admin` and `system_admin` members can create, read full
configuration, update, activate, and disable Agents in their Workspace.
Employees and knowledge administrators receive `403` for those operations.

### AC-003 - Active-member use

Every active Workspace role can list summaries and use an active Agent.
Use also requires one active Knowledge Base in the route Workspace.
Inactive/missing Memberships, disabled Workspaces, inactive Knowledge Bases,
and draft/disabled Agents cannot reach routing.

### AC-004 - Workspace isolation

All Agent and Knowledge Base lookups are Workspace-scoped. A foreign ID cannot
be combined with an authorized route or disclose whether the foreign resource
exists.

### AC-005 - Validated routing taxonomy

Every successful request has exactly one server-validated intent:
`knowledge_qa`, `tool_request`, or `unsupported`. Malformed provider output
fails closed and no confidence score is exposed.

### AC-006 - Knowledge reuse

A `knowledge_qa` route calls the existing Feature 009 answer service with the
request's validated Knowledge Base context and retains Workspace isolation,
active Membership rules, Knowledge Base/Document eligibility, grounded
citations, and explicit insufficient-evidence behavior.

### AC-007 - Tool safety

A `tool_request` returns the documented fixed not-executed outcome. It does not
select a Tool, generate arguments, call an enterprise API, fabricate business
data, create an approval, or persist an execution log.

### AC-008 - Unsupported behavior

An out-of-scope request returns the explicit top-level `unsupported` outcome
and does not call retrieval, grounded generation, or a Tool.

### AC-009 - Provider isolation

The routing integration uses the narrow provider interface, strict structured
output, fixed limits, `store=false`, no tools, no retries, minimized data, and
sanitized failures.

### AC-010 - Separate Assistant interface

The frontend demonstrates all three routing outcomes in a separate Assistant
area while preserving the Feature 010 Knowledge Q&A interface and existing
Workspace administration behavior.

### AC-011 - No live calls in tests

All required automated tests use fake routing, embedding, and generation
providers and pass without `OPENAI_API_KEY`, internet access, or paid calls.

## 16. Test Requirements

### 16.1 Migration and model

- Upgrade `0006 -> 0007`, downgrade, Alembic head, and schema drift.
- Field types, defaults, timestamps, indexes, checks, and foreign keys.
- Workspace ownership constraint and scoped Agent persistence.
- No changes to migrations `0001` through `0006`.

### 16.2 Agent API and authorization

- `401` for every endpoint without valid authentication.
- Summary listing for all four active roles.
- Active-only default listing, administrator-only `include_inactive=true`, and
  exact-key serialization proof that no summary exposes `system_prompt`.
- Create, full-configuration read, and update success for `agent_admin` and
  `system_admin`.
- Management denial for `employee` and `knowledge_admin`.
- Regression proof that `agent_admin` cannot mutate Knowledge Bases or manage
  Memberships.
- Per-Workspace role resolution for one User who is an Agent administrator in
  Workspace A and an employee in Workspace B: management succeeds only in A,
  while active-Agent use succeeds in both.
- Successful active-Agent routing for each of the four active roles.
- Persisted Workspace, creator, prompt, default `draft` status, and timestamps.
- Activation, disabling, and re-enabling.
- Empty/oversized/unknown fields and empty PATCH rejection.
- Missing, invited, and disabled Membership denial.
- Disabled Workspace denial.
- Missing and cross-Workspace Agent and Knowledge Base IDs.
- Call-count proof that missing/invalid authentication, disabled Users,
  missing/invited/disabled Memberships, disabled Workspaces, missing/foreign
  Agents or Knowledge Bases, inactive Knowledge Bases, and draft/disabled
  Agents are all rejected before routing-provider invocation.

### 16.3 Routing and knowledge reuse

- `knowledge_qa`, `tool_request`, and `unsupported` using fake routing
  providers.
- Malformed, extra-field, missing-field, and unknown-enum provider output.
- Provider timeout/failure, refusal, incomplete output, model mismatch, and
  missing configuration.
- Routing input budget enforcement before a provider call.
- Proof that provider input contains only fixed instructions, the system
  prompt, request, and schema and excludes IDs, roles, secrets, retrieved text,
  and Tool definitions.
- Proof that the request uses `store=false`, no tools, no streaming, no
  background mode, no retries, and fixed model/limits.
- Knowledge routing calls the existing answer service with the validated
  runtime Knowledge Base and preserves answered and insufficient-evidence
  variants.
- Existing Feature 009 citation verification and disabled/non-ready Document
  eligibility through regression tests.
- Tool routing makes no retrieval, grounded-generation, Tool, enterprise API,
  approval, or persistence call and returns no fabricated business data.
- Unsupported routing makes no retrieval or grounded-generation call.
- Routing failures never become unsupported outcomes.
- Sanitized errors/logs contain no request, prompt, secret, or provider body.

### 16.4 Frontend

Mocked component tests cover:

- Workspace-scoped Agent loading and active-Agent selection,
- active Knowledge Base context selection and exact scoped route request,
- Workspace switch reset and reload,
- rejection of late Agent-list responses after a Workspace switch,
- isolation proving an Agent-list failure does not break Workspace or Knowledge
  Q&A loading,
- successful `knowledge_qa` answer and citation rendering,
- nested insufficient-evidence rendering,
- `tool_request` non-executed rendering,
- top-level `unsupported` rendering,
- pending state and duplicate-submit prevention,
- blank request validation,
- no-active-Agent and no-active-Knowledge-Base states,
- Assistant visibility and successful use for ordinary active members,
- `401` session clearing,
- `403` access denied,
- `404` stale or missing Agent/Knowledge Base,
- `409` unavailable Agent or Knowledge Base,
- recoverable `422` validation/input-budget failure,
- `502`/`503` provider/service failure, and
- generic API/network failure.

API utility tests cover active-summary listing and exact Agent-route URL, body,
Bearer header, and response-union typing.

### 16.5 Verification after approval

- Feature-specific PostgreSQL integration tests.
- Full backend `pytest` suite against PostgreSQL with no skips.
- Backend Ruff checks.
- Alembic head and schema-drift checks.
- Full frontend tests, lint, and production build.
- `git diff --check`.
- Independent review before merge because the feature changes database schema,
  authorization, and tenant-isolation-sensitive paths.

## 17. Out of Scope

- Feature 012 Enterprise Tool Calling.
- Tool persistence, registry, concrete selection, schemas, arguments,
  validation, mock enterprise APIs, or execution.
- Reimbursement, employee-information, IT-request, or other business APIs.
- Provider function/tool calling.
- Feature 013 human approval, approval models, execution logs, and audit
  workflows.
- Workflow persistence or orchestration.
- Conversation or message persistence, saved history, multi-turn memory, or
  streaming.
- Multi-agent collaboration.
- Multi-Knowledge-Base retrieval or persisted Agent-to-Knowledge-Base
  associations.
- Retrieval tuning, reranking, hybrid search, or RAG changes.
- Model training or fine-tuning.
- Feature 014 evaluation management or dashboards.
- Frontend Agent-configuration administration.
- Deployment work.
- Hard deletion of Agents.
- New custom roles or changes to existing Membership role values.

## 18. Required Human Approval Gate

Before implementation, a human must approve all of the following:

1. **Migration:** create additive Alembic revision `0007` and the `agents`
   table, constraints, and indexes described in Section 9; do not modify or
   execute destructive operations against earlier migrations or existing data.
2. **Knowledge context:** require exactly one active, same-Workspace
   `knowledge_base_id` in each routing request, validate it before the provider
   call, and use it only on the knowledge branch; do not persist an Agent
   association or implement multi-Knowledge-Base retrieval.
3. **Authorization:** allow all active members to list Agent summaries and use
   active Agents; restrict full configuration, create, and update to
   `agent_admin` and `system_admin`; do not grant adjacent Knowledge Base,
   Membership, or system-administration rights.
4. **Routing model:** reuse fixed model `gpt-5.6-terra` through the existing
   official OpenAI SDK and narrow project-owned provider interface.
5. **External data:** send only the normalized User request, Agent system
   prompt, fixed instructions, and strict enum schema. Send no tenant/user
   identifiers, roles, secrets, retrieved text, citations, Tool definitions,
   or business-system data.
6. **Provider behavior:** use strict structured output, `store=false`, no
   tools, no streaming/background/conversation state, disabled truncation,
   low reasoning effort, an 8,000-token maximum counted locally over the
   complete instructions, Agent prompt, User request, and schema before the
   call, 64 maximum output tokens, 30-second timeout, and zero retries.
7. **Control and validation:** accept only the three-value enum; expose no
   confidence; keep authorization, Knowledge Base selection, public messages,
   and downstream behavior server-owned; return sanitized `422`, `502`, and
   `503` failures as documented.
8. **Knowledge reuse:** route knowledge through the unchanged Feature 009
   answer service; do not add the Agent prompt to grounded generation or
   duplicate retrieval/citation logic.
9. **Dependencies and framework:** add no runtime dependency and do not add
   LangGraph, a broad Agent framework, or a tool abstraction in Feature 011.
10. **Frontend:** add the separate single-turn Assistant surface in Section 14
    while preserving Knowledge Q&A; keep Agent administration API-only.

Approval of this proposal authorizes scoped implementation and migration file
creation, but not migration execution against any non-test database, merge to
`main`, Feature 012, or any destructive database operation.
