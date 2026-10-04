import json
import shutil
from pathlib import Path

import httpx
import pytest
from benchmarks.business_baseline.dataset import DATA, batches, load
from benchmarks.business_baseline.reporting import markdown, summary
from benchmarks.business_baseline.runner import (
    Operations,
    check_generation,
    freeze_configuration,
    main,
    offline_policy,
    open_state,
    rag,
)


@pytest.fixture
def frozen():
    manifest, cases, fingerprint = load()
    state = open_state(
        Path("unused-nonexistent-checkpoint.json"),
        fingerprint,
        {"mode": "offline_policy_only", "workspace_id": None},
    )
    return manifest, cases, state


def test_frozen_corpus_has_all_gold_and_disjoint_scenario_splits(frozen):
    manifest, cases, _ = frozen
    assert len(manifest["documents"]) == 12
    assert len(cases) == 108
    assert len(batches(cases)) == 26
    assert max(len(rows) for _, rows in batches(cases)) == 5
    assert {c["id"] for _, rows in batches(cases) for c in rows} == {c["id"] for c in cases}


def test_git_line_endings_do_not_change_corpus_identity(tmp_path):
    root = tmp_path / "data"
    shutil.copytree(DATA, root)
    for path in (root / "manifest.json", root / "cases.json", *(root / "docs").glob("*.txt")):
        normalized = path.read_text(encoding="utf-8").replace("\r\n", "\n")
        path.write_bytes(normalized.replace("\n", "\r\n").encode("utf-8"))
    assert load(root)[2] == load(DATA)[2]


@pytest.mark.parametrize(
    "defect", ["quote", "split", "duplicate", "expectation", "reference", "filename"]
)
def test_bad_gold_or_split_is_rejected_before_live_work(tmp_path, defect):
    root = tmp_path / "data"
    shutil.copytree(DATA, root)
    cases = json.loads((root / "cases.json").read_text(encoding="utf-8"))
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if defect == "quote":
        cases[0]["facts"][0] = cases[0]["evidence"][0]["quote"] = "not present in source"
    elif defect == "split":
        cases[0]["split"] = "holdout"
    elif defect == "duplicate":
        cases[1]["test_input"] = cases[0]["test_input"]
    elif defect == "expectation":
        cases[0]["expected_behavior"]["answer_status"] = "unsupported"
    elif defect == "reference":
        cases[0]["expected_doc_ids"] = ["missing"]
    else:
        manifest["documents"][0]["file_name"] = "../secret.txt"
    (root / "cases.json").write_text(json.dumps(cases), encoding="utf-8")
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError):
        load(root)


def test_missing_and_errors_cannot_inflate_performance(frozen):
    _, cases, state = frozen
    group = [c for c in cases if c["split"] == "development" and c["case_type"] == "knowledge_qa"]
    state["observations"] = {
        group[0]["id"]: {"result": "passed"},
        group[1]["id"]: {"result": "error"},
        group[2]["id"]: {"result": None},
    }
    state["retrieval"][group[0]["id"]] = {
        "question_id": group[0]["id"],
        "expected_doc_ids": group[0]["expected_doc_ids"],
        "request_status": "success",
        "hit_at_3": True,
        "hit_at_5": True,
        "document_recall_at_5": 1.0,
    }
    result = summary(cases, state)
    row = result["groups"]["development"]["knowledge_qa"]
    assert row["counts"] == {"passed": 1, "error": 1, "pending": 30}
    assert row["non_error_pass_rate"]["value"] == 1
    assert row["passed_over_planned"]["value"] == 1 / 32
    assert result["retrieval"]["development"]["document_recall_at_5"]["macro_average"] == 1 / 32


def test_unreviewed_or_missing_answers_never_count_correct(frozen):
    _, cases, state = frozen
    c = cases[0]
    state["reviews"][c["id"]] = {
        "correct": True,
        "reviewer": "synthetic-reviewer",
        "fact_supported": [True] * len(c["facts"]),
    }
    result = summary(cases, state)
    assert result["answer_review"]["development"]["reviewed"] == 0
    assert result["answer_review"]["development"]["correct_over_reviewed"]["value"] is None
    state["answers"][c["id"]] = {
        "question_id": c["id"],
        "expected_doc_ids": c["expected_doc_ids"],
        "request_status": "success",
        "status": "answered",
        "citations": [],
    }
    result = summary(cases, state)
    assert result["answer_review"]["development"]["reviewed"] == 1
    assert result["answer_review"]["development"]["unreviewed"] == 31


def test_offline_policy_is_labelled_and_not_rag_quality(frozen):
    _, cases, state = frozen
    offline_policy(cases, state)
    assert len(state["observations"]) == 24
    assert all(v["result"] == "passed" for v in state["observations"].values())
    assert all(
        v["execution_mode"] == "offline_policy_simulation" for v in state["observations"].values()
    )
    result = summary(cases, state)
    assert result["groups"]["development"]["knowledge_qa"]["coverage"]["value"] == 0
    assert "Recall@5：未评测" in markdown(result)


@pytest.mark.parametrize("change", ["fingerprint", "target"])
def test_checkpoint_cannot_change_dataset_or_workspace(tmp_path, frozen, change):
    _, _, state = frozen
    path = tmp_path / "state.json"
    path.write_text(json.dumps(state))
    fingerprint = "different" if change == "fingerprint" else state["fingerprint"]
    target = {"workspace_id": "different"} if change == "target" else state["target"]
    with pytest.raises(ValueError, match="changed"):
        open_state(path, fingerprint, target)


def test_lost_write_response_blocks_replay_and_preserves_marker(tmp_path, frozen):
    _, _, state = frozen
    calls = []

    def fail(request):
        calls.append(request.method)
        raise httpx.ReadTimeout("private payload must not be reported", request=request)

    path = tmp_path / "state.json"
    with httpx.Client(transport=httpx.MockTransport(fail), base_url="http://localhost") as client:
        op = Operations(client, state, path)
        with pytest.raises(httpx.ReadTimeout):
            op.write("create case", "POST", "/example", lambda v: None, json={"name": "x"})
        with pytest.raises(ValueError, match="reconciled"):
            op.write("create case", "POST", "/example", lambda v: None, json={"name": "x"})
    assert calls == ["POST"]
    with pytest.raises(ValueError, match="Ambiguous"):
        open_state(path, state["fingerprint"], state["target"])


def test_failed_rag_checkpoint_stops_paid_resume(tmp_path, frozen):
    _, cases, state = frozen
    state["answers"]["failed"] = {"request_status": "failure"}
    with httpx.Client(
        transport=httpx.MockTransport(lambda r: pytest.fail("unexpected request"))
    ) as client:
        op = Operations(client, state, tmp_path / "state.json")
        with pytest.raises(ValueError, match="prior RAG failure"):
            rag(op, cases, "answers")


def test_no_egress_flag_prevents_login_and_calls(tmp_path):
    with pytest.raises(ValueError, match="acknowledge"):
        main(["all", "--output-dir", str(tmp_path)])


def test_process_termination_after_paid_rag_post_cannot_replay(tmp_path, frozen):
    _, cases, state = frozen
    state["resources"]["kb"] = "kb"
    calls = []

    def interrupted(request):
        calls.append(request.method)
        raise KeyboardInterrupt()

    path = tmp_path / "state.json"
    with httpx.Client(
        transport=httpx.MockTransport(interrupted), base_url="http://localhost"
    ) as client:
        op = Operations(client, state, path)
        with pytest.raises(KeyboardInterrupt):
            rag(op, cases, "retrieval")
    assert calls == ["POST"]
    saved = json.loads(path.read_text())
    assert saved["pending_write"]["kind"] == "paid_read"
    with pytest.raises(ValueError, match="Ambiguous"):
        open_state(path, state["fingerprint"], state["target"])


@pytest.mark.parametrize("field", ["model", "prompt_version", "max_output_tokens"])
def test_generation_metadata_change_is_rejected(field):
    providers = {
        "generation_model": "original",
        "generation_reasoning_effort": "low",
        "generation_retrieval_limit": 5,
        "generation_prompt_version": "v1",
        "generation_max_input_tokens": 12000,
        "generation_max_output_tokens": 1200,
    }
    state = {"configuration": {"providers": providers}}
    value = {
        "model": "original",
        "reasoning_effort": "low",
        "retrieval_limit": 5,
        "prompt_version": "v1",
        "max_input_tokens": 12000,
        "max_output_tokens": 1200,
    }
    check_generation(state, value)
    value[field] = "changed"
    with pytest.raises(ValueError, match="metadata differs"):
        check_generation(state, value)
    assert state["configuration_drift"] is True


def test_cross_run_configuration_change_does_not_replace_baseline(frozen):
    _, _, state = frozen
    original = {"providers": {"routing_model": "v1"}, "instruction_hashes": {"routing": "abc"}}
    freeze_configuration(state, original)
    with pytest.raises(ValueError, match="configuration drift"):
        freeze_configuration(state, {"providers": {"routing_model": "v2"}})
    assert state["configuration"] == original
    assert state["configuration_drift"] is True


def test_loopback_login_ignores_external_proxy_environment(tmp_path, monkeypatch):
    from benchmarks.business_baseline import runner

    original_client = httpx.Client
    monkeypatch.setenv("HTTP_PROXY", "http://untrusted.proxy.invalid:8080")
    monkeypatch.setenv("ALL_PROXY", "http://untrusted.proxy.invalid:8080")
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("WORKBENCH_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("WORKBENCH_WORKSPACE_ID", raising=False)
    monkeypatch.setenv("WORKBENCH_EMAIL", "benchmark@example.test")
    monkeypatch.setenv("WORKBENCH_PASSWORD", "synthetic-not-a-real-password")
    paths = []

    def transport(request):
        paths.append(request.url.path)
        if request.url.path == "/api/auth/login":
            return httpx.Response(200, json={"access_token": "synthetic-test-token"})
        return httpx.Response(200, json=[{"id": "synthetic-workspace"}])

    def factory(**kwargs):
        assert kwargs["trust_env"] is False
        return original_client(**kwargs, transport=httpx.MockTransport(transport))

    monkeypatch.setattr(runner.httpx, "Client", factory)
    monkeypatch.setattr(runner, "prepare", lambda *args: None)
    assert main(["prepare", "--output-dir", str(tmp_path), "--acknowledge-egress"]) == 0
    assert paths == ["/api/auth/login", "/api/workspaces"]
