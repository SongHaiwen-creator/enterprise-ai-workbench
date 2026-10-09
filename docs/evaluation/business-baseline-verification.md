# Business baseline — verification and execution status

Updated: 2026-10-09 (Asia/Shanghai). Related Issue: #44; PR #45.
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
| New benchmark unit + PostgreSQL API checks | 31 passed, no skips; including explicit diagnosed-error continuation |
| Full backend suite after review/recovery changes | 1633 passed, no skips; 74 existing deprecation warnings |
| Ruff backend + benchmark | passed |
| Frontend lint / production build | preparation-stage checks passed; frontend source unchanged by recovery/report changes |
| Independent review and follow-up | initial three findings fixed; recovery review found no blockers |
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
- Default stop-on-error remains. After diagnosing a contract defect, explicit
  continuation records a bounded reason and collects remaining first attempts
  only. Agent allows `provider_contract`; answers allow only HTTP 502 with exact
  safe generation-failure detail. Failed rows/denominators remain. Unknown errors,
  timeouts, authentication failures, embedding errors and configuration drift
  still stop; no paid retry or weakened auth. Independently reviewed.

The independent reviewer performed a read-only audit, not shared database tests.
The last corpus-portability selection initially encountered a Windows atomic-file
replace permission error in a reused pytest temp directory. A new isolated temp
directory passed all 24 tests without code/test relaxation; that failed attempt is
not counted as passing evidence. Unrecoverable checkpoint writes always stop API
execution rather than replaying an ambiguous operation.
On October 9 the first recovery selection similarly encountered a Windows atomic
replace `PermissionError` (30 passed, 1 failed). A fresh OS temporary directory
passed all 31 without changing the tests or persistence behavior; the full suite
then passed all 1633 in 86.71 seconds. Pytest cache was disabled for these two
checks to avoid the independently observed local cache-directory ACL warning.
Search does not expose query-embedding metadata; Index does not expose a chunking
implementation hash. The runner cannot prove that no backend implementation change
occurred between a probe and request; use the same backend build during measurement.

## Actual business execution

**All first attempts measured; business-owner review and real-task ROI remain unmeasured.**

- Initial credentials blocker was resolved by the user. Normal product login
  prepared a new KB/Agent, 12 indexed documents, 26 datasets and all 108 cases.
  Product API verification confirmed original 4 user cases and 200 public
  documents remain. No adapter, Approval or IT business write was performed.
- Retrieval: 56/56 successful requests; Hit@3/5 and macro Document Recall@5 were
  100% on 48 answerable questions over the controlled 12-policy corpus.
- Standalone answers: 52 success, 4 HTTP 502, 0 pending; 44/48 answerable questions
  cited the expected document; 8/8 no-evidence questions returned unsupported.
- Agent: all 26 Runs terminal, all 108 cases observed; 91 PASS, 9 FAIL, 8 ERROR.
  Seven errors are provider_contract and one is case_timeout. One knowledge
  routing FAIL and eight tool holdout FAILs are reported without changing gold.
  The latter are safe unsupported responses that conflict with exact route
  expectations; not evidence of unauthorized execution.
- First systemic error stopped measurement for diagnosis. Two separate synthetic
  diagnostic calls were retained and excluded from scores. One confirmed duplicate
  E1 citation references rejected by the existing schema. Other error causes
  remain unconfirmed. Explicit diagnosed-error continuation collected unmeasured
  cases only; the failed first attempts were never replaced/replayed.
- Agent execution spans October 5 and October 9. Local API/container interruption
  was recovered on the same merged backend commit; all five no-provider probes
  matched the frozen snapshot. No migration/model/prompt/policy change.
- Four representative findings were created through existing Feature 018 APIs,
  with open status, original terminal source evidence and creation history.
  Cause descriptions are agent-assisted hypotheses pending business review.
- Gold remains agent-authored. Signed answer review is 0/48; a packet contains all
  source facts, actual first answers and citations. No semantic accuracy or real
  business ROI is claimed; no user time/total cost has been measured.

Actual results are in `business-baseline-v1-live-summary.json` and
`business-baseline-v1-report.md`; the unsigned packet is
`business-baseline-v1-answer-review.md`. Runtime IDs and full checkpoints stay
local/ignored. `business-baseline-v1-policy-summary.json` is the earlier offline
record. Issue #44 stays open until human merge of PR #45; no automatic merge.
