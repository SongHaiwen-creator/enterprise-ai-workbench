# Business Evaluation Baseline v1

## Goal

Turn the existing evaluation APIs into a reproducible employee-service benchmark.
Measure retrieval, grounded answering and structured Agent behavior separately,
with evidence for failures and explicit denominators. This is data and benchmark
work requested by the user after Feature 018, not implementation of Features 019–023.

## Scope

- Original, explicitly synthetic Chinese employee-service policies and questions.
- 108 cases: 48 knowledge, 24 tool planning, 24 policy simulation, 12 refusal.
- Document-level evidence, literal supporting quotes and answer fact rubrics.
- Development/holdout labels grouped by scenario family. Holdout is frozen before
  measurement, not an independent human-authored or real-traffic test set.
- Existing authenticated APIs only; dedicated benchmark KB and Agent; batches of
  at most five active cases, retaining original user-created datasets and resources.
- A sequential resumable local CLI for preparation, measurement and reporting.
- Representative live failures are triaged through existing Feature 018 Bad Case
  APIs, retaining their source results and leaving findings open for review.
- Current RAG Top-K 5, chunk size 1000/overlap 200, approved models/prompts unchanged.

## Business rules

Synthetic rules are illustrative company policy, not claims about a real employer.
Questions and facts are authored before observing model answers. Evidence quotes
must occur in the cited source documents. No automatic tuning or changing gold to
make results pass. Cases are versioned and fingerprinted; a changed corpus requires
a new output directory and baseline. Development and holdout scenario families do
not overlap. Report each category and split separately, not a business-weighted
overall quality percentage. No SLA or production-readiness claim from this sample.

Knowledge scoring in the product remains structural. Local answer review records
facts and citations; lexical hints are aids, never semantic correctness judgments.
Unreviewed answers remain unreviewed and cannot count as correct. Policy cases are
simulation, not additional penetration tests. Tool cases are dry runs; no adapters,
Approval decisions or IT access writes. No self-issued authentication token or
dependency override may bypass normal login.

## API / data contract

`benchmarks/business_baseline/data/` contains policy `.txt`, `manifest.json`, and
`cases.json`. Each case has a stable ID, split, scenario family, business purpose,
input and typed existing expectation. Knowledge cases additionally contain expected
document IDs, supporting quotes, gold answer, required facts and forbidden claims.

The runner uses existing Knowledge Base/Document/Agent/Tool/Evaluation APIs.
`WORKBENCH_EMAIL`/`WORKBENCH_PASSWORD` or `WORKBENCH_ACCESS_TOKEN` supplies normal
authentication. Credentials stay out of checkpoints, console output and Git.
Live preparation/indexing/measurement requires `--acknowledge-egress`; only this
synthetic corpus, questions, benchmark Agent prompt and registered selector metadata
may use the existing configured OpenAI providers. No new provider or judge.

Output includes resource mappings, fingerprints, per-case results, retrieval
Hit@3/5 and macro Document Recall@5, structural outcomes and coverage/error rates,
answer/citation records, nullable fact-review fields and a report. Failed or pending
cases stay in applicable planned denominators; conditional non-error pass rate is
shown alongside passed/planned, coverage and errors. Missing prerequisites are
reported as blocked, never converted into fake live results. Ambiguous writes stop
for reconciliation; no automatic replay of a POST. Successful measurements are
checkpointed and not repeated on resume. A first systemic provider error stops
paid execution for diagnosis.
After recording an explicit diagnosis, an operator may collect remaining first
attempts for Agent `provider_contract` or the answer endpoint's known generation
HTTP 502 response. These failures stay failures and are never replayed. The latter
does not disclose its exact cause; a diagnosed example cannot establish all HTTP
502 causes. Unknown errors, configuration drift and ambiguous requests still stop.

## Acceptance criteria

1. All 108 cases validate against the product schema and their source evidence.
2. No duplicate IDs/questions or development/holdout family overlap.
3. Existing four user cases, original Agent and public corpus remain untouched.
4. Normal authenticated preparation creates dedicated resources and API-visible
   datasets, each with at most five cases.
5. Live measurements have recorded configuration, fingerprints, denominators and
   actual results; failures and pending observations remain visible.
6. Report clearly distinguishes synthetic benchmark performance, policy simulation,
   structural behavior and human-reviewed answer quality.
7. Credentials, source secrets and raw external corpus are never committed.

## Test requirements

Meaningful offline tests for gold-evidence integrity, split leakage, malformed
expectations, missing/error denominator handling, unreviewed-answer accounting,
checkpoint fingerprint rejection, batching and ambiguous write handling. Existing
PostgreSQL integration regression, backend pytest and Ruff. Frontend is unchanged;
existing lint/build checks remain applicable to repository verification. Automated
tests never call a live provider or reset the runtime database.

## Out of scope

Real business ROI measurement without real tasks and human time/cost baselines;
production traffic sampling; automatic semantic judging; model/prompt changes;
retest linking/version comparison; new public APIs/UI, migrations, dependencies,
authentication/RBAC/policy changes, automatic merges.
