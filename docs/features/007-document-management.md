# Feature 007 - Document Management API

Status: Approved
Milestone: 2

## 1. Goal

Allow authorized Workspace administrators to upload supported, text-extractable
documents into a Knowledge Base, observe processing outcomes, list and inspect
document metadata, and disable or re-enable documents.

This feature establishes the workspace-isolated document and extracted-text
foundation required by later chunking and RAG work. It does not create chunks,
embeddings, retrieval, answer generation, or citations.

## 2. Scope

This feature will:

- Add the `documents` PostgreSQL table through Alembic revision `0004`.
- Add Document models, enums, response schemas, services, nested routes, and
  router registration.
- Accept multipart uploads for text-extractable PDF, UTF-8 TXT, and UTF-8
  Markdown files.
- Extract text synchronously and persist normalized extracted text for later
  chunking without retaining the original uploaded binary.
- Expose document metadata and processing status, but never extracted text,
  through the API.
- Let active Workspace members list and read document metadata.
- Let active `knowledge_admin` and `system_admin` members upload, disable, and
  re-enable documents.
- Enforce Workspace, Knowledge Base, and Document scoping in every query.
- Add PostgreSQL integration tests and regression verification.

Runtime dependencies are limited to:

- `python-multipart`, required by FastAPI for multipart form parsing.
- `pypdf`, used only for text extraction from text-extractable PDFs.

## 3. Open-Source Reuse Decision

Document parsing is commodity infrastructure and will use maintained libraries
rather than custom multipart or PDF parsers.

PDF candidates considered:

| Candidate | Fit | License consideration | Decision |
|---|---|---|---|
| `pypdf` | Text extraction for ordinary text PDFs; pure Python | Permissive BSD license | Use |
| `pdfplumber` | Stronger layout/table inspection than this scope needs | Permissive, but adds PDFMiner-related complexity | Do not add |
| PyMuPDF | Fast and feature-rich | AGPL/commercial licensing is a poor default fit | Do not add |

TXT and Markdown decoding use the Python standard library. OCR, table recovery,
image extraction, and document conversion services are outside this feature.

## 4. Business Rules

### BR-001 - Workspace and Knowledge Base Ownership

A Document belongs to exactly one Knowledge Base and one Workspace. The stored
`workspace_id` must equal the parent Knowledge Base's `workspace_id`.

Every Document query must be scoped by all route ancestors:

- `workspace_id`
- `knowledge_base_id`
- `document_id`, when addressing one Document

A cross-Workspace or wrong-Knowledge-Base Document ID is returned as not found.

### BR-002 - Read Access

Any authenticated User with an active Membership in an active Workspace may
list and read Document metadata in that Workspace's Knowledge Bases.

Lists include uploaded, processing, ready, failed, and disabled Documents so
administrators can observe processing and management state. Extracted text is
never included in list or detail responses.

### BR-003 - Management Access

Uploading or changing Document status requires an active Membership whose role
is either:

- `knowledge_admin`
- `system_admin`

The `employee` and `agent_admin` roles cannot upload or mutate Documents.

### BR-004 - Parent Knowledge Base State

The parent Knowledge Base must exist under the route Workspace.

- Reading Document metadata remains allowed when the Knowledge Base is
  disabled, matching Feature 006's management-visibility rule.
- Uploading into a disabled Knowledge Base returns `409 Conflict`.
- An authorized administrator may disable or re-enable an existing Document
  while its parent Knowledge Base is disabled.
- Later retrieval must require both an active Knowledge Base and a ready
  Document; retrieval behavior itself is out of scope here.

### BR-005 - Supported Files

Supported file types are:

- `.pdf`: text-extractable PDF only.
- `.txt`: valid UTF-8 plain text.
- `.md`: valid UTF-8 Markdown treated as text.

The server validates the normalized extension and parses the content rather
than trusting the client-supplied media type alone. Empty files, files with no
extractable non-whitespace text, encrypted PDFs, malformed files, and files
larger than 10 MiB are rejected or recorded as failed according to Section 7.

The original client filename is reduced to a basename, trimmed, stripped of
control characters, and limited to 255 characters. It is metadata only and is
never used as a filesystem path.

### BR-006 - Processing State

Supported persisted statuses are:

- `uploaded`
- `processing`
- `ready`
- `failed`
- `disabled`

Upload processing is synchronous for the MVP and follows:

```text
uploaded -> processing -> ready
                       -> failed
```

A parsing failure after a valid upload has created a Document preserves the
record with `failed` status and a short sanitized `processing_error`. Internal
exceptions, stack traces, paths, and file contents must not be persisted in the
error or returned to clients.

Only a ready Document can be disabled. Only a disabled Document can be
re-enabled, and re-enabling returns it to ready because its extracted text was
already validated. API callers cannot set uploaded, processing, or failed
directly.

### BR-007 - Extracted Text

Normalized extracted text is persisted in `extracted_text` for later chunking.
It is nullable until processing succeeds and for failed Documents. It is never
returned by this feature's API.

The original uploaded binary is not retained. Reprocessing or replacing a
source therefore requires a new upload in a later versioning feature.

### BR-008 - Version

New Documents use `version = 1`. Replacement uploads, logical document
families, automatic version incrementing, and superseding older versions are
not implemented in this feature because the current data model does not define
a stable document-family identity.

### BR-009 - Ordering

Document lists are ordered by `file_name`, then `version`, then `id`.

## 5. Authorization Matrix

| Endpoint | Employee / agent admin | Knowledge admin | System admin |
|---|---:|---:|---:|
| List Document metadata | Yes | Yes | Yes |
| Get Document metadata | Yes | Yes | Yes |
| Upload Document | No | Yes | Yes |
| Disable / re-enable Document | No | Yes | Yes |

All checks are enforced by FastAPI backend dependencies and workspace-scoped
service queries. Frontend visibility is not authorization.

## 6. Database Contract

Table: `documents`

| Field | Type | Rules |
|---|---|---|
| `id` | UUID | Primary key, generated by PostgreSQL |
| `workspace_id` | UUID | Required FK to `workspaces.id`, `ON DELETE RESTRICT` |
| `knowledge_base_id` | UUID | Required FK to `knowledge_bases.id`, `ON DELETE RESTRICT` |
| `file_name` | VARCHAR(255) | Required normalized metadata name |
| `file_type` | VARCHAR(16) | Required: `pdf`, `txt`, or `md` |
| `status` | VARCHAR(32) | Required processing/management status, default `uploaded` |
| `version` | INTEGER | Required, default `1`, greater than zero |
| `extracted_text` | TEXT | Nullable; populated only after successful extraction |
| `processing_error` | VARCHAR(500) | Nullable; sanitized failure summary |
| `created_by` | UUID | Required FK to `users.id`, `ON DELETE RESTRICT` |
| `created_at` | TIMESTAMPTZ | Required, database default current timestamp |
| `updated_at` | TIMESTAMPTZ | Required, database default current timestamp |

Indexes:

- `ix_documents_workspace_id`
- `ix_documents_knowledge_base_id`
- `ix_documents_created_by`
- `ix_documents_knowledge_base_status`

Constraints:

- Primary key on `id`.
- Foreign keys for `workspace_id`, `knowledge_base_id`, and `created_by`.
- Check constraints for supported `file_type`, supported `status`, and positive
  `version`.
- No filename uniqueness constraint in this feature.

Migration requirements:

- Create revision `0004` with `down_revision = "0003"`.
- Do not modify revisions `0001`, `0002`, or `0003`.
- Upgrade creates only the Document table and its indexes.
- Downgrade removes only the Document table.
- Update `docs/DATABASE.md` to record the approved extracted-text and processing
  error fields before implementation is reported complete.

## 7. API / Data Contract

Base path:

`/api/workspaces/{workspace_id}/knowledge-bases/{knowledge_base_id}/documents`

### 7.1 Upload Document

Endpoint: `POST /api/workspaces/{workspace_id}/knowledge-bases/{knowledge_base_id}/documents`

Content type: `multipart/form-data`

Form field:

- `file`: one required upload

Success: `201 Created`

A successfully extracted upload returns a Document response with `ready`
status. A syntactically supported upload whose extraction fails after the
Document record is created returns `201 Created` with `failed` status and a
sanitized `processing_error`; the resource was created specifically so the
failure remains visible.

Errors before a Document is created:

- `413 Payload Too Large`: upload exceeds 10 MiB.
- `415 Unsupported Media Type`: unsupported extension/type.
- `422 Unprocessable Entity`: invalid filename or empty content.
- `409 Conflict`: parent Knowledge Base is disabled.

### 7.2 List Documents

Endpoint: `GET /api/workspaces/{workspace_id}/knowledge-bases/{knowledge_base_id}/documents`

Success: `200 OK`

Returns all Document metadata in the parent Knowledge Base in the ordering from
BR-009. An empty Knowledge Base returns an empty list.

### 7.3 Get Document

Endpoint: `GET /api/workspaces/{workspace_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}`

Success: `200 OK`

A missing, cross-Workspace, or wrong-parent Document returns `404` with:

```json
{
  "detail": "Document not found"
}
```

### 7.4 Update Document Status

Endpoint: `PATCH /api/workspaces/{workspace_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}`

Request:

```json
{
  "status": "disabled"
}
```

The only client-requestable statuses are `ready` and `disabled`, subject to the
state transitions in BR-006. Invalid transitions return `409 Conflict`.

Success: `200 OK`

### 7.5 Document Response

```json
{
  "id": "document-uuid",
  "workspace_id": "workspace-uuid",
  "knowledge_base_id": "knowledge-base-uuid",
  "file_name": "employee-handbook.pdf",
  "file_type": "pdf",
  "status": "ready",
  "version": 1,
  "processing_error": null,
  "created_by": "user-uuid",
  "created_at": "2026-09-16T10:00:00Z",
  "updated_at": "2026-09-16T10:00:00Z"
}
```

`extracted_text` is deliberately absent.

## 8. Error Behavior

- `401 Unauthorized`: existing Bearer authentication behavior.
- `403 Forbidden`: existing Workspace access behavior; unauthorized mutations
  use `Knowledge administrator role required`.
- `404 Not Found`: missing route Workspace, Knowledge Base, or scoped Document.
- `409 Conflict`: disabled parent Knowledge Base or invalid status transition.
- `413 Payload Too Large`: upload exceeds the configured 10 MiB limit.
- `415 Unsupported Media Type`: unsupported file type.
- `422 Unprocessable Entity`: invalid route/payload data, filename, or empty
  content.

Unexpected parser or database details must not be exposed to clients.

## 9. Application Structure

```text
HTTP request
-> Current User dependency
-> Active Workspace Membership dependency
-> Knowledge Administrator dependency for mutations
-> Workspace-scoped Knowledge Base lookup
-> Document service
-> File validation / text extractor
-> SQLAlchemy
-> PostgreSQL
```

Routes own HTTP contracts, the service owns persistence and state transitions,
and a small extraction module owns TXT/Markdown decoding and PDF extraction.
No repository layer, task queue, object-storage abstraction, or RAG service is
introduced.

## 10. Acceptance Criteria

### AC-001 - Migration

Alembic upgrades from `0003` to `0004`, creates the specified table,
constraints, and indexes, and downgrades to `0003` without changing prior
tables or migrations.

### AC-002 - Supported Uploads

An active `knowledge_admin` or `system_admin` can upload valid PDF, TXT, and
Markdown files to an active Knowledge Base. Successful extraction persists the
text internally and returns ready metadata without exposing that text.

### AC-003 - Processing Failure Visibility

A supported but malformed, encrypted, or non-text-extractable document produces
a persisted failed Document with a sanitized error and no extracted text.

### AC-004 - Read and Ordering

Any active Workspace member can list and retrieve metadata for Documents in the
authorized parent Knowledge Base. Results include all statuses and use the
specified deterministic ordering.

### AC-005 - Disable and Re-enable

An active `knowledge_admin` or `system_admin` can transition a ready Document to
disabled and a disabled Document back to ready. Other transitions are rejected.

### AC-006 - Role Enforcement

An active `employee` or `agent_admin` receives 403 when uploading or changing a
Document.

### AC-007 - Isolation

Missing, invited, or disabled Memberships; disabled Workspaces; cross-Workspace
Knowledge Bases; and cross-parent Document IDs cannot bypass Workspace
isolation.

### AC-008 - File Safety and Validation

Unsupported, oversized, empty, invalidly named, and incorrectly encoded files
are handled according to the documented error contract without persisting raw
content or exposing internal details.

### AC-009 - Existing Behavior

Authentication, Workspace, Membership, Knowledge Base, migrations, health,
CORS, and frontend behavior continue to pass existing verification.

## 11. Test Requirements

PostgreSQL-backed tests must cover:

- Migration `0003 -> 0004`, schema constraints/indexes, head, and downgrade.
- Authentication on every Document route.
- PDF, TXT, and Markdown upload and text extraction.
- Creator, parent IDs, version, timestamps, and ready status persistence.
- Extracted-text persistence and exclusion from API responses.
- Empty, unsupported, oversized, malformed, encrypted/non-text PDF, and
  non-UTF-8 input handling.
- Failed status and sanitized processing errors.
- Ordered lists, empty lists, and all-status visibility.
- Ready-to-disabled and disabled-to-ready transitions.
- Rejection of invalid state transitions and unknown request fields.
- Employee and agent-administrator mutation denial.
- Invited/disabled Membership and disabled Workspace denial.
- Disabled Knowledge Base upload denial and metadata visibility.
- Cross-Workspace and wrong-parent Knowledge Base/Document isolation.
- Regression coverage for existing APIs.

Verification must include:

- Feature-specific PostgreSQL integration tests.
- Full backend `pytest` suite against PostgreSQL with no skips.
- Backend Ruff checks.
- Alembic head and schema-drift checks.
- Frontend unit tests, lint, and production build.
- `git diff --check`.

SQLite must not replace PostgreSQL integration tests.

## 12. Approval Record

Human approval was granted on 2026-09-16 for:

- Alembic revision `0004` and the `documents` schema.
- The Document read/mutation authorization matrix and tenant-isolation rules.
- Persisting extracted enterprise text in PostgreSQL while not retaining the
  source binary.
- Adding the small `python-multipart` and `pypdf` runtime dependencies.

Implementation remains limited to the migration, authorization policy,
extracted-text retention model, dependencies, and API scope defined in this
specification.

## 13. Out of Scope

- Frontend Document management UI.
- Original binary retention, download, object storage, antivirus scanning, or
  data-loss-prevention integration.
- Asynchronous workers, retries, queues, scheduling, or progress percentages.
- Document replacement, logical version families, automatic version
  increments, or superseding old versions.
- Editing extracted content or exposing full extracted text through an API.
- OCR, scanned PDFs, complex tables, layout preservation, images, office
  documents, audio, or video.
- Chunking, embeddings, pgvector, retrieval, reranking, LLM generation, and
  citations.
- Fine-grained document/department permissions or custom roles.
- Hard deletion or bulk operations.
- Agents, tools, workflows, approvals, execution logs, or evaluation.
