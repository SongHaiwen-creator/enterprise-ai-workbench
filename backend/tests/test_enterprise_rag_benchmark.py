import json
from pathlib import Path
from typing import Any

import pytest
from benchmarks.enterprise_rag.runner import (
    answer_metrics,
    ingest_corpus,
    retrieval_metrics,
    retrieved_doc_ids,
    run_answer_inspection,
    run_retrieval_baseline,
    validate_benchmark,
)


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def benchmark_fixture(root: Path) -> None:
    documents = root / "docs"
    documents.mkdir()
    (documents / "doc-1.txt").write_text("Travel limit is $100.", encoding="utf-8")
    (documents / "doc-2.txt").write_text("Security policy.", encoding="utf-8")
    manifest = [
        {"doc_id": "doc-1", "file_name": "doc-1.txt", "role": "gold", "gold_for": ["q1"]},
        {"doc_id": "doc-2", "file_name": "doc-2.txt", "role": "distractor", "gold_for": []},
    ]
    questions = [
        {
            "question_id": "q1",
            "question_type": "basic",
            "question": "What is the travel limit?",
            "expected_doc_ids": ["doc-1"],
            "gold_answer": "$100",
            "answer_facts": ["The limit is $100."],
        },
        {
            "question_id": "q2",
            "question_type": "info_not_found",
            "question": "What is not documented?",
            "expected_doc_ids": [],
            "gold_answer": "Not found",
            "answer_facts": ["The answer is not available."],
        },
    ]
    write_json(root / "corpus_manifest.json", manifest)
    (root / "questions.jsonl").write_text(
        "\n".join(json.dumps(question) for question in questions) + "\n",
        encoding="utf-8",
    )
    write_json(
        root / "selection_report.json",
        {
            "source_corpus": "confluence",
            "random_seed": 20260920,
            "selected_question_count": 2,
            "final_corpus_document_count": 2,
        },
    )
    (root / "SOURCE.md").write_text("EnterpriseRAG-Bench, MIT\n", encoding="utf-8")


class FakeClient:
    def __init__(self) -> None:
        self.workspace_id = "workspace-1"
        self.knowledge_base_id = "knowledge-base-1"
        self.upload_calls: list[str] = []
        self.index_calls: list[str] = []

    def upload(self, path: Path) -> dict[str, Any]:
        self.upload_calls.append(path.name)
        return {"id": f"product-{path.stem}"}

    def index(self, document_id: str) -> dict[str, Any]:
        self.index_calls.append(document_id)
        return {
            "chunk_count": 1,
            "embedding_model": "text-embedding-3-small",
        }

    def search(self, question: str) -> dict[str, Any]:
        if "travel" in question.lower():
            results = [
                {
                    "file_name": "doc-1.txt",
                    "document_id": "product-doc-1",
                    "chunk_id": "chunk-1",
                    "chunk_index": 0,
                    "cosine_distance": 0.1,
                },
                {
                    "file_name": "doc-2.txt",
                    "document_id": "product-doc-2",
                    "chunk_id": "chunk-2",
                    "chunk_index": 0,
                    "cosine_distance": 0.2,
                },
            ]
        else:
            results = []
        return {"query": question, "results": results}

    def answer(self, question: str) -> dict[str, Any]:
        generation = {
            "model": "gpt-5.6-terra",
            "reasoning_effort": "low",
            "retrieval_limit": 5,
            "prompt_version": "grounded-answer-v1",
            "max_input_tokens": 12000,
            "max_output_tokens": 1200,
            "input_tokens": 100,
            "output_tokens": 20,
            "total_tokens": 120,
        }
        if "travel" in question.lower():
            return {
                "status": "answered",
                "answer": "The limit is $100.",
                "message": None,
                "citations": [
                    {
                        "document_id": "product-doc-1",
                        "file_name": "doc-1.txt",
                        "document_version": 1,
                        "chunk_id": "chunk-1",
                        "chunk_index": 0,
                        "excerpt": "Travel limit is $100.",
                    }
                ],
                "generation": generation,
            }
        return {
            "status": "unsupported",
            "answer": None,
            "message": "Not enough evidence.",
            "citations": [],
            "generation": generation,
        }


def test_validate_prepared_benchmark_and_reject_missing_gold(tmp_path: Path) -> None:
    benchmark_fixture(tmp_path)

    benchmark = validate_benchmark(tmp_path)

    assert len(benchmark.manifest) == 2
    assert len(benchmark.questions) == 2
    assert benchmark.file_name_to_doc_id == {
        "doc-1.txt": "doc-1",
        "doc-2.txt": "doc-2",
    }
    question_lines = (tmp_path / "questions.jsonl").read_text(encoding="utf-8").splitlines()
    questions = json.loads(question_lines[0])
    questions["expected_doc_ids"] = ["missing"]
    (tmp_path / "questions.jsonl").write_text(json.dumps(questions) + "\n", encoding="utf-8")
    selection = json.loads((tmp_path / "selection_report.json").read_text(encoding="utf-8"))
    selection["selected_question_count"] = 1
    write_json(tmp_path / "selection_report.json", selection)

    with pytest.raises(ValueError, match="missing gold"):
        validate_benchmark(tmp_path)


def test_ingestion_is_resumable_and_does_not_copy_corpus(tmp_path: Path) -> None:
    benchmark_fixture(tmp_path)
    benchmark = validate_benchmark(tmp_path)
    client = FakeClient()
    state_path = tmp_path / "output" / "state.json"

    first = ingest_corpus(client, benchmark, state_path)
    second = ingest_corpus(client, benchmark, state_path)

    assert len(first["documents"]) == 2
    assert first == second
    assert client.upload_calls == ["doc-1.txt", "doc-2.txt"]
    assert client.index_calls == ["product-doc-1", "product-doc-2"]
    assert all(item["status"] == "indexed" for item in second["documents"].values())
    assert second["target"] == {
        "workspace_id": "workspace-1",
        "knowledge_base_id": "knowledge-base-1",
    }


def test_retrieval_baseline_preserves_ids_and_calculates_metrics(tmp_path: Path) -> None:
    benchmark_fixture(tmp_path)
    benchmark = validate_benchmark(tmp_path)
    output = tmp_path / "retrieval.json"

    payload = run_retrieval_baseline(FakeClient(), benchmark, output)

    assert output.exists()
    assert payload["metadata"]["chunk_size"] == 1000
    assert payload["metadata"]["chunk_overlap"] == 200
    assert payload["metadata"]["retrieval_limit"] == 5
    assert payload["metrics"]["retrieval_hit_at_3"] == {
        "count": 1,
        "denominator": 1,
        "rate": 1.0,
    }
    assert payload["metrics"]["retrieval_hit_at_5"]["rate"] == 1.0
    assert payload["metrics"]["document_recall_at_5"]["macro_average"] == 1.0
    assert payload["questions"][0]["question_id"] == "q1"
    assert payload["questions"][0]["expected_doc_ids"] == ["doc-1"]
    assert "content" not in payload["questions"][0]["results"][0]


def test_answer_inspection_records_settings_usage_and_review_template(tmp_path: Path) -> None:
    benchmark_fixture(tmp_path)
    benchmark = validate_benchmark(tmp_path)
    output = tmp_path / "answers.json"
    review = tmp_path / "review.json"

    payload = run_answer_inspection(FakeClient(), benchmark, output, review)

    assert payload["metadata"]["generation"] == {
        "model": "gpt-5.6-terra",
        "reasoning_effort": "low",
        "retrieval_limit": 5,
        "prompt_version": "grounded-answer-v1",
        "max_input_tokens": 12000,
        "max_output_tokens": 1200,
    }
    assert payload["metadata"]["token_usage"] == {
        "responses_with_usage": 2,
        "input_tokens": 200,
        "output_tokens": 40,
        "total_tokens": 240,
    }
    assert payload["metrics"]["citation_expected_document_precision"]["rate"] == 1.0
    assert payload["metrics"]["info_not_found_unsupported_accuracy"]["rate"] == 1.0
    review_payload = json.loads(review.read_text(encoding="utf-8"))
    assert review_payload["questions"][0]["answer_facts"] == [
        {"fact": "The limit is $100.", "covered": None, "notes": None}
    ]
    assert review_payload["questions"][0]["overall_correct"] is None


def test_metric_helpers_use_answerable_denominators() -> None:
    retrieval = retrieval_metrics(
        [
            {
                "expected_doc_ids": ["a", "b"],
                "hit_at_3": True,
                "hit_at_5": True,
                "document_recall_at_5": 0.5,
            },
            {
                "expected_doc_ids": [],
                "hit_at_3": False,
                "hit_at_5": False,
                "document_recall_at_5": None,
            },
        ]
    )
    answers = answer_metrics(
        [
            {
                "expected_doc_ids": ["a"],
                "status": "answered",
                "citations": [{"expected_document": True}],
            },
            {
                "expected_doc_ids": [],
                "status": "unsupported",
                "citations": [],
            },
        ]
    )

    assert retrieval["answerable_question_count"] == 1
    assert retrieval["document_recall_at_5"]["macro_average"] == 0.5
    assert answers["answerable_question_count"] == 1
    assert answers["info_not_found_question_count"] == 1


def test_retrieval_rank_positions_preserve_duplicate_document_chunks() -> None:
    results = [
        {"file_name": "a.txt"},
        {"file_name": "a.txt"},
        {"file_name": "b.txt"},
    ]

    assert retrieved_doc_ids(results, {"a.txt": "a", "b.txt": "b"}) == ["a", "a", "b"]
