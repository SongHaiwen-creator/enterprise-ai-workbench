# Feature 010 - Knowledge Q&A Interface

Status: Implemented - pending review
Milestone: 2

## 1. Goal

Turn the grounded answer API delivered by Feature 009 into a usable enterprise
Knowledge Q&A interface:

```text
Workspace
-> Knowledge Base
-> Knowledge Q&A
-> ask question
-> grounded answer or explicit unsupported result
-> inspect citations
```

The interface must preserve the existing in-memory authentication session,
Workspace selection, backend RBAC enforcement, and Workspace isolation rules.

## 2. Scope

This feature will:

- Add a Knowledge Q&A product area to the existing authenticated frontend.
- Keep the user inside the currently selected Workspace.
- Load only Knowledge Bases returned by the selected Workspace's authorized
  list endpoint and let the user select one of them.
- Provide a multiline, validated question composer with a pending state and
  duplicate-submit prevention.
- Call the existing Feature 009 answer endpoint without implementing retrieval
  or generation logic in the browser.
- Present answered, unsupported, loading, empty, request-error,
  unauthorized/forbidden, and disabled-Knowledge-Base states.
- Display grounded citations using file name, chunk index, and the bounded
  source excerpt returned by the backend.
- Let a user select a citation and inspect its supporting excerpt in a simple,
  deterministic source panel.
- Retain the existing Workspace overview and role-aware member-management
  experience.
- Add frontend component tests with mocked API responses.

No backend endpoint, authorization policy, database model, migration, or
runtime dependency is required.

## 3. Business Rules

### BR-001 - Workspace-bound operation

`GET /api/workspaces` remains the source of truth for the Workspaces available
to the signed-in user. Knowledge Bases are loaded only through:

`GET /api/workspaces/{selected_workspace_id}/knowledge-bases`

The browser must never combine a Workspace ID and Knowledge Base ID that were
not associated through that response. Switching Workspace clears the selected
Knowledge Base, question result, citation selection, and Q&A errors before
loading that Workspace's Knowledge Bases.

### BR-002 - Authorization remains server-owned

All Knowledge Base and answer requests include the existing in-memory Bearer
token. Frontend visibility and state handling are usability controls only; the
backend remains the authorization boundary.

A `401` response clears the in-memory session and returns the user to sign-in.
A `403` response is rendered as an explicit access-denied state without
exposing protected data. Knowledge Base IDs, Document IDs, Chunk IDs, and
Workspace IDs are not presented as primary UI content.

### BR-003 - Knowledge Base selection

The list response includes active and disabled Knowledge Bases. The first
active Knowledge Base is selected by default. A user may inspect a disabled
Knowledge Base in the selector, but the question composer is disabled and a
clear unavailable state is shown.

If the selected Workspace has no Knowledge Bases, the Q&A area shows an empty
state and no answer request can be submitted.

### BR-004 - Question validation and submission

Questions are trimmed and must contain between 1 and 2,000 characters,
matching Feature 009. Validation occurs before the request and is announced in
the composer. While a request is pending, the question input, Knowledge Base
selector, submit action, Workspace switching, and product-area switching are
disabled so the request context cannot change and duplicate submission is
prevented.

Submission calls only:

`POST /api/workspaces/{workspace_id}/knowledge-bases/{knowledge_base_id}/answer`

with `{ "question": "..." }`. No RAG, retrieval, prompt, citation validation,
or model logic is duplicated in the frontend.

### BR-005 - Result states

- `answered`: display the generated answer and citation list.
- `unsupported`: display the server message, no fabricated answer, and no
  citation panel.
- `loading`: retain the submitted question context and show a polished progress
  state with duplicate controls disabled.
- `empty`: before a question is submitted, explain what the user can ask and
  that answers are grounded in the selected Knowledge Base.
- `error`: display a recoverable API/network error without discarding the typed
  question.
- `unauthorized`: clear the session on `401`.
- `forbidden`: display a dedicated access-denied state on `403`.
- `disabled Knowledge Base`: display a dedicated unavailable state for a
  disabled selection or a `409` answer response.

All other backend failures use sanitized messages supplied by the shared API
client, with a stable fallback when needed.

### BR-006 - Citation presentation and inspection

Each citation card displays:

- a stable ordinal label such as `Source 1`,
- Document file name,
- human-readable chunk position derived from the zero-based `chunk_index`,
- the bounded excerpt supplied by Feature 009.

The first citation is selected after an answered response. Selecting another
citation updates a single source-inspection panel to show that citation's file
name, chunk position, and full returned excerpt. The interaction does not fetch
or expose full Document contents and does not prominently display internal
database identifiers.

### BR-007 - Session handling

The Feature 005 behavior remains unchanged: access tokens stay in browser
memory only and are cleared on sign-out or authenticated-request `401`.

## 4. API / Data Contract

The frontend reuses these existing endpoints:

- `POST /api/auth/login`
- `GET /api/auth/me`
- `GET /api/workspaces`
- `GET /api/workspaces/{workspace_id}`
- `GET /api/workspaces/{workspace_id}/members` for `system_admin` only
- `POST /api/workspaces/{workspace_id}/members`
- `PATCH /api/workspaces/{workspace_id}/members/{membership_id}`
- `GET /api/workspaces/{workspace_id}/knowledge-bases`
- `POST /api/workspaces/{workspace_id}/knowledge-bases/{knowledge_base_id}/answer`

The Knowledge Base and grounded-answer response shapes are unchanged from
Features 006 and 009. Generation metadata may be accepted by the typed client
but is not a primary end-user surface in this feature.

## 5. User Experience

The authenticated shell keeps a clear left navigation containing:

- Workspace selection,
- `Knowledge Q&A` as the primary product area,
- `Workspace` administration as the existing secondary area,
- signed-in user identity and sign-out.

The Q&A page uses a spacious two-column desktop layout:

- the primary column contains context, composer, and answer state,
- the supporting column contains citation cards and the selected source
  excerpt.

On narrow screens, the layout stacks without hiding state or source content.
Neutral surfaces, restrained green accents, readable type, and distinct source
cards communicate a portfolio-quality B2B product without introducing a full
design system.

## 6. Acceptance Criteria

### AC-001 - Authorized context

After login, the user can enter Knowledge Q&A for the currently selected
Workspace and choose only a Knowledge Base returned by that Workspace's list
endpoint.

### AC-002 - Question composer

The user can submit a trimmed multiline question of 1-2,000 characters. Blank
or oversized questions show validation. Pending requests cannot be duplicated
and context-changing controls are disabled.

### AC-003 - Grounded answer

An `answered` response displays the generated answer and all citations with
file name, human-readable chunk position, and bounded excerpt.

### AC-004 - Citation inspection

The first returned citation is selected by default. Activating a citation card
deterministically updates the source-inspection panel with that citation's
metadata and excerpt.

### AC-005 - Unsupported evidence

An `unsupported` response displays the backend's evidence-insufficiency message
and does not render an answer or citations.

### AC-006 - Failure states

Network/API failures, forbidden access, expired authentication, and disabled
Knowledge Bases are clearly distinguished. A `401` clears the session; a `403`
does not imply missing evidence; a `409` is presented as a disabled or
unavailable Knowledge Base.

### AC-007 - Workspace and RBAC regression

Workspace switching reloads scoped Knowledge Bases and clears Q&A state.
Existing role-aware member management remains available only to Workspace
`system_admin` users. Backend enforcement remains unchanged.

### AC-008 - Quality gates

- Feature-specific frontend component tests pass with mocked backend responses.
- The complete frontend test suite passes without OpenAI credentials.
- Frontend lint and production build pass.
- Relevant Feature 009 backend regression tests pass without live OpenAI calls.
- `git diff --check` passes.

## 7. Test Requirements

Automated frontend tests must cover at minimum:

- Knowledge Base list loading and selection within the current Workspace,
- selection reset and scoped reloading when the Workspace changes,
- successful grounded answer rendering,
- unsupported result rendering,
- pending/loading state and duplicate-submit prevention,
- generic API/network error state,
- `401` session-clearing behavior,
- `403` access-denied behavior,
- disabled Knowledge Base behavior,
- citation metadata and excerpt rendering,
- citation selection updating the inspection panel,
- blank question validation.

All API responses are mocked. Tests must not require a database, network,
OpenAI credentials, embedding calls, or generation calls.

Verification also includes the relevant backend answer tests with existing
fake providers to protect the consumed contract.

## 8. Dependency Decision

The existing Node test runner covers API utilities but cannot render and
interact with React client components. Add only development-time test tooling:

- Vitest for TypeScript/TSX test execution,
- jsdom for browser DOM behavior,
- Testing Library React and user-event for accessible interaction tests,
- Testing Library jest-dom matchers.

These packages do not affect the production bundle and are limited to the
component behavior required by this feature.

## 9. Out of Scope

- Any Feature 011 or later roadmap functionality.
- Agents, intent routing, tools, workflows, approvals, or tool calling.
- Conversation history, saved chats, message persistence, or answer storage.
- Streaming responses, retry orchestration, cancellation, or background work.
- Full-Document viewing, download, search highlighting, or new Document APIs.
- Knowledge Base creation, editing, disabling, Document upload, or indexing UI.
- Changes to retrieval, ranking, chunking, embeddings, prompts, generation,
  citations, provider configuration, or backend response contracts.
- New database tables, migrations, authentication changes, RBAC changes, or
  Workspace isolation changes.
- A comprehensive design system, theme framework, or component library.
