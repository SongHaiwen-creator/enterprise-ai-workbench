# Feature 008 - RAG Retrieval Foundation

Status: Proposed - Human Approval Required
Milestone: 2

## 1. Goal

Turn successfully extracted Document text into workspace-isolated vector chunks
and let authorized Workspace members retrieve the most relevant chunks with
source metadata.

This feature is the retrieval foundation for later answer generation and
citations. It does not call an LLM to compose an answer.

## 2. Scope

This feature will:

- Enable the PostgreSQL `vector` extension and add the `chunks` table through
  Alembic revision `0005`.
- Replace the local PostgreSQL development image with the official pgvector
  PostgreSQL 17 image while preserving the existing databases, ports, health
  check, and test-database initialization behavior.
- Split a ready Document's retained extracted text into deterministic,
  overlapping chunks.
- Generate 1,536-dimension embeddings with OpenAI
  `text-embedding-3-small` through the official OpenAI Python SDK.
- Persist chunk text, order, embedding model, vector, and timestamps in
  PostgreSQL.
- Add an explicit administrator-only Document indexing endpoint that creates
  or atomically replaces all chunks for one Document.
- Add a read-only semantic search endpoint for active Workspace members.
- Restrict search to active Knowledge Bases and ready Documents in the route
  Workspace.
- Return ranked chunk content and stable source metadata suitable for a later
  citation layer.
- Add unit tests, PostgreSQL integration tests, and regression verification.

## 3. Open-Source Reuse Decision

RAG ingestion and vector search are substantial AI infrastructure. The project
will reuse focused, maintained components instead of implementing embedding
HTTP calls, vector serialization, or generic text splitting from scratch.

### 3.1 Vector storage

| Candidate | Functional fit | License / maintenance | Deployment and integration | Decision |
|---|---|---|---|---|
| Existing PostgreSQL plus `pgvector` and `pgvector-python` | Matches `ARCHITECTURE.md`; keeps tenant data and vector search in the existing database | PostgreSQL-style permissive license; actively maintained | Official PostgreSQL 17 image and direct SQLAlchemy support; one existing service remains authoritative | Use |
| Qdrant | Mature dedicated vector database | Apache 2.0; active | Adds a second stateful service, synchronization, backup, and tenant-filtering surface | Do not add for MVP |
| Weaviate | Mature vector platform | BSD-3-Clause; active | Adds a larger external platform and duplicates product-owned data controls | Do not add for MVP |
| PostgreSQL arrays plus custom distance SQL | Avoids an extension | Custom commodity implementation | Poor fit for indexed vector search and contradicts the specified pgvector architecture | Reject |

The MVP will use exact cosine-distance search. pgvector documents exact search
as the default with perfect recall; HNSW and IVFFlat trade recall or add tuning
and are unnecessary for the initial data volume.

Sources:

- <https://github.com/pgvector/pgvector>
- <https://github.com/pgvector/pgvector-python>

### 3.2 Embedding provider

| Candidate | Functional fit | License / maintenance | Deployment and integration | Decision |
|---|---|---|---|---|
| Official OpenAI Python SDK with `text-embedding-3-small` | Direct supported embeddings API; configurable output dimensions | Apache 2.0 SDK; maintained by OpenAI | Small integration surface; requires an API key and sends chunk/query text to OpenAI | Use for the MVP |
| LangChain OpenAI integration | Supports the same provider | MIT; active | Adds an abstraction not needed for one provider and one operation | Do not add |
| Raw HTTP client | Technically sufficient | Project-owned | Reimplements SDK authentication, errors, retries, and response typing | Reject |
| Local sentence-transformer model | Avoids external text transmission | Common models and runtimes vary | Large model/runtime dependency and operational footprint exceed this feature | Defer |

The integration will call the embeddings endpoint only. The official API
accepts arrays of inputs, supports a `dimensions` parameter for
`text-embedding-3` models, and applies per-input and aggregate request limits.
The implementation must batch requests below the documented limits.

Sources:

- <https://developers.openai.com/api/docs/models/text-embedding-3-small>
- <https://developers.openai.com/api/reference/python/resources/embeddings/methods/create>
- <https://github.com/openai/openai-python>

### 3.3 Text splitting

| Candidate | Functional fit | License / maintenance | Deployment and integration | Decision |
|---|---|---|---|---|
| `langchain-text-splitters` `RecursiveCharacterTextSplitter` | Recommended generic recursive splitter; preserves paragraphs, lines, and words when possible | MIT; active standalone package | Focused dependency; use only local `split_text` and require a patched release | Use, version `>=1.1.2,<2.0` |
| Full LangChain | Includes the selected splitter | MIT; active | Unnecessary agent, prompt, and model abstractions | Do not add |
| LlamaIndex core | Capable ingestion framework | MIT; active | Broader indexing framework than this scoped pipeline requires | Do not add |
| Custom recursive splitter | Simple to prototype | Project-owned | Reimplements a commodity algorithm and edge-case handling | Reject |

Only in-memory text splitting is used. URL-fetching and HTML-loading helpers
are not used. Version 1.1.2 or newer is required because it contains the fix
for the package's 2026 URL-redirect SSRF advisory, even though the affected URL
API is outside this feature.

Sources:

- <https://docs.langchain.com/oss/python/integrations/splitters/recursive_text_splitter>
- <https://github.com/langchain-ai/langchain/security/advisories/GHSA-fv5p-p927-qmxr>

## 4. Business Rules

### BR-001 - Workspace and parent ownership

A Chunk belongs to exactly one Document and one Workspace. Its stored
`workspace_id` must equal the parent Document's `workspace_id`.

Every indexing and search query must be scoped by the route Workspace and
Knowledge Base. Cross-Workspace, cross-Knowledge-Base, and wrong-parent IDs
must not disclose whether a resource exists elsewhere.

### BR-002 - Indexing access

Indexing or re-indexing requires an authenticated active Membership with role:

- `knowledge_admin`, or
- `system_admin`.

The Knowledge Base must be active. The Document must belong to it, have status
`ready`, and contain non-empty extracted text. Employees and agent
administrators cannot index Documents.

Indexing is explicit in this feature. Upload does not make a network call and
does not automatically create embeddings.

### BR-003 - Deterministic chunking

The implementation uses `RecursiveCharacterTextSplitter` with:

- chunk size: 1,000 characters,
- chunk overlap: 200 characters,
- length function: Python character length,
- separators: the library's generic recursive defaults.

Whitespace-only chunks are discarded. Remaining chunks preserve splitter
output and receive zero-based, gap-free `chunk_index` values in source order.
The configured size keeps every embedding input comfortably below the OpenAI
per-input token limit without adding a tokenizer dependency.

### BR-004 - Embedding contract

Index and query embeddings use:

- provider: OpenAI,
- model: `text-embedding-3-small`,
- dimensions: 1,536,
- encoding format: floating-point values.

Index inputs are sent in bounded batches of no more than 256 chunks. The
implementation validates response count, response indexes, and vector
dimensions before persistence.

Changing provider, model, or dimensions is out of scope because stored and
query vectors must share one compatible embedding space. A later model change
requires an explicit re-indexing and schema/versioning design.

### BR-005 - Atomic re-indexing

The system generates and validates every replacement embedding before it
changes persisted chunks.

After successful generation, replacement occurs in one database transaction:

1. delete existing chunks for the scoped Document,
2. insert the complete replacement set,
3. commit.

If splitting, provider access, response validation, or persistence fails, the
previous complete chunk set remains unchanged. A first-time failure leaves no
partial chunk set.

### BR-006 - Search access and eligibility

Any authenticated User with an active Membership in an active Workspace may
search an active Knowledge Base in that Workspace.

Search candidates must belong to:

- the route Workspace,
- the route Knowledge Base,
- a Document whose current status is `ready`.

Chunks belonging to disabled Documents or a disabled Knowledge Base cannot
appear. Documents without chunks contribute no results.

### BR-007 - Ranking and limits

The query is embedded with the same model and dimensions used for indexed
chunks. Results are ordered by ascending pgvector cosine distance, then
`document_id`, then `chunk_index` for deterministic ties.

The requested limit defaults to 5 and must be between 1 and 20. The API returns
cosine distance, chunk content, and source metadata. It does not apply a hidden
relevance threshold or claim that a result is correct.

### BR-008 - External data handling

Indexing sends chunk text to the configured OpenAI API account. Searching sends
the user's query text. No Workspace ID, user ID, document filename, membership
data, JWT, password, or database credential is included in embedding inputs.

The API key comes only from `OPENAI_API_KEY` and is represented as a secret in
settings. It must not be persisted, returned, or logged. Provider error bodies
must not be persisted or returned to clients.

### BR-009 - Failure behavior

Missing embedding configuration returns `503 Service Unavailable`. Provider
timeouts, rate limits, unavailable responses, or invalid provider payloads
return a sanitized `502 Bad Gateway` response. These failures do not expose
credentials, request text, provider response bodies, or stack traces.

No automatic retry loop is added in this feature. Operators or authorized
administrators may retry the idempotent indexing request.

## 5. Authorization Matrix

| Operation | Employee / agent admin | Knowledge admin | System admin |
|---|---:|---:|---:|
| Index or re-index one ready Document | No | Yes | Yes |
| Semantic search in an active Knowledge Base | Yes | Yes | Yes |

All authorization and tenant filtering occur in the backend. Frontend
visibility is not authorization.

## 6. Database Contract

Migration `0005` has `down_revision = "0004"` and must not modify any prior
migration.

It will:

1. create the PostgreSQL `vector` extension if it is not already available,
2. create `chunks`,
3. create relational indexes and constraints,
4. leave vector search exact, without HNSW or IVFFlat indexes.

Table: `chunks`

| Field | Type | Rules |
|---|---|---|
| `id` | UUID | Primary key, generated by PostgreSQL |
| `workspace_id` | UUID | Required FK to `workspaces.id`, `ON DELETE RESTRICT` |
| `document_id` | UUID | Required FK to `documents.id`, `ON DELETE RESTRICT` |
| `content` | TEXT | Required, non-empty after trimming |
| `chunk_index` | INTEGER | Required, zero or greater |
| `embedding_model` | VARCHAR(100) | Required; `text-embedding-3-small` in this feature |
| `embedding` | VECTOR(1536) | Required |
| `created_at` | TIMESTAMPTZ | Required, database default current timestamp |

Indexes and constraints:

- `ix_chunks_workspace_id`
- `ix_chunks_document_id`
- unique constraint on (`document_id`, `chunk_index`)
- check constraint for non-negative `chunk_index`
- check constraint for non-empty `content`
- foreign keys for `workspace_id` and `document_id`

No cascade deletion is introduced. Hard deletion remains out of scope.
Downgrade drops only `chunks` and then drops the `vector` extension only when
no remaining database object depends on it.

## 7. API / Data Contract

### 7.1 Index or re-index a Document

Endpoint:

`POST /api/workspaces/{workspace_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/index`

Request body: none.

Success: `200 OK`

```json
{
  "document_id": "document-uuid",
  "chunk_count": 14,
  "embedding_model": "text-embedding-3-small",
  "embedding_dimensions": 1536,
  "indexed_at": "2026-09-16T12:00:00Z"
}
```

`indexed_at` is the greatest `created_at` in the newly committed chunk set.

Errors:

- `401 Unauthorized`: missing or invalid authentication.
- `403 Forbidden`: missing active Membership or insufficient role.
- `404 Not Found`: scoped Workspace, Knowledge Base, or Document not found.
- `409 Conflict`: disabled Knowledge Base, non-ready Document, or missing
  extracted text.
- `502 Bad Gateway`: sanitized embedding-provider failure or invalid response.
- `503 Service Unavailable`: embedding provider is not configured.

### 7.2 Semantic search

Endpoint:

`POST /api/workspaces/{workspace_id}/knowledge-bases/{knowledge_base_id}/search`

Request:

```json
{
  "query": "What is the travel reimbursement limit?",
  "limit": 5
}
```

Validation:

- `query` is trimmed and must contain between 1 and 2,000 characters.
- `limit` defaults to 5 and must be between 1 and 20.
- unknown fields are rejected.

Success: `200 OK`

```json
{
  "query": "What is the travel reimbursement limit?",
  "results": [
    {
      "chunk_id": "chunk-uuid",
      "document_id": "document-uuid",
      "file_name": "travel-policy.md",
      "document_version": 1,
      "chunk_index": 3,
      "content": "...",
      "cosine_distance": 0.0812
    }
  ]
}
```

An active Knowledge Base with no eligible indexed chunks returns `200 OK` with
an empty `results` list.

Errors:

- `401 Unauthorized`: missing or invalid authentication.
- `403 Forbidden`: missing active Workspace Membership.
- `404 Not Found`: scoped Workspace or Knowledge Base not found.
- `409 Conflict`: Knowledge Base is disabled.
- `502 Bad Gateway`: sanitized embedding-provider failure or invalid response.
- `503 Service Unavailable`: embedding provider is not configured.

## 8. Application Structure

```text
Index request
-> authentication and Knowledge Administrator authorization
-> scoped ready Document lookup
-> RecursiveCharacterTextSplitter
-> official OpenAI SDK embedding batches
-> validate complete embedding response
-> atomic Chunk replacement
-> PostgreSQL / pgvector

Search request
-> authentication and active Workspace Membership
-> scoped active Knowledge Base lookup
-> official OpenAI SDK query embedding
-> workspace/Knowledge Base/ready-Document filters
-> exact pgvector cosine ranking
-> chunk and source metadata response
```

The provider integration must be behind a narrow project-owned embedding
protocol so tests can use deterministic fakes without network access. This is
not a provider marketplace or general AI framework abstraction.

## 9. Configuration and Dependencies

New configuration:

- `OPENAI_API_KEY`: optional at process startup, required at indexing/search
  call time.
- `EMBEDDING_MODEL`: fixed default and only allowed value
  `text-embedding-3-small` in this feature.
- `EMBEDDING_DIMENSIONS`: fixed default and only allowed value `1536`.

New runtime dependencies:

- official `openai` Python SDK,
- `pgvector` Python package,
- `langchain-text-splitters>=1.1.2,<2.0`.

Infrastructure dependency:

- official `pgvector/pgvector` PostgreSQL 17 container image, pinned to an
  explicit pgvector and PostgreSQL-major-compatible tag.

No API key value is added to `.env.example`; only an empty placeholder and
documentation are allowed.

## 10. Acceptance Criteria

### AC-001 - Migration and extension

Revision `0005` upgrades from `0004`, enables pgvector, creates the specified
table and constraints, reaches Alembic head without drift, and downgrades to
`0004` without changing prior migrations or tables.

### AC-002 - Deterministic indexing

An authorized administrator can index a ready Document. The persisted chunks
are ordered, overlap according to the fixed splitter settings, preserve the
Document and Workspace ownership, and contain validated 1,536-dimension
embeddings.

### AC-003 - Atomic re-indexing

Re-indexing replaces rather than duplicates chunks. Any failure before commit
preserves the previous complete chunk set and creates no partial replacement.

### AC-004 - Search and source metadata

An active member can search an active Knowledge Base. Results are ranked by
cosine distance and include content plus stable Document citation metadata.

### AC-005 - Eligibility filters

Disabled Knowledge Bases cannot be indexed or searched. Disabled, failed,
processing, or uploaded Documents cannot be indexed, and disabled Documents'
existing chunks cannot appear in search.

### AC-006 - Authorization and isolation

Employees and agent administrators cannot index. Missing, invited, or disabled
Memberships; disabled Workspaces; and cross-Workspace or cross-parent IDs
cannot bypass isolation for indexing or search.

### AC-007 - Provider safety

Missing configuration and simulated provider errors use the documented status
codes and sanitized messages. Tests verify that secrets, source text, query
text, and provider response bodies do not appear in API errors or logs.

### AC-008 - No live-provider test dependency

Automated tests use an injected deterministic embedding fake. Required tests
do not require an OpenAI credential, internet access, or paid API calls.

### AC-009 - Existing behavior

Authentication, Workspace, Membership, Knowledge Base, Document, health,
CORS, migrations, and frontend behavior continue to pass existing
verification.

## 11. Test Requirements

Tests must cover:

- `0004 -> 0005` migration, pgvector extension, schema, constraints, indexes,
  head, downgrade, and schema drift.
- Chunk model constraints and parent relationships in PostgreSQL.
- Deterministic chunk boundaries, overlap, ordering, and whitespace handling.
- Embedding batching, response ordering, count validation, and dimension
  validation with a fake client.
- First-time indexing and successful atomic re-indexing.
- Preservation of old chunks after simulated splitter, provider, validation,
  or persistence failures.
- Authentication and the indexing authorization matrix.
- Ready/disabled/failed/processing/uploaded Document eligibility.
- Active/disabled Knowledge Base behavior.
- Cross-Workspace and wrong-parent isolation.
- Search request validation, default/maximum result limits, empty results,
  cosine ordering, and deterministic ties.
- Exclusion of disabled Documents from retrieval even when chunks exist.
- Missing provider configuration and sanitized provider failures.
- Regression coverage for existing APIs.

Verification must include:

- Feature-specific PostgreSQL integration tests.
- Full backend `pytest` suite against PostgreSQL with no skips.
- Backend Ruff checks.
- Alembic head and schema-drift checks.
- Frontend unit tests, lint, and production build.
- `git diff --check`.

SQLite must not replace PostgreSQL integration tests. Live OpenAI calls are not
part of automated verification.

## 12. Human Approval Required

Implementation must not begin until a human explicitly approves:

- Alembic revision `0005`, creation of the `chunks` table, and enabling the
  PostgreSQL `vector` extension.
- Replacing the local PostgreSQL image with the official pgvector image.
- The three runtime dependencies and reuse decisions in Section 3.
- Sending extracted enterprise chunk text and employee search queries to the
  configured OpenAI API account.
- The fixed OpenAI embedding model/dimension contract and exact-search design.
- The indexing/search authorization and tenant-isolation policy.

## 13. Out of Scope

- LLM answer generation, prompt construction, answer citations, or streaming.
- Reranking, hybrid keyword search, relevance thresholds, HNSW, or IVFFlat.
- Automatic indexing during upload, background workers, queues, retries,
  scheduling, progress percentages, or recovery jobs.
- Multi-provider embedding configuration, local models, model migration, or
  mixed embedding dimensions.
- Chunk editing, bulk indexing, hard deletion, or public chunk-list APIs.
- OCR, table/layout recovery, source-binary retention, or new file formats.
- Fine-grained document/department permissions or custom roles.
- Agents, tools, workflows, approvals, execution logs, or evaluation.
