# Feature 009 - Grounded RAG Answer and Citation

Status: Approved - implementation in progress
Milestone: 2

## 1. Goal

Turn the authorized semantic retrieval capability from Feature 008 into the
smallest portfolio-ready enterprise knowledge question-answering flow:

```text
Question
-> authenticated Workspace and Knowledge Base authorization
-> existing semantic retrieval
-> grounded generation
-> answer or explicit unsupported result
-> server-verifiable citations
```

The feature must preserve the existing Workspace, Knowledge Base, and Document
isolation rules. It adds generation after retrieval; it does not replace,
fork, or bypass Feature 008 retrieval.

## 2. Smallest Portfolio-Ready MVP

This feature will:

- Add one synchronous, non-streaming Knowledge Base answer endpoint.
- Reuse the existing active Workspace Membership dependency.
- Call the existing `search_knowledge_base` service with the Feature 008
  default of five results.
- Generate an answer only from those retrieved chunks through a narrow,
  project-owned generation provider interface.
- Return an explicit `unsupported` result when the retrieved evidence is not
  sufficient.
- Resolve every public citation from server-owned retrieval results rather
  than model-supplied database metadata.
- Return document identity, file name, document version, chunk identity,
  chunk index, and a bounded, verified excerpt for every citation.
- Add deterministic fakes and automated tests that never call a live model.
- Add a small local benchmark runner and documentation for the prepared
  EnterpriseRAG-Bench subset.
- Measure the unchanged Feature 008 retrieval baseline before using answer
  results to inspect citation correctness, no-answer behavior, and answer-fact
  coverage.

No database migration, persistence model, frontend chat experience, or new
runtime dependency is required.

## 3. Existing Foundation and Reuse Decision

### 3.1 Existing product path

Feature 009 reuses these existing components:

- Document upload:
  `POST /api/workspaces/{workspace_id}/knowledge-bases/{knowledge_base_id}/documents`
- Document indexing:
  `POST /api/workspaces/{workspace_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/index`
- Semantic search:
  `POST /api/workspaces/{workspace_id}/knowledge-bases/{knowledge_base_id}/search`
- `EmbeddingProvider` and the configured OpenAI embedding implementation.
- `ActiveWorkspaceMembership`, which authenticates the User and requires an
  active Membership in an active Workspace.
- Feature 008 retrieval filters for route Workspace, route Knowledge Base,
  matching embedding model, and ready Documents.

The answer service must call the existing retrieval service. It must not
reimplement vector search or perform a second, less restrictive Chunk query.

### 3.2 Generation implementation candidates

| Candidate | Functional fit | Dependency and operations | Decision |
|---|---|---|---|
| Existing official OpenAI Python SDK and Responses API | Supports text generation and strict structured output; the SDK is already a runtime dependency | Smallest integration surface; sends the question and retrieved enterprise text to the configured OpenAI account | Proposed for approval |
| Full LangChain or LlamaIndex generation/RAG stack | Can orchestrate RAG | Broad framework would duplicate project-owned retrieval and add unnecessary abstractions | Reject |
| Raw HTTP client | Can call the API | Reimplements SDK authentication, timeouts, errors, and response types | Reject |
| Local generation model | Avoids external generation transfer | Adds a large model/runtime and deployment surface not justified by this feature | Defer |

The proposed generation model is `gpt-5.6-terra`, selected as the current
balanced intelligence/cost tier for a constrained grounded-answer task. The
model, contract, data transfer, limits, cost, and failure behavior remain
subject to the explicit human gate in Section 13.

Sources consulted on 2026-09-20:

- <https://developers.openai.com/api/docs/models/gpt-5.6-terra>
- <https://developers.openai.com/api/reference/cli/resources/responses/methods/create>
- <https://developers.openai.com/api/docs/guides/structured-outputs>

## 4. Business Rules

### BR-001 - Authentication, authorization, and isolation

Any authenticated User with an active Membership in an active Workspace may
ask a question against an active Knowledge Base in that Workspace, matching
Feature 008 search access.

The route must use `ActiveWorkspaceMembership`. The answer service must invoke
the existing workspace-scoped retrieval service using the route
`workspace_id` and `knowledge_base_id`.

Cross-Workspace and wrong-parent identifiers must not disclose foreign data.
Disabled Knowledge Bases and non-ready or disabled Documents remain excluded
through the existing retrieval path. Generation must never query Chunks or
Documents independently.

### BR-002 - Retrieval contract

Generation uses exactly the first five results returned by Feature 008
semantic retrieval. Feature 009 does not make Top-K client-configurable and
does not add a threshold, reranker, hybrid search, or approximate vector
index.

Feature 008 chunking remains unchanged:

- `chunk_size = 1000`
- `chunk_overlap = 200`

The retrieval baseline must be measured before any later tuning is proposed.

### BR-003 - Evidence-only generation

The generation instructions must state that retrieved text is the only source
of enterprise facts. The model must not fill gaps with general knowledge,
assumptions, or facts from prior context.

Retrieved text is untrusted data. Instructions found inside a retrieved chunk
must be treated as quoted evidence, not as system or developer instructions.
No tools, web search, file search, previous response, or conversation state may
be available to generation.

### BR-004 - Unsupported result

The public result has one of two statuses:

- `answered`: the retrieved evidence is sufficient for the returned answer.
- `unsupported`: the retrieved evidence is absent, irrelevant, conflicting in
  a way that prevents a supported conclusion, or otherwise insufficient.

If retrieval returns no chunks, the backend returns `unsupported` without
calling the generation provider.

An `unsupported` response has `answer = null`, an empty citation list, and a
stable server-owned message. A model refusal, malformed provider response, or
provider failure is not evidence insufficiency and must not be mislabeled as
`unsupported`.

### BR-005 - Model-facing evidence references

The backend labels retrieved results with request-local opaque references
`E1` through `E5`. Only those labels, their ordered chunk text, and the User's
question are included in the generation input.

The model is not given and must not return trusted Workspace IDs, Knowledge
Base IDs, Document IDs, Chunk IDs, file names, user metadata, or authorization
metadata.

For an answered result, the model returns:

- an answer,
- one or more cited evidence labels, and
- an exact excerpt for each cited label.

### BR-006 - Server-verifiable citations

The backend validates generation output before constructing the API response:

- every evidence label exists in this request's retrieval results,
- no more than five citations are returned,
- every excerpt is between 1 and 500 characters after validation,
- every excerpt is an exact contiguous substring of the corresponding
  retrieved Chunk,
- an answered result has a non-empty answer and at least one citation,
- an unsupported result has no answer and no citations.

The backend then maps each validated evidence label to the server-owned
retrieval result and emits the real Document and Chunk metadata. Arbitrary
model-generated identifiers are never accepted.

Duplicate evidence labels fail validation rather than being silently
collapsed. Citation order is deterministic. Citation excerpts contain only
the model-selected, verified substring and never more than 500 characters.

### BR-007 - Generation provider boundary

Generation is hidden behind a narrow project-owned protocol that accepts the
question plus ordered evidence items and returns an internal answered or
unsupported result. Tests inject deterministic fakes.

The boundary is not a general model marketplace, prompt framework, agent, or
tool-calling abstraction.

### BR-008 - External data handling

Subject to human approval, a generation request sends only:

- the User's normalized question,
- the text of up to five chunks returned by authorized Feature 008 retrieval,
- request-local labels `E1` through `E5` and their order,
- fixed grounding and structured-output instructions.

It does not send Workspace ID, Knowledge Base ID, Document ID, Chunk ID, file
name, document version, User ID, email, Membership, role, JWT, database
credential, or API key as model input or request metadata.

The Responses request uses `store = false`. Prompts, retrieved text, raw
provider responses, and provider error bodies must not be persisted or logged
by the application.

### BR-009 - Context and output limits

The endpoint retains the Feature 008 question limit of 1 to 2,000 trimmed
characters and fixed Top-5 retrieval.

The proposed provider request has:

- a hard 12,000-token local input budget for the complete instructions,
  question, labels, and retrieved text,
- `truncation = "disabled"`, so evidence is never silently dropped,
- `max_output_tokens = 1200`, including visible and reasoning tokens,
- low reasoning effort,
- no streaming, tools, background mode, or conversation state.

If the complete request exceeds the local input budget, the backend fails
safely with a sanitized service error rather than truncating evidence. The
input budget is intentionally far below the proposed model context window and
does not change stored chunks.

### BR-010 - Failure behavior

- Missing generation configuration returns `503 Service Unavailable`.
- Provider timeout, rate limit, unavailable response, refusal, incomplete
  output, context-limit failure, or schema/semantic validation failure returns
  a sanitized `502 Bad Gateway`.
- No automatic retry is performed; the endpoint is safe for the client to
  retry.
- The proposed SDK client timeout is 30 seconds and `max_retries = 0`.
- Errors must not include the question, chunk text, API key, provider response
  body, or stack trace.

Embedding failures continue to use the existing Feature 008 error contract.

## 5. API / Data Contract

### 5.1 Ask a grounded question

Endpoint:

`POST /api/workspaces/{workspace_id}/knowledge-bases/{knowledge_base_id}/answer`

Request:

```json
{
  "question": "What is the travel reimbursement limit?"
}
```

Validation:

- `question` is trimmed and contains 1 to 2,000 characters.
- unknown fields are rejected.
- retrieval limit is server-owned and fixed at five.

Answered response: `200 OK`

```json
{
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
      "excerpt": "...exact excerpt from the retrieved chunk..."
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
```

Unsupported response: `200 OK`

```json
{
  "question": "What is the production value that is not documented?",
  "status": "unsupported",
  "answer": null,
  "message": "The retrieved knowledge does not contain enough evidence to answer this question.",
  "citations": [],
  "generation": {
    "model": "gpt-5.6-terra",
    "reasoning_effort": "low",
    "retrieval_limit": 5,
    "prompt_version": "grounded-answer-v1",
    "max_input_tokens": 12000,
    "max_output_tokens": 1200,
    "input_tokens": null,
    "output_tokens": null,
    "total_tokens": null
  }
}
```

Errors:

- `401 Unauthorized`: missing or invalid authentication.
- `403 Forbidden`: missing active Workspace Membership.
- `404 Not Found`: scoped Workspace or Knowledge Base not found.
- `409 Conflict`: Knowledge Base is disabled.
- `422 Unprocessable Entity`: the complete deterministic application input
  exceeds the configured 12,000-token budget; no generation call is made.
- `502 Bad Gateway`: sanitized embedding or generation provider failure, or
  invalid generation output.
- `503 Service Unavailable`: required embedding or generation provider is not
  configured.

### 5.2 Internal generation result

The strict provider-facing schema is equivalent to:

```json
{
  "status": "answered",
  "answer": "Grounded answer text",
  "citations": [
    {
      "evidence_ref": "E1",
      "excerpt": "Exact contiguous text copied from E1"
    }
  ]
}
```

or:

```json
{
  "status": "unsupported",
  "answer": null,
  "citations": []
}
```

The model-facing schema contains no database identifiers. SDK parsing and
Pydantic validation are followed by the cross-field and exact-substring checks
in BR-006.

## 6. Application Structure

```text
Answer request
-> current User authentication
-> active Workspace Membership authorization
-> existing Feature 008 search service with limit 5
-> empty retrieval: server-owned unsupported result
-> request-local evidence labels
-> narrow generation provider
-> strict schema and semantic validation
-> map labels to server-owned retrieval metadata
-> answer plus citations
```

No new persistence layer is introduced. Answer and provider payloads are not
stored.

## 7. Configuration and Dependencies

Proposed configuration:

- `GENERATION_MODEL=gpt-5.6-terra`
- `GENERATION_MAX_INPUT_TOKENS=12000`
- `GENERATION_MAX_OUTPUT_TOKENS=1200`

`OPENAI_API_KEY` and the existing 30-second OpenAI timeout are reused. The
generation model and limits are fixed contracts for this feature rather than
arbitrary per-request values.

The existing `openai>=3.8,<4.0` SDK and existing Pydantic/tiktoken packages are
reused. No new runtime dependency is proposed.

## 8. Benchmark Support

### 8.1 Source and repository policy

The benchmark uses the prepared local subset at a caller-supplied path, such
as:

`D:\Datasets\EnterpriseRAG-Bench\feature009`

It is derived from
[onyx-dot-app/EnterpriseRAG-Bench](https://github.com/onyx-dot-app/EnterpriseRAG-Bench),
which is MIT licensed. Repository benchmark documentation and generated result
metadata must preserve that attribution and license notice.

The 200 upstream corpus files are never copied into or committed to this
repository. The runner accepts the benchmark root as an argument and validates
the expected local files:

- `docs/`
- `questions.jsonl`
- `corpus_manifest.json`
- `selection_report.json`
- `SOURCE.md`

### 8.2 Prepared subset

- source Confluence corpus: 5,189 Documents,
- selected corpus: 200 Documents,
- selected questions: 24,
- gold Documents: 34,
- hard distractors: 100,
- random distractors: 66,
- missing gold Documents: 0,
- deterministic selection seed: `20260920`.

Question distribution:

- basic: 5,
- semantic: 8,
- intra-document reasoning: 2,
- project related: 2,
- constrained: 2,
- completeness: 2,
- conflicting information: 1,
- information not found: 2.

### 8.3 Runner workflow

A small Python CLI under `benchmarks/enterprise_rag/` will use authenticated
product APIs and caller-supplied configuration. It will support separate,
resumable stages:

1. Validate the local benchmark manifest and file set.
2. Require a dedicated benchmark Knowledge Base. A fresh ingest requires zero
   existing Documents; a resumed run requires its Documents to match the saved
   ingest state exactly.
3. Upload the 200 selected TXT files through the existing Document API.
4. Index successfully uploaded ready Documents through the existing indexing
   API.
5. Run all 24 questions through semantic search with limits 3 and 5, without
   changing chunking or retrieval behavior.
6. Save a machine-readable retrieval baseline.
7. After generation is available, run the questions through the answer API and
   save machine-readable answer/citation records for inspection.

Credentials, tokens, host URLs, Workspace IDs, and Knowledge Base IDs come
from CLI arguments or environment variables and are never written to committed
fixtures. Resumable state and generated results default to a caller-selected
output directory. A small sanitized baseline result may be committed, but raw
corpus content and secrets may not.

The runner maps upstream `doc_id` values to product Document IDs using the
validated manifest file name. It preserves `question_id`, `question_type`, and
`expected_doc_ids` in every per-question output record.

Retrieval and answer results are checkpointed after each completed question.
Request-level failures are retained as sanitized records containing a failure
type and HTTP status when available, without exception messages, response
bodies, credentials, or raw enterprise text. A normal rerun skips all recorded
questions; an explicit retry option retries failed records only. Summaries
report total, successful, failed, and pending request counts. Failed or pending
requests remain in applicable quality-metric denominators so failures cannot
inflate the baseline. Search results are never post-filtered to hide Documents
outside the benchmark corpus; the dedicated-Knowledge-Base preflight enforces
the corpus invariant before measurement instead.

### 8.4 Retrieval metrics

The retrieval baseline includes at minimum:

- **Retrieval Hit@3:** for answerable questions, the fraction where at least
  one expected Document appears among the first three ranked Chunk results.
- **Retrieval Hit@5:** for answerable questions, the fraction where at least
  one expected Document appears among the first five ranked Chunk results.
- **Document Recall@5:** macro-average across answerable questions of
  `|expected_doc_ids intersect document IDs in the first five Chunk results|
  / |expected_doc_ids|`.

The two `info_not_found` questions have no expected Documents and are excluded
from retrieval-hit and document-recall denominators. Counts and denominators
must be saved alongside rates.

### 8.5 Answer inspection

Answer evaluation remains a feature-level benchmark aid, not the Milestone 4
evaluation product. Per-question records include the API result plus the
upstream `gold_answer` and `answer_facts` for review.

The generated summary and review artifact support inspection of:

- citation validity: every API citation is bound to a retrieved chunk,
- expected-document citation precision and question-level expected citation
  coverage,
- unsupported accuracy for `info_not_found` questions,
- unsupported rate for answerable questions,
- answer correctness and answer-fact coverage through a machine-readable
  manual review template with one review field per upstream answer fact.

No second live judge model, evaluation dashboard, dataset database, or tuning
loop is introduced.

## 9. Acceptance Criteria

### AC-001 - Existing authorization and retrieval are reused

The answer endpoint requires an active Workspace Membership and reaches
generation only through the existing Feature 008 search service. Cross-tenant,
disabled Knowledge Base, and disabled/non-ready Document behavior matches
Feature 008.

### AC-002 - Grounded answer

When retrieved evidence is sufficient, the endpoint returns an answered result
whose provider-selected evidence references all resolve to actual retrieval
results and whose excerpts are verified substrings of those chunks.

### AC-003 - Explicit unsupported result

Empty or insufficient evidence returns the documented `unsupported` contract
without fabricated enterprise facts. Empty retrieval does not call generation.

### AC-004 - Server-verifiable citations

Every citation is constructed from server-owned retrieval metadata and
contains Document ID, file name, document version, Chunk ID, chunk index, and
an excerpt of at most 500 verified characters. Unknown evidence references or
non-matching excerpts fail closed.

### AC-005 - Provider isolation and validation

The generation integration uses the narrow project-owned interface, strict
structured output, semantic validation, sanitized failures, no tools, no
response storage, no retries, and the documented limits.

### AC-006 - No live calls in automated tests

All required automated tests use fake embedding and generation providers and
pass without OpenAI credentials, internet access, or paid API calls.

### AC-007 - Retrieval baseline

The local runner can ingest/index the prepared external 200-Document subset,
run all 24 questions, preserve question and expected Document IDs, calculate
Hit@3, Hit@5, and Document Recall@5, and save machine-readable results without
requiring raw corpus files in Git. It enforces a dedicated clean Knowledge Base,
verifies resumed targets against ingest state, checkpoints each question, and
supports explicit retry of sanitized failure records.

### AC-008 - Answer inspection

The runner saves enough per-question and summary data to inspect citation
correctness, no-answer behavior, and answer correctness/fact coverage without
becoming the Milestone 4 evaluation product.

### AC-009 - Existing behavior

Authentication, Workspace, Membership, Knowledge Base, Document, Feature 008
indexing/search, migrations, health, CORS, and frontend behavior continue to
pass existing verification.

## 10. Test Requirements

Automated tests must cover:

- answer request trimming, length limits, and unknown fields,
- all active Workspace roles and inactive/missing Membership denial,
- disabled Workspace and Knowledge Base behavior,
- cross-Workspace and wrong-parent isolation,
- proof that the existing retrieval service is the only evidence source,
- fixed retrieval limit of five,
- empty retrieval bypassing generation,
- answered and unsupported fake-provider results,
- rejection of invented, duplicate, or out-of-range evidence labels,
- exact excerpt membership and 500-character bound,
- answered/unsupported cross-field invariants,
- deterministic server mapping to Document and Chunk metadata,
- exclusion of disabled/non-ready Documents through retrieval,
- prompt-injection-shaped text remaining evidence rather than instructions,
- local input budget and output-limit handling,
- missing configuration, timeout, provider errors, refusal, incomplete output,
  and malformed structured output,
- absence of secrets, question text, chunk text, and provider bodies from
  errors and logs,
- benchmark manifest validation, dedicated-Knowledge-Base preflight, resumed
  target consistency, upstream-ID mapping, metric denominators and formulas,
  per-question checkpointing, sanitized failures, explicit failure retry, and
  output schema,
- regressions for the existing Feature 008 endpoints.

Verification must include:

- feature-specific PostgreSQL integration tests,
- the full backend `pytest` suite against PostgreSQL with no skips,
- backend Ruff checks,
- Alembic head and schema-drift checks even though no migration is expected,
- benchmark runner unit tests using temporary synthetic fixtures rather than
  committed upstream corpus files,
- frontend unit tests, lint, and production build,
- `git diff --check`.

## 11. Security and Privacy Review Points

- Authorization remains before retrieval and generation.
- Provider input is minimized and contains no tenant or database identifiers.
- Retrieved Documents are treated as untrusted prompt data.
- Response storage is disabled at the API request level.
- Model-supplied database IDs are never trusted.
- Citation excerpts are verified against authorized retrieved text.
- Application logs and errors exclude prompts, evidence, secrets, and raw
  provider payloads.
- No answer or citation data is persisted in this feature.

## 12. Out of Scope

- Changes to `chunk_size=1000` or `chunk_overlap=200`.
- Client-configurable Top-K, retrieval tuning, relevance thresholds,
  reranking, hybrid search, HNSW, or IVFFlat.
- New embedding providers, generation provider marketplace, broad AI
  framework, or local model runtime.
- Streaming, conversation persistence, response persistence, prompt history,
  or frontend chat UI.
- Agents, tool calling, workflows, human approval, or intent routing.
- Execution logs, evaluation database, evaluation dashboard, bad-case product,
  or automatic LLM-as-judge evaluation.
- Database migrations or new tables.
- Bulk product APIs, background ingestion, queues, workers, retries, or
  scheduling.
- Committing the 200 EnterpriseRAG-Bench source Documents.
- Feature 010 or any later roadmap feature.

## 13. Required Human Approval Gate

Feature 008 approval covered sending chunk and query text to the OpenAI
Embeddings API only. It did not cover sending a User question and retrieved
enterprise text to a generation model.

Before implementing the live provider, a human must approve all of the
following proposed terms:

1. **Model:** `gpt-5.6-terra`, fixed by configuration for Feature 009.
2. **API and SDK:** existing official OpenAI Python SDK, synchronous Responses
   API structured parsing, `store=false`, no tools, and no streaming.
3. **External text and metadata:** normalized question; up to five authorized
   retrieved Chunk texts; ephemeral `E1`-`E5` labels/order; fixed instructions.
   No real tenant, User, Document, Chunk, filename, or authorization metadata.
4. **Validation:** strict structured output parsed into Pydantic, followed by
   answered/unsupported invariant checks, evidence-label allowlisting, exact
   excerpt substring verification, and server-side citation metadata mapping.
5. **Limits:** fixed Top-5 evidence, 12,000-token local input budget,
   `truncation=disabled`, 1,200 maximum output tokens, low reasoning effort,
   and question length 1-2,000 characters.
6. **Cost/configuration:** current published standard pricing is billed per
   input/output token; at the hard budgets the generation ceiling is about
   $0.0384 per request (12,000 input tokens and 1,200 output/reasoning tokens),
   excluding embeddings. The 24-question generation benchmark ceiling is
   about $0.92, while typical usage should be materially lower. The existing
   `OPENAI_API_KEY` is reused and three non-secret fixed generation settings
   are added.
7. **Failure and timeout:** 30-second timeout, zero SDK retries, sanitized 502
   for provider/validation failures, 503 for missing configuration, and a
   server-owned unsupported 200 only for evidence insufficiency.
8. **Dependencies:** no new runtime dependency; reuse `openai`, Pydantic, and
   tiktoken already present in the backend.

Human approval was granted on 2026-09-20 for all terms above, with these
clarifications incorporated into the implementation contract:

- the 12,000-token limit is an application cost/evidence budget, not a model
  context-window claim,
- the complete instructions, serialized question/evidence, and strict output
  schema are counted deterministically before the request,
- over-budget input returns a documented sanitized application error without
  truncation or a provider call,
- duplicate citations fail validation rather than being collapsed,
- benchmark records include the generation model, reasoning effort, retrieval
  limit, prompt/schema version, fixed budgets, and token usage when available.

No further approval is required for the scoped implementation. A new human
gate is still required if implementation would change authentication,
authorization, tenant isolation, database schema, the approved external data
boundary, dependencies, or architecture.
