# Feature 009 EnterpriseRAG-Bench Baseline

This development utility runs the deterministic local Confluence subset built
from [onyx-dot-app/EnterpriseRAG-Bench](https://github.com/onyx-dot-app/EnterpriseRAG-Bench).
The upstream benchmark is MIT licensed. Preserve its `SOURCE.md` and license
attribution with every local copy.

The upstream corpus is external input. Do not copy or commit its 200 raw source
documents into this repository. Generated local output defaults to the ignored
`benchmarks/enterprise_rag/output/` directory.

The runner validates the external manifest, uploads and indexes through the
existing product APIs, records the unchanged Feature 008 retrieval baseline,
and then captures Feature 009 answers and a manual fact-review template.

## Expected external files

```text
<benchmark-root>/
  docs/
  questions.jsonl
  corpus_manifest.json
  selection_report.json
  SOURCE.md
```

## Usage

Run from the repository root with the backend development environment:

```powershell
backend\.venv\Scripts\python.exe -m benchmarks.enterprise_rag.runner validate `
  --benchmark-root D:\Datasets\EnterpriseRAG-Bench\feature009
```

Set `WORKBENCH_WORKSPACE_ID`, `WORKBENCH_KNOWLEDGE_BASE_ID`, and either
`WORKBENCH_ACCESS_TOKEN` or `WORKBENCH_EMAIL` plus `WORKBENCH_PASSWORD`. The
default API URL is `http://localhost:8000`; override it with
`WORKBENCH_BASE_URL`.

Run the resumable upload/index stage before measuring retrieval:

```powershell
backend\.venv\Scripts\python.exe -m benchmarks.enterprise_rag.runner ingest `
  --benchmark-root D:\Datasets\EnterpriseRAG-Bench\feature009

backend\.venv\Scripts\python.exe -m benchmarks.enterprise_rag.runner retrieval `
  --benchmark-root D:\Datasets\EnterpriseRAG-Bench\feature009

backend\.venv\Scripts\python.exe -m benchmarks.enterprise_rag.runner answers `
  --benchmark-root D:\Datasets\EnterpriseRAG-Bench\feature009
```

`all` runs those three stages in order. The runner never changes chunk size,
chunk overlap, or retrieval Top-K.

## Outputs

- `ingest_state.json`: resumable upstream-to-product Document mapping.
- `retrieval_baseline.json`: per-question retrieval records plus Hit@3, Hit@5,
  and macro Document Recall@5.
- `answer_baseline.json`: answers, citations, no-answer/citation summaries,
  generation configuration, prompt version, and available token usage.
- `answer_fact_review.json`: gold answer facts beside system answers and
  citations, with nullable fields for manual correctness/fact-coverage review.

Credentials and full raw documents are not written to these files. Answer
outputs retain the API's bounded citation excerpts so citation correctness can
be inspected; keep generated output local unless it has been reviewed for
appropriate disclosure.
