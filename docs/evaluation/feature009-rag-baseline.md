# Feature 009 RAG Baseline

## Retrieval baseline

This baseline uses the prepared Confluence subset derived from
[onyx-dot-app/EnterpriseRAG-Bench](https://github.com/onyx-dot-app/EnterpriseRAG-Bench),
which is MIT licensed. The upstream corpus remains external to this repository.

| Measure | Result |
| --- | ---: |
| Corpus | 200 Documents |
| Questions | 24 |
| Answerable questions | 22 |
| Successful retrieval requests | 24/24 |
| Retrieval Hit@3 | 21/22 (95.45%) |
| Retrieval Hit@5 | 21/22 (95.45%) |
| Document Recall@5 | 20/22 (90.91%) |

The two `info_not_found` questions have no expected Documents and are excluded
from the retrieval metric denominators.

The measured configuration remained fixed at retrieval Top-K 5,
`chunk_size=1000`, and `chunk_overlap=200`. No retrieval tuning was performed
after observing this baseline. In particular, chunking, embeddings, retrieval
parameters, and the benchmark dataset were not changed in response to the
results.

## Known retrieval bad cases

- `qst_0234` (`semantic`): complete retrieval miss; Document Recall@5 is 0.
- `qst_0358` (`project_related`): partial multi-Document retrieval; Document
  Recall@5 is 0.5.
- `qst_0433` (`completeness`): partial multi-Document retrieval; Document
  Recall@5 is 0.5.

These cases are retrieval limitations in the frozen baseline. A later answer
evaluation must not attribute downstream failures to generation when the
retrieved evidence was missing or incomplete.

## Live generation benchmark status

**DEFERRED.**

The local development/Codex execution environment could not reliably inherit
the product authentication and OpenAI credentials required to run the live
answer benchmark. This is an environment and evaluation limitation, not a
claimed product result.

No live generation quality, citation, no-answer, answer-correctness, or token
usage metrics are reported here. The live answer benchmark must be rerun before
publishing generation quality metrics.

Feature 009 remains implementation-complete based on its automated fake-provider
coverage and regression verification. The deferred live evaluation does not
change the generation contract, authorization behavior, database schema, or
benchmark inputs.
