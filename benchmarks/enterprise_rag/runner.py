import argparse
import hashlib
import json
import os
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

BENCHMARK_SOURCE = "onyx-dot-app/EnterpriseRAG-Bench"
BENCHMARK_LICENSE = "MIT"
RETRIEVAL_LIMIT = 5
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200


@dataclass(frozen=True)
class BenchmarkPaths:
    root: Path
    documents: Path
    questions: Path
    manifest: Path
    selection_report: Path
    source: Path


@dataclass(frozen=True)
class ValidatedBenchmark:
    paths: BenchmarkPaths
    manifest: list[dict[str, Any]]
    questions: list[dict[str, Any]]
    selection_report: dict[str, Any]
    file_name_to_doc_id: dict[str, str]


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as source:
        return json.load(source)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise TypeError(f"Expected object at {path}:{line_number}")
            records.append(value)
    return records


def benchmark_paths(root: Path) -> BenchmarkPaths:
    return BenchmarkPaths(
        root=root,
        documents=root / "docs",
        questions=root / "questions.jsonl",
        manifest=root / "corpus_manifest.json",
        selection_report=root / "selection_report.json",
        source=root / "SOURCE.md",
    )


def validate_benchmark(root: Path) -> ValidatedBenchmark:
    paths = benchmark_paths(root.resolve())
    required = (
        paths.documents,
        paths.questions,
        paths.manifest,
        paths.selection_report,
        paths.source,
    )
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise ValueError(f"Benchmark files are missing: {', '.join(missing)}")

    manifest = load_json(paths.manifest)
    selection_report = load_json(paths.selection_report)
    questions = load_jsonl(paths.questions)
    if not isinstance(manifest, list) or not all(isinstance(item, dict) for item in manifest):
        raise ValueError("corpus_manifest.json must contain a list of objects")
    if not isinstance(selection_report, dict):
        raise TypeError("selection_report.json must contain an object")

    document_ids: set[str] = set()
    file_names: set[str] = set()
    file_name_to_doc_id: dict[str, str] = {}
    for item in manifest:
        doc_id = item.get("doc_id")
        file_name = item.get("file_name")
        if not isinstance(doc_id, str) or not doc_id:
            raise ValueError("Every manifest entry requires doc_id")
        if not isinstance(file_name, str) or not file_name:
            raise ValueError("Every manifest entry requires file_name")
        if doc_id in document_ids or file_name in file_names:
            raise ValueError("Manifest document IDs and file names must be unique")
        if Path(file_name).name != file_name or not file_name.lower().endswith(".txt"):
            raise ValueError(f"Unsafe or unsupported benchmark file name: {file_name}")
        if not (paths.documents / file_name).is_file():
            raise ValueError(f"Manifest document is missing: {file_name}")
        document_ids.add(doc_id)
        file_names.add(file_name)
        file_name_to_doc_id[file_name] = doc_id

    selected_count = selection_report.get("selected_question_count")
    corpus_count = selection_report.get("final_corpus_document_count")
    if selected_count != len(questions) or corpus_count != len(manifest):
        raise ValueError("Selection report counts do not match local benchmark files")

    question_ids: set[str] = set()
    for question in questions:
        question_id = question.get("question_id")
        text = question.get("question")
        expected = question.get("expected_doc_ids")
        if not isinstance(question_id, str) or not question_id or question_id in question_ids:
            raise ValueError("Question IDs must be present and unique")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"Question {question_id} has no text")
        if not isinstance(expected, list) or not all(isinstance(item, str) for item in expected):
            raise ValueError(f"Question {question_id} has invalid expected_doc_ids")
        unknown = set(expected) - document_ids
        if unknown:
            raise ValueError(f"Question {question_id} references missing gold documents")
        question_ids.add(question_id)

    return ValidatedBenchmark(
        paths=paths,
        manifest=manifest,
        questions=questions,
        selection_report=selection_report,
        file_name_to_doc_id=file_name_to_doc_id,
    )


def run_metadata(benchmark: ValidatedBenchmark) -> dict[str, Any]:
    return {
        "source": BENCHMARK_SOURCE,
        "license": BENCHMARK_LICENSE,
        "source_corpus": benchmark.selection_report.get("source_corpus"),
        "selection_seed": benchmark.selection_report.get("random_seed"),
        "manifest_sha256": sha256_file(benchmark.paths.manifest),
        "questions_sha256": sha256_file(benchmark.paths.questions),
        "selection_report_sha256": sha256_file(benchmark.paths.selection_report),
        "document_count": len(benchmark.manifest),
        "question_count": len(benchmark.questions),
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "retrieval_limit": RETRIEVAL_LIMIT,
        "recorded_at": utc_now(),
    }


def save_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as destination:
        json.dump(payload, destination, ensure_ascii=False, indent=2, sort_keys=True)
        destination.write("\n")
    temporary.replace(path)


class WorkbenchClient:
    def __init__(
        self,
        base_url: str,
        workspace_id: str,
        knowledge_base_id: str,
        token: str,
        *,
        timeout_seconds: float,
    ) -> None:
        self.workspace_id = workspace_id
        self.knowledge_base_id = knowledge_base_id
        self.client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout_seconds,
        )

    @property
    def knowledge_base_path(self) -> str:
        return (
            f"/api/workspaces/{self.workspace_id}"
            f"/knowledge-bases/{self.knowledge_base_id}"
        )

    def close(self) -> None:
        self.client.close()

    def upload(self, path: Path) -> dict[str, Any]:
        with path.open("rb") as source:
            response = self.client.post(
                f"{self.knowledge_base_path}/documents",
                files={"file": (path.name, source, "text/plain")},
            )
        response.raise_for_status()
        return response.json()

    def list_documents(self) -> list[dict[str, Any]]:
        response = self.client.get(f"{self.knowledge_base_path}/documents")
        response.raise_for_status()
        documents = response.json()
        if not isinstance(documents, list):
            raise TypeError("Document list response is invalid")
        return documents

    def index(self, document_id: str) -> dict[str, Any]:
        response = self.client.post(
            f"{self.knowledge_base_path}/documents/{document_id}/index"
        )
        response.raise_for_status()
        return response.json()

    def search(self, question: str) -> dict[str, Any]:
        response = self.client.post(
            f"{self.knowledge_base_path}/search",
            json={"query": question, "limit": RETRIEVAL_LIMIT},
        )
        response.raise_for_status()
        return response.json()

    def answer(self, question: str) -> dict[str, Any]:
        response = self.client.post(
            f"{self.knowledge_base_path}/answer",
            json={"question": question},
        )
        response.raise_for_status()
        return response.json()


def login(base_url: str, email: str, password: str, timeout_seconds: float) -> str:
    with httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout_seconds) as client:
        response = client.post("/api/auth/login", json={"email": email, "password": password})
        response.raise_for_status()
        token = response.json().get("access_token")
    if not isinstance(token, str) or not token:
        raise ValueError("Login response did not contain an access token")
    return token


def load_state(path: Path, benchmark: ValidatedBenchmark) -> dict[str, Any]:
    expected_metadata = run_metadata(benchmark)
    if path.exists():
        state = load_json(path)
        if not isinstance(state, dict) or not isinstance(state.get("documents"), dict):
            raise ValueError("Benchmark state file is invalid")
        metadata = state.get("metadata")
        if not isinstance(metadata, dict):
            raise ValueError("Benchmark state metadata is invalid")
        fingerprint_keys = (
            "source",
            "manifest_sha256",
            "questions_sha256",
            "selection_report_sha256",
            "document_count",
        )
        if any(metadata.get(key) != expected_metadata[key] for key in fingerprint_keys):
            raise ValueError("Benchmark state does not match the selected corpus")
        return state
    return {"metadata": expected_metadata, "documents": {}}


def _target(client: WorkbenchClient) -> dict[str, str]:
    return {
        "workspace_id": client.workspace_id,
        "knowledge_base_id": client.knowledge_base_id,
    }


def preflight_benchmark_knowledge_base(
    client: WorkbenchClient,
    benchmark: ValidatedBenchmark,
    state_path: Path,
    *,
    allow_fresh: bool,
    require_complete: bool,
) -> dict[str, Any] | None:
    """Enforce that the target KB contains only this saved benchmark corpus."""
    product_documents = client.list_documents()
    if not state_path.exists():
        if not allow_fresh:
            raise ValueError("Benchmark ingest state is required before this stage")
        if product_documents:
            raise ValueError(
                "A fresh benchmark run requires a dedicated empty Knowledge Base"
            )
        return None

    state = load_state(state_path, benchmark)
    if state.get("target") != _target(client):
        raise ValueError("Benchmark state belongs to a different product target")

    saved_documents = state["documents"]
    manifest_file_names = {
        item["doc_id"]: item["file_name"] for item in benchmark.manifest
    }
    manifest_ids = set(manifest_file_names)
    if not set(saved_documents).issubset(manifest_ids):
        raise ValueError("Benchmark state contains documents outside the selected corpus")
    if require_complete and (
        set(saved_documents) != manifest_ids
        or any(item.get("status") != "indexed" for item in saved_documents.values())
    ):
        raise ValueError("Benchmark corpus ingestion is not complete")

    expected_by_product_id: dict[str, dict[str, Any]] = {}
    for doc_id, record in saved_documents.items():
        product_id = record.get("product_document_id")
        file_name = record.get("file_name")
        if not isinstance(product_id, str) or not isinstance(file_name, str):
            raise TypeError("Benchmark ingest state contains an invalid document record")
        if file_name != manifest_file_names[doc_id]:
            raise ValueError("Benchmark ingest state file names do not match the corpus")
        if product_id in expected_by_product_id:
            raise ValueError("Benchmark ingest state reuses a product document")
        expected_by_product_id[product_id] = record

    actual_by_id: dict[str, dict[str, Any]] = {}
    for document in product_documents:
        product_id = document.get("id")
        if not isinstance(product_id, str) or product_id in actual_by_id:
            raise ValueError("Knowledge Base returned an invalid document list")
        actual_by_id[product_id] = document

    if set(actual_by_id) != set(expected_by_product_id):
        raise ValueError(
            "Dedicated benchmark Knowledge Base documents do not match ingest state"
        )
    for product_id, expected in expected_by_product_id.items():
        actual = actual_by_id[product_id]
        if (
            actual.get("file_name") != expected["file_name"]
            or actual.get("status") != "ready"
        ):
            raise ValueError(
                "Dedicated benchmark Knowledge Base documents do not match ingest state"
            )
    return state


def ingest_corpus(
    client: WorkbenchClient,
    benchmark: ValidatedBenchmark,
    state_path: Path,
) -> dict[str, Any]:
    state = preflight_benchmark_knowledge_base(
        client,
        benchmark,
        state_path,
        allow_fresh=True,
        require_complete=False,
    )
    if state is None:
        state = load_state(state_path, benchmark)
        state["target"] = _target(client)
    documents = state["documents"]
    for item in benchmark.manifest:
        doc_id = item["doc_id"]
        current = documents.get(doc_id, {})
        if current.get("status") == "indexed":
            continue
        product_document_id = current.get("product_document_id")
        if not isinstance(product_document_id, str):
            uploaded = client.upload(benchmark.paths.documents / item["file_name"])
            product_document_id = uploaded["id"]
            documents[doc_id] = {
                "file_name": item["file_name"],
                "product_document_id": product_document_id,
                "status": "uploaded",
            }
            save_json(state_path, state)
        indexed = client.index(product_document_id)
        documents[doc_id].update(
            {
                "status": "indexed",
                "chunk_count": indexed["chunk_count"],
                "embedding_model": indexed["embedding_model"],
            }
        )
        save_json(state_path, state)
    return state


def retrieved_doc_ids(
    results: Sequence[dict[str, Any]],
    file_name_to_doc_id: dict[str, str],
) -> list[str]:
    retrieved: list[str] = []
    for result in results:
        file_name = result.get("file_name")
        doc_id = file_name_to_doc_id.get(file_name)
        if doc_id is None:
            raise ValueError(f"Search returned unknown benchmark file: {file_name}")
        retrieved.append(doc_id)
    return retrieved


def _request_summary(
    records: Sequence[dict[str, Any]], total_questions: int
) -> dict[str, int]:
    successful = sum(
        record.get("request_status", "success") == "success" for record in records
    )
    failed = sum(record.get("request_status") == "failure" for record in records)
    return {
        "total": total_questions,
        "completed": successful + failed,
        "successful": successful,
        "failed": failed,
        "pending": total_questions - successful - failed,
    }


def _failure_details(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, httpx.HTTPStatusError):
        return {"type": "http_error", "http_status": exc.response.status_code}
    if isinstance(exc, httpx.TimeoutException):
        return {"type": "timeout", "http_status": None}
    if isinstance(exc, httpx.RequestError):
        return {"type": "request_error", "http_status": None}
    return {"type": "invalid_response", "http_status": None}


def _failure_record(question: dict[str, Any], exc: Exception) -> dict[str, Any]:
    return {
        "question_id": question["question_id"],
        "question_type": question["question_type"],
        "expected_doc_ids": question["expected_doc_ids"],
        "request_status": "failure",
        "failure": _failure_details(exc),
    }


def _load_checkpoint(
    path: Path,
    benchmark: ValidatedBenchmark,
    run_type: str,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    expected_metadata = run_metadata(benchmark)
    if not path.exists():
        return {**expected_metadata, "run_type": run_type}, {}
    payload = load_json(path)
    if not isinstance(payload, dict) or not isinstance(payload.get("questions"), list):
        raise TypeError("Benchmark checkpoint is invalid")
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict) or metadata.get("run_type") != run_type:
        raise ValueError("Benchmark checkpoint has an incompatible run type")
    fingerprint_keys = (
        "source",
        "manifest_sha256",
        "questions_sha256",
        "selection_report_sha256",
        "document_count",
        "question_count",
        "retrieval_limit",
    )
    if any(metadata.get(key) != expected_metadata[key] for key in fingerprint_keys):
        raise ValueError("Benchmark checkpoint does not match the selected corpus")

    questions_by_id = {question["question_id"]: question for question in benchmark.questions}
    records: dict[str, dict[str, Any]] = {}
    for record in payload["questions"]:
        if not isinstance(record, dict):
            raise TypeError("Benchmark checkpoint contains an invalid question record")
        question_id = record.get("question_id")
        question = questions_by_id.get(question_id)
        if (
            question is None
            or question_id in records
            or record.get("question_type") != question["question_type"]
            or record.get("expected_doc_ids") != question["expected_doc_ids"]
            or record.get("request_status") not in {"success", "failure"}
        ):
            raise ValueError("Benchmark checkpoint question records do not match the corpus")
        records[question_id] = record
    return metadata, records


def _ordered_records(
    benchmark: ValidatedBenchmark,
    records: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        records[question["question_id"]]
        for question in benchmark.questions
        if question["question_id"] in records
    ]


def retrieval_metrics(
    records: Sequence[dict[str, Any]],
    questions: Sequence[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    denominator_questions = list(questions) if questions is not None else list(records)
    answerable_questions = [
        question for question in denominator_questions if question["expected_doc_ids"]
    ]
    answerable = [
        record
        for record in records
        if record["expected_doc_ids"] and record.get("request_status", "success") == "success"
    ]
    if not answerable_questions:
        raise ValueError("Retrieval metrics require at least one answerable question")
    hit_3_count = sum(record["hit_at_3"] for record in answerable)
    hit_5_count = sum(record["hit_at_5"] for record in answerable)
    recall_sum = sum(record["document_recall_at_5"] for record in answerable)
    denominator = len(answerable_questions)
    return {
        "requests": _request_summary(records, len(denominator_questions)),
        "answerable_question_count": denominator,
        "successful_answerable_question_count": len(answerable),
        "failed_or_pending_answerable_question_count": denominator - len(answerable),
        "excluded_info_not_found_count": len(denominator_questions) - denominator,
        "retrieval_hit_at_3": {
            "count": hit_3_count,
            "denominator": denominator,
            "rate": hit_3_count / denominator,
        },
        "retrieval_hit_at_5": {
            "count": hit_5_count,
            "denominator": denominator,
            "rate": hit_5_count / denominator,
        },
        "document_recall_at_5": {
            "sum": recall_sum,
            "denominator": denominator,
            "macro_average": recall_sum / denominator,
        },
    }


def run_retrieval_baseline(
    client: WorkbenchClient,
    benchmark: ValidatedBenchmark,
    state_path: Path,
    output_path: Path,
    *,
    retry_failed: bool = False,
) -> dict[str, Any]:
    preflight_benchmark_knowledge_base(
        client,
        benchmark,
        state_path,
        allow_fresh=False,
        require_complete=True,
    )
    metadata, records = _load_checkpoint(output_path, benchmark, "retrieval")

    def persist() -> dict[str, Any]:
        ordered = _ordered_records(benchmark, records)
        payload = {
            "metadata": {**metadata, "updated_at": utc_now()},
            "metrics": retrieval_metrics(ordered, benchmark.questions),
            "questions": ordered,
        }
        save_json(output_path, payload)
        return payload

    for question in benchmark.questions:
        existing = records.get(question["question_id"])
        if existing is not None and (
            existing["request_status"] == "success" or not retry_failed
        ):
            continue
        try:
            response = client.search(question["question"])
            results = response["results"]
            if not isinstance(results, list):
                raise TypeError("Search response results are invalid")
            ranked_doc_ids = retrieved_doc_ids(results, benchmark.file_name_to_doc_id)
            expected = question["expected_doc_ids"]
            expected_set = set(expected)
            hit_3 = bool(expected_set.intersection(ranked_doc_ids[:3])) if expected else False
            hit_5 = bool(expected_set.intersection(ranked_doc_ids[:5])) if expected else False
            recall_5 = (
                len(expected_set.intersection(ranked_doc_ids[:5])) / len(expected_set)
                if expected
                else None
            )
            records[question["question_id"]] = {
                "question_id": question["question_id"],
                "question_type": question["question_type"],
                "expected_doc_ids": expected,
                "request_status": "success",
                "retrieved_doc_ids_at_5": ranked_doc_ids[:5],
                "hit_at_3": hit_3,
                "hit_at_5": hit_5,
                "document_recall_at_5": recall_5,
                "results": [
                    {
                        "doc_id": benchmark.file_name_to_doc_id[item["file_name"]],
                        "file_name": item["file_name"],
                        "product_document_id": item["document_id"],
                        "product_chunk_id": item["chunk_id"],
                        "chunk_index": item["chunk_index"],
                        "cosine_distance": item["cosine_distance"],
                    }
                    for item in results
                ],
            }
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            records[question["question_id"]] = _failure_record(question, exc)
        persist()
    return persist()


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _fixed_generation_settings(generation: dict[str, Any]) -> dict[str, Any]:
    return {
        key: generation[key]
        for key in (
            "model",
            "reasoning_effort",
            "retrieval_limit",
            "prompt_version",
            "max_input_tokens",
            "max_output_tokens",
        )
    }


def answer_metrics(
    records: Sequence[dict[str, Any]],
    questions: Sequence[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    denominator_questions = list(questions) if questions is not None else list(records)
    answerable_questions = [
        question for question in denominator_questions if question["expected_doc_ids"]
    ]
    not_found_questions = [
        question for question in denominator_questions if not question["expected_doc_ids"]
    ]
    successful = [
        record for record in records if record.get("request_status", "success") == "success"
    ]
    answerable = [record for record in successful if record["expected_doc_ids"]]
    not_found = [record for record in successful if not record["expected_doc_ids"]]
    citations = [
        citation
        for record in answerable
        for citation in record["citations"]
    ]
    expected_citations = sum(citation["expected_document"] for citation in citations)
    expected_coverage = sum(
        any(citation["expected_document"] for citation in record["citations"])
        for record in answerable
    )
    correct_no_answer = sum(record["status"] == "unsupported" for record in not_found)
    answerable_unsupported = sum(record["status"] == "unsupported" for record in answerable)
    return {
        "requests": _request_summary(records, len(denominator_questions)),
        "answerable_question_count": len(answerable_questions),
        "successful_answerable_question_count": len(answerable),
        "failed_or_pending_answerable_question_count": len(answerable_questions)
        - len(answerable),
        "info_not_found_question_count": len(not_found_questions),
        "successful_info_not_found_question_count": len(not_found),
        "citation_expected_document_precision": {
            "count": expected_citations,
            "denominator": len(citations),
            "rate": _ratio(expected_citations, len(citations)),
        },
        "expected_document_citation_coverage": {
            "count": expected_coverage,
            "denominator": len(answerable_questions),
            "rate": _ratio(expected_coverage, len(answerable_questions)),
        },
        "info_not_found_unsupported_accuracy": {
            "count": correct_no_answer,
            "denominator": len(not_found_questions),
            "rate": _ratio(correct_no_answer, len(not_found_questions)),
        },
        "answerable_unsupported_rate": {
            "count": answerable_unsupported,
            "denominator": len(answerable_questions),
            "rate": _ratio(answerable_unsupported, len(answerable_questions)),
        },
    }


def run_answer_inspection(
    client: WorkbenchClient,
    benchmark: ValidatedBenchmark,
    state_path: Path,
    output_path: Path,
    review_path: Path,
    *,
    retry_failed: bool = False,
) -> dict[str, Any]:
    preflight_benchmark_knowledge_base(
        client,
        benchmark,
        state_path,
        allow_fresh=False,
        require_complete=True,
    )
    metadata, records = _load_checkpoint(output_path, benchmark, "answers")

    def persist() -> dict[str, Any]:
        ordered = _ordered_records(benchmark, records)
        generation_settings: dict[str, Any] | None = None
        usage_totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        usage_available_count = 0
        for record in ordered:
            if record["request_status"] != "success":
                continue
            generation = record["generation"]
            fixed_settings = _fixed_generation_settings(generation)
            if generation_settings is None:
                generation_settings = fixed_settings
            elif generation_settings != fixed_settings:
                raise ValueError("Generation settings changed during benchmark run")
            if generation["total_tokens"] is not None:
                usage_available_count += 1
                for key in usage_totals:
                    usage_totals[key] += generation[key]

        payload = {
            "metadata": {
                **metadata,
                "updated_at": utc_now(),
                "generation": generation_settings,
                "token_usage": {
                    "responses_with_usage": usage_available_count,
                    **usage_totals,
                },
            },
            "metrics": answer_metrics(ordered, benchmark.questions),
            "questions": ordered,
        }
        save_json(output_path, payload)

        records_by_id = {record["question_id"]: record for record in ordered}
        review_records = []
        for question in benchmark.questions:
            record = records_by_id.get(question["question_id"])
            if record is None:
                continue
            review_record = {
                "question_id": question["question_id"],
                "question_type": question["question_type"],
                "question": question["question"],
                "expected_doc_ids": question["expected_doc_ids"],
                "gold_answer": question.get("gold_answer"),
                "request_status": record["request_status"],
                "system_status": record.get("status"),
                "system_answer": record.get("answer"),
                "citations": record.get("citations", []),
                "answer_facts": [
                    {"fact": fact, "covered": None, "notes": None}
                    for fact in question.get("answer_facts", [])
                ],
                "overall_correct": None,
                "review_notes": None,
            }
            if record["request_status"] == "failure":
                review_record["failure"] = record["failure"]
            review_records.append(review_record)
        save_json(
            review_path,
            {
                "metadata": payload["metadata"],
                "instructions": (
                    "Review each successful answer fact against the system answer and citations; "
                    "set covered to true or false, then set overall_correct and notes."
                ),
                "questions": review_records,
            },
        )
        return payload

    for question in benchmark.questions:
        existing = records.get(question["question_id"])
        if existing is not None and (
            existing["request_status"] == "success" or not retry_failed
        ):
            continue
        try:
            response = client.answer(question["question"])
            generation = response["generation"]
            if not isinstance(generation, dict):
                raise TypeError("Answer generation metadata is invalid")
            fixed_settings = _fixed_generation_settings(generation)
            prior_settings = {
                tuple(_fixed_generation_settings(record["generation"]).items())
                for record in records.values()
                if record["request_status"] == "success"
            }
            if prior_settings and tuple(fixed_settings.items()) not in prior_settings:
                raise ValueError("Generation settings changed during benchmark run")
            usage = {
                usage_key: generation[usage_key]
                for usage_key in ("input_tokens", "output_tokens", "total_tokens")
            }
            if any(
                value is not None
                and (isinstance(value, bool) or not isinstance(value, int))
                for value in usage.values()
            ) or (
                usage["total_tokens"] is not None
                and (usage["input_tokens"] is None or usage["output_tokens"] is None)
            ):
                raise TypeError("Answer token usage metadata is invalid")
            expected = set(question["expected_doc_ids"])
            citations = []
            for citation in response["citations"]:
                doc_id = benchmark.file_name_to_doc_id.get(citation["file_name"])
                if doc_id is None:
                    raise ValueError(
                        f"Answer returned unknown benchmark file: {citation['file_name']}"
                    )
                citations.append(
                    {
                        **citation,
                        "doc_id": doc_id,
                        "expected_document": doc_id in expected,
                    }
                )
            records[question["question_id"]] = {
                "question_id": question["question_id"],
                "question_type": question["question_type"],
                "expected_doc_ids": question["expected_doc_ids"],
                "request_status": "success",
                "status": response["status"],
                "answer": response["answer"],
                "message": response["message"],
                "citations": citations,
                "generation": generation,
            }
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            records[question["question_id"]] = _failure_record(question, exc)
        persist()
    return persist()


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Feature 009 EnterpriseRAG baseline")
    parser.add_argument("stage", choices=("validate", "ingest", "retrieval", "answers", "all"))
    parser.add_argument("--benchmark-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).parent / "output")
    parser.add_argument("--base-url", default=os.getenv("WORKBENCH_BASE_URL", "http://localhost:8000"))
    parser.add_argument("--workspace-id", default=os.getenv("WORKBENCH_WORKSPACE_ID"))
    parser.add_argument("--knowledge-base-id", default=os.getenv("WORKBENCH_KNOWLEDGE_BASE_ID"))
    parser.add_argument("--token", default=os.getenv("WORKBENCH_ACCESS_TOKEN"))
    parser.add_argument("--email", default=os.getenv("WORKBENCH_EMAIL"))
    parser.add_argument("--password", default=os.getenv("WORKBENCH_PASSWORD"))
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Retry only failed checkpoint records; successful records are always preserved",
    )
    return parser.parse_args(argv)


def require(value: str | None, name: str) -> str:
    if not value:
        raise ValueError(f"{name} is required for this stage")
    return value


def stages(selected: str) -> Iterable[str]:
    if selected == "all":
        return ("ingest", "retrieval", "answers")
    return (selected,)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    benchmark = validate_benchmark(args.benchmark_root)
    if args.stage == "validate":
        print(json.dumps(run_metadata(benchmark), indent=2, sort_keys=True))
        return 0

    workspace_id = require(args.workspace_id, "--workspace-id")
    knowledge_base_id = require(args.knowledge_base_id, "--knowledge-base-id")
    token = args.token
    if not token:
        token = login(
            args.base_url,
            require(args.email, "--email"),
            require(args.password, "--password"),
            args.timeout_seconds,
        )
    client = WorkbenchClient(
        args.base_url,
        workspace_id,
        knowledge_base_id,
        token,
        timeout_seconds=args.timeout_seconds,
    )
    try:
        state_path = args.output_dir / "ingest_state.json"
        for stage in stages(args.stage):
            if stage == "ingest":
                ingest_corpus(client, benchmark, state_path)
            elif stage == "retrieval":
                run_retrieval_baseline(
                    client,
                    benchmark,
                    state_path,
                    args.output_dir / "retrieval_baseline.json",
                    retry_failed=args.retry_failed,
                )
            elif stage == "answers":
                run_answer_inspection(
                    client,
                    benchmark,
                    state_path,
                    args.output_dir / "answer_baseline.json",
                    args.output_dir / "answer_fact_review.json",
                    retry_failed=args.retry_failed,
                )
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
