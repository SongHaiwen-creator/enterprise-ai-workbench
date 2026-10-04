# Business baseline — verification and execution status

Date: 2026-10-05 (Asia/Shanghai). Related Issue: #44.
Source baseline: merged `origin/main` `8d9f3ea0f0f93dd70543056d011f24e99a8f5774`.
User requested dataset construction, business benchmark and actual measurement
after the Feature 018 runtime upgrade. No new roadmap product feature is implemented.

## Prepared artifacts

- 12 original synthetic policies; 108 typed cases; 74 development / 34 holdout.
- Counts: knowledge 48, tool planning 24, policy 24, refusal 12.
- Gold answers, supporting facts, exact evidence quotes and scenario grouping.
- Corpus/case fingerprint:
  `cdfb0b2a9f1cb2d590d6d8354173b222e0aa3511d2d4e9109cb4c122e3ca9adc`.
  Identity uses canonical JSON values and normalized document text, so Git line
  ending conversions do not change it; this has a cross-line-ending regression.
- Existing authenticated APIs only; 26 datasets of at most five cases each.
- Separate retrieval/answer/Agent stages, local evidence and nullable signed review.
- A real-task business pilot plan with task success, time including verification,
  application first-acceptance and escalation measures. No inferred business ROI.

## Verification

| Check | Result |
|---|---|
| Corpus validation | 108 typed cases; valid quotes, unique IDs/questions; no cross-split family leakage |
| New benchmark unit + PostgreSQL API checks | 24 passed, no skips |
| Full backend suite after review fixes | 1625 passed, no skips; 74 existing deprecation warnings; subsequent canonical-fingerprint change covered by the 24-test selection |
| Ruff backend + benchmark | passed |
| Frontend lint / production build | passed; no frontend source change |
| Independent review and follow-up | all three findings fixed; no remaining blockers |
| `git diff --check` | passed |

PostgreSQL tests use only the dedicated `enterprise_ai_workbench_test` through the
existing safety fixture, never the runtime DB. Model providers in automated tests
are deterministic fakes. The import/resume test creates a dedicated KB/Agent,
indexes with a fake provider, imports all cases, verifies idempotent preparation,
checks that original test data remain, and detects edited questions. Permission-only
configuration probes are verified to make no provider calls. These are software
tests, not live Agent quality results.

## Review corrections

- Disable HTTPX environment proxies (`trust_env=False`) and redirects so loopback
  credentials do not pass through an external environment proxy.
- Persist a pending marker before paid search/answer requests. A killed process
  or lost response blocks automatic replay; raw exception bodies are never printed.
- Freeze provider, instructions/schema hashes, policy and registry configuration
  from a permission-only Run; compare every subsequent Agent snapshot and each
  answer's generation metadata. Persist and stop on drift.
- Preserve required nullable keys inside typed expectations; the initial import
  test exposed recursive omission of tool expectation keys. The fix was verified
  with full 108-case import before any runtime import.
- Activate only the new benchmark Agent and newly created Tools via normal APIs.
  Existing disabled Tools are never automatically enabled.

The independent reviewer performed a read-only audit, not shared database tests.
The last corpus-portability selection initially encountered a Windows atomic-file
replace permission error in a reused pytest temp directory. A new isolated temp
directory passed all 24 tests without code/test relaxation; that failed attempt is
not counted as passing evidence. Unrecoverable checkpoint writes always stop API
execution rather than replaying an ambiguous operation.
Search does not expose query-embedding metadata; Index does not expose a chunking
implementation hash. The runner cannot prove that no backend implementation change
occurred between a probe and request; use the same backend build during measurement.

## Actual business execution

**Partial, blocked on normal product credentials.**

- 24 offline policy simulations executed: 24 passed (18 development, 6 holdout).
- Live preparation / RAG / Agent attempted entry, then stopped before login, paid
  calls or runtime writes because `WORKBENCH_EMAIL`/`WORKBENCH_PASSWORD` and
  `WORKBENCH_ACCESS_TOKEN` are absent.
- Local merged API started on loopback port 8000; `/health` returned `{"status":"ok"}`.
- Runtime version remains `0013`: 1 Agent, 1 KB, 200 Documents, 1 Dataset, 4 Cases,
  1 Run, 1 Approval, 1 Mock IT request. Counts match the pre-benchmark inventory.
- 108 cases have **not** been imported into the runtime database. No fresh RAG
  recall, live answer correctness or Agent pass-rate result is claimed.
- Gold is agent-authored, not business-owner-certified. Answer facts are pending
  signed review; synthesis does not substitute for real business pilot evidence.

Actual offline measures are in `business-baseline-v1-policy-summary.json` and
`business-baseline-v1-report.md`. Normal local login setup and resume commands are
in `benchmarks/business_baseline/README.md`; do not put secrets in chat or Git.
Issue #44 stays open and the PR remains a draft until measurement prerequisites
and the requested live result are handled. Human merge remains required.
