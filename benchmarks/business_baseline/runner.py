"""Sequential benchmark operations through normal authenticated product APIs."""

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

import httpx
from app.services.authorization_policy import permission_observation
from dotenv import dotenv_values

from benchmarks.business_baseline.dataset import DATA, batches, load, payload
from benchmarks.business_baseline.reporting import markdown, summary
from benchmarks.enterprise_rag.runner import retrieved_doc_ids, save_json, utc_now

AGENT_PROMPT = (
    "你是星桥示例科技的员工服务助手，所有资料均为合成示例。"
    "范围包括企业制度问答、查询当前登录员工本人的报销状态和个人资料、"
    "准备IT权限申请。制度答案必须基于知识库证据，缺乏证据时不得编造。"
    "不提供范围外的创作、生活建议。不能查他人资料、修改报销或员工档案。"
    "生产数据库只读；访问申请必须人工审核，提交不等于授权，不得自行批准。"
)
SYSTEMIC_ERRORS = {
    "provider_configuration",
    "provider_failure",
    "provider_contract",
    "authorization_revoked",
    "persistence_failure",
    "internal_error",
}


def open_state(path, fingerprint, target):
    if path.exists():
        state = json.loads(path.read_text(encoding="utf-8"))
        if state.get("fingerprint") != fingerprint or state.get("target") != target:
            raise ValueError("Checkpoint target or dataset changed; use a new output directory")
        if state.get("pending_write"):
            raise ValueError("Ambiguous write requires manual reconciliation; no automatic replay")
        if state.get("configuration_drift"):
            raise ValueError("Configuration drift requires a separate baseline")
        return state
    return {
        "fingerprint": fingerprint,
        "target": target,
        "created_at": utc_now(),
        "resources": {"tools": {}, "documents": {}, "datasets": {}, "cases": {}, "assignments": []},
        "runs": {},
        "observations": {},
        "retrieval": {},
        "answers": {},
        "reviews": {},
        "pending_write": None,
    }


class Operations:
    def __init__(self, client, state, path):
        self.client, self.state, self.path = client, state, path
        self.base = f"/api/workspaces/{state['target']['workspace_id']}"

    def persist(self):
        self.state["updated_at"] = utc_now()
        save_json(self.path, self.state)

    def read(self, path, **kwargs):
        response = self.client.get(path, **kwargs)
        response.raise_for_status()
        return response.json()

    def write(self, label, method, path, accept, **kwargs):
        if self.state.get("pending_write"):
            raise ValueError("An earlier write must be reconciled")
        self.state["pending_write"] = {
            "operation": label,
            "method": method,
            "path": path,
            "started_at": utc_now(),
        }
        self.persist()
        response = self.client.request(method, path, **kwargs)
        response.raise_for_status()
        result = response.json()
        accept(result)
        self.state["pending_write"] = None
        self.persist()
        return result


def prepare(op, manifest, cases, root):
    resources = op.state["resources"]
    tag = op.state["fingerprint"][:10]
    if not resources.get("kb"):
        op.write(
            "create dedicated KB",
            "POST",
            f"{op.base}/knowledge-bases",
            lambda v: resources.update(kb=v["id"]),
            json={"name": f"合成员工制度 v1 · {tag}", "description": "仅业务基准；非真实公司制度"},
        )
    if not resources.get("agent"):
        op.write(
            "create dedicated Agent",
            "POST",
            f"{op.base}/agents",
            lambda v: resources.update(agent=v["id"]),
            json={"name": f"员工服务基准 Agent v1 · {tag}", "system_prompt": AGENT_PROMPT},
        )
    registered = {t["tool_key"]: t for t in op.read(f"{op.base}/tools")}
    resources.setdefault("owned_tools", [])
    resources.setdefault("tools_activated", [])
    for key in ("get_reimbursement_status", "get_employee_information", "create_it_access_request"):
        if key not in resources["tools"]:
            if key in registered:
                if registered[key]["status"] != "active":
                    raise ValueError(
                        "Existing required Tool is disabled; baseline will not change it"
                    )
                resources["tools"][key] = registered[key]["id"]
                op.persist()
            else:

                def accept_tool(value, key=key):
                    resources["tools"][key] = value["id"]
                    resources["owned_tools"].append(key)

                op.write(
                    f"register {key}",
                    "POST",
                    f"{op.base}/tools",
                    accept_tool,
                    json={"tool_key": key, "name": key, "description": "业务基准采用既有注册能力"},
                )
        if key in resources["owned_tools"] and key not in resources["tools_activated"]:
            op.write(
                f"activate newly created {key}",
                "PATCH",
                f"{op.base}/tools/{resources['tools'][key]}",
                lambda v, key=key: resources["tools_activated"].append(key),
                json={"status": "active"},
            )
        if key not in resources["assignments"]:
            op.write(
                f"assign {key} to benchmark Agent",
                "PUT",
                f"{op.base}/agents/{resources['agent']}/tools/{resources['tools'][key]}",
                lambda v, key=key: resources["assignments"].append(key),
            )
    if not resources.get("agent_activated"):
        op.write(
            "activate benchmark Agent",
            "PATCH",
            f"{op.base}/agents/{resources['agent']}",
            lambda v: resources.update(agent_activated=True),
            json={"status": "active"},
        )
    document_path = f"{op.base}/knowledge-bases/{resources['kb']}/documents"
    existing = op.read(document_path)
    saved = {r["id"] for r in resources["documents"].values()}
    if {d["id"] for d in existing} != saved:
        raise ValueError("Dedicated KB contains unsaved documents; reconcile before continuing")
    for doc in manifest["documents"]:
        doc_id = doc["id"]
        if doc_id not in resources["documents"]:
            with (root / "docs" / doc["file_name"]).open("rb") as source:
                op.write(
                    f"upload {doc_id}",
                    "POST",
                    document_path,
                    lambda v, doc_id=doc_id: resources["documents"].update(
                        {doc_id: {"id": v["id"], "file_name": v["file_name"], "indexed": False}}
                    ),
                    files={"file": (doc["file_name"], source, "text/plain")},
                )
        saved_doc = resources["documents"][doc_id]
        if not saved_doc["indexed"]:
            op.write(
                f"index {doc_id}",
                "POST",
                f"{document_path}/{saved_doc['id']}/index",
                lambda v, saved_doc=saved_doc: saved_doc.update(
                    indexed=True, chunk_count=v["chunk_count"], embedding_model=v["embedding_model"]
                ),
            )
    for batch_id, rows in batches(cases):
        if batch_id not in resources["datasets"]:
            op.write(
                f"create dataset {batch_id}",
                "POST",
                f"{op.base}/evaluation-datasets",
                lambda v, batch_id=batch_id: resources["datasets"].update({batch_id: v["id"]}),
                json={
                    "name": f"业务基准 v1 · {batch_id} · {tag}",
                    "description": "合成基准，最多5题；题目与答案已冻结，不按结果修改标准",
                },
            )
        dataset_id = resources["datasets"][batch_id]
        for case in rows:
            if case["id"] not in resources["cases"]:
                op.write(
                    f"create case {case['id']}",
                    "POST",
                    f"{op.base}/evaluation-datasets/{dataset_id}/cases",
                    lambda v, case=case: resources["cases"].update({case["id"]: v["id"]}),
                    json=payload(case, resources),
                )
    return resources


def verify_resources(op, manifest, cases):
    r = op.state["resources"]
    agent = op.read(f"{op.base}/agents/{r['agent']}")
    if agent["status"] != "active" or agent["system_prompt"] != AGENT_PROMPT:
        raise ValueError("Benchmark Agent configuration changed")
    assignments = op.read(f"{op.base}/agents/{r['agent']}/tools")
    if {(t["tool_key"], t["id"], t["status"]) for t in assignments} != {
        (key, value, "active") for key, value in r["tools"].items()
    }:
        raise ValueError("Benchmark Agent Tool assignment changed")
    docs = op.read(f"{op.base}/knowledge-bases/{r['kb']}/documents")
    expected = {(v["id"], v["file_name"], "ready", 1) for v in r["documents"].values()}
    if (
        len(expected) != len(manifest["documents"])
        or {(d["id"], d["file_name"], d["status"], d["version"]) for d in docs} != expected
    ):
        raise ValueError("Benchmark KB document set or versions changed")
    for batch_id, rows in batches(cases):
        ds = r["datasets"][batch_id]
        if op.read(f"{op.base}/evaluation-datasets/{ds}")["status"] != "active":
            raise ValueError("Benchmark dataset disabled")
        summaries = op.read(f"{op.base}/evaluation-datasets/{ds}/cases", params={"limit": 100})[
            "items"
        ]
        if {v["id"] for v in summaries} != {r["cases"][c["id"]] for c in rows}:
            raise ValueError("Dataset case set changed")
        for c in rows:
            actual = op.read(f"{op.base}/evaluation-datasets/{ds}/cases/{r['cases'][c['id']]}")
            expected_case = payload(c, r)
            if actual["status"] != "active" or any(
                actual.get(k) != v for k, v in expected_case.items()
            ):
                raise ValueError("Product case differs from frozen baseline")


def evaluate_agent(op, cases, diagnosis=None):
    r = op.state["resources"]
    for batch_id, rows in batches(cases):
        if batch_id not in op.state["runs"]:

            def accept_run(value, batch_id=batch_id):
                op.state["runs"][batch_id] = value["id"]

            op.write(
                f"evaluate {batch_id}",
                "POST",
                f"{op.base}/evaluation-datasets/{r['datasets'][batch_id]}/runs",
                accept_run,
                json={"agent_id": r["agent"], "provider_egress_acknowledged": True},
            )
        run_id = op.state["runs"][batch_id]
        run = op.read(f"{op.base}/evaluation-runs/{run_id}")
        op.state.setdefault("run_details", {})[batch_id] = run
        try:
            freeze_configuration(op.state, run["config_snapshot"])
        finally:
            op.persist()
        actual_rows = op.read(f"{op.base}/evaluation-runs/{run_id}/cases", params={"limit": 100})[
            "items"
        ]
        expected_ids = {r["cases"][c["id"]]: c["id"] for c in rows}
        if {v["case_id"] for v in actual_rows} != set(expected_ids):
            raise ValueError("Run did not preserve its expected case set")
        for v in actual_rows:
            detail = op.read(f"{op.base}/evaluation-runs/{run_id}/cases/{v['id']}")
            op.state["observations"][expected_ids[v["case_id"]]] = detail
        op.persist()
        print(f"Agent: {batch_id} {run['status']}", flush=True)
        stop_errors = SYSTEMIC_ERRORS - ({"provider_contract"} if diagnosis else set())
        if any(v.get("error_category") in stop_errors for v in actual_rows):
            raise ValueError("Systemic evaluation failure; stopped further paid batches")


def freeze_configuration(state, config):
    if "configuration" in state and state["configuration"] != config:
        state["configuration_drift"] = True
        raise ValueError("Provider, instruction or policy configuration drift; baseline stopped")
    state.setdefault("configuration", config)


def probe_configuration(op, cases):
    # A permission-only existing Run captures current provider/instruction settings
    # with no live model call, token minting, new endpoint or auth override.
    batch_id = next(
        k for k, rows in batches(cases) if rows[0]["case_type"] == "permission_boundary"
    )
    resources = op.state["resources"]
    op.state.setdefault("configuration_probes", [])
    result = op.write(
        "permission-only configuration probe",
        "POST",
        f"{op.base}/evaluation-datasets/{resources['datasets'][batch_id]}/runs",
        lambda v: op.state["configuration_probes"].append(v["id"]),
        json={"agent_id": resources["agent"], "provider_egress_acknowledged": False},
    )
    current = op.read(f"{op.base}/evaluation-runs/{result['id']}")
    if current["status"] != "completed" or current["error_cases"]:
        raise ValueError("Configuration probe failed; no paid measurement")
    try:
        freeze_configuration(op.state, current["config_snapshot"])
    finally:
        op.persist()


def check_generation(state, generation):
    providers = state["configuration"]["providers"]
    fields = {
        "model": "generation_model",
        "reasoning_effort": "generation_reasoning_effort",
        "retrieval_limit": "generation_retrieval_limit",
        "prompt_version": "generation_prompt_version",
        "max_input_tokens": "generation_max_input_tokens",
        "max_output_tokens": "generation_max_output_tokens",
    }
    if any(generation.get(k) != providers[v] for k, v in fields.items()):
        state["configuration_drift"] = True
        raise ValueError("Answer generation metadata differs from frozen configuration")


def rag(op, cases, stage, diagnosis=None):
    if op.state.get("pending_write") or op.state.get("configuration_drift"):
        raise ValueError("Interrupted request or configuration drift requires reconciliation")
    if any(
        v.get("request_status") == "failure"
        and not (
            diagnosis
            and stage == "answers"
            and v.get("failure_category") == "generation_http_502"
        )
        for v in op.state[stage].values()
    ):
        raise ValueError("A prior RAG failure requires diagnosis; no paid requests on resume")
    r = op.state["resources"]
    names = {v["file_name"]: key for key, v in r["documents"].items()}
    kb = f"{op.base}/knowledge-bases/{r['kb']}"
    for c in cases:
        if c["case_type"] != "knowledge_qa" and not (
            c["case_type"] == "refusal_behavior"
            and c["expected_behavior"]["routing_intent"] == "knowledge_qa"
        ):
            continue
        records = op.state[stage]
        if c["id"] in records:
            continue
        question = {"question_id": c["id"], "expected_doc_ids": c["expected_doc_ids"]}
        try:
            path = f"{kb}/{'search' if stage == 'retrieval' else 'answer'}"
            op.state["pending_write"] = {
                "operation": f"paid {stage} {c['id']}",
                "method": "POST",
                "path": path,
                "kind": "paid_read",
                "started_at": utc_now(),
            }
            op.persist()  # Includes process termination, not only HTTP exceptions.
            response = op.client.post(
                path,
                json={"query": c["test_input"], "limit": 5}
                if stage == "retrieval"
                else {"question": c["test_input"]},
            )
            response.raise_for_status()
            value = response.json()
            record = {**question, "request_status": "success"}
            expected = set(c["expected_doc_ids"])
            if stage == "retrieval":
                ranked = retrieved_doc_ids(value["results"], names)
                record.update(
                    hit_at_3=bool(expected.intersection(ranked[:3])),
                    hit_at_5=bool(expected.intersection(ranked[:5])),
                    document_recall_at_5=len(expected.intersection(ranked[:5])) / len(expected)
                    if expected
                    else None,
                    ranked_document_ids=ranked,
                    results=value["results"],
                )
            else:
                check_generation(op.state, value["generation"])
                citations = []
                for citation in value["citations"]:
                    doc_id = names[citation["file_name"]]
                    citations.append(
                        {**citation, "doc_id": doc_id, "expected_document": doc_id in expected}
                    )
                record.update(
                    status=value["status"],
                    answer=value["answer"],
                    citations=citations,
                    generation=value["generation"],
                )
                op.state["reviews"][c["id"]] = {
                    "gold_answer": c["gold_answer"],
                    "facts": c["facts"],
                    "evidence": c["evidence"],
                    "correct": None,
                    "fact_supported": [None] * len(c["facts"]),
                    "reviewer": None,
                    "notes": None,
                }
            records[c["id"]] = record
            op.state["pending_write"] = None
            op.persist()
            print(f"{stage}: {c['id']} success", flush=True)
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            generation_failure = False
            if isinstance(error, httpx.HTTPStatusError) and error.response.status_code == 502:
                try:
                    generation_failure = (
                        error.response.json().get("detail") == "Generation provider request failed"
                    )
                except (ValueError, AttributeError):
                    pass
            records[c["id"]] = {
                **question,
                "request_status": "failure",
                "failure_type": type(error).__name__,
                "http_status": error.response.status_code
                if isinstance(error, httpx.HTTPStatusError)
                else None,
                "failure_category": "generation_http_502" if generation_failure else None,
            }
            if diagnosis and stage == "answers" and generation_failure:
                # Received HTTP error on a read-only endpoint, not a lost product write.
                # Preserve the failed first attempt and measure only remaining questions.
                # HTTP 502 hides the exact cause; do not label every error a schema defect.
                op.state["pending_write"] = None
                op.persist()
                print(f"{stage}: {c['id']} failure (recorded, not retried)", flush=True)
                continue
            op.persist()
            raise ValueError(
                "RAG request failed; saved failure and stopped paid requests"
            ) from None


def offline_policy(cases, state):
    for c in cases:
        if c["case_type"] != "permission_boundary":
            continue
        expected = c["expected_behavior"]
        actual = permission_observation(
            role=expected["actor_role"],
            membership_status=expected["actor_membership_status"],
            operation=expected["operation"],
            present=expected["target_context"] == "same_workspace",
            active=True,
        )
        checks = {
            "http_status": actual["http_status"] == expected["expected_http_status"],
            "result_category": actual["result_category"] == expected["result_category"],
            "access_denied": actual["access_denied"] == expected["access_denied"],
        }
        state["observations"][c["id"]] = {
            "result": "passed" if all(checks.values()) else "failed",
            "actual": actual,
            "comparison_checks": checks,
            "execution_mode": "offline_policy_simulation",
        }


def report(cases, state, output):
    result = summary(cases, state)
    save_json(output / "summary.json", result)
    (output / "report.md").write_text(markdown(result), encoding="utf-8")
    print(f"Report: {output / 'report.md'}", flush=True)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "stage",
        choices=("validate", "policy", "prepare", "agent", "retrieval", "answers", "all", "report"),
    )
    p.add_argument("--data-dir", type=Path, default=DATA)
    p.add_argument("--output-dir", type=Path, default=Path(__file__).parent / "output")
    p.add_argument("--env-file", type=Path)
    p.add_argument("--base-url", default="http://127.0.0.1:8000")
    p.add_argument("--workspace-id")
    p.add_argument("--acknowledge-egress", action="store_true")
    p.add_argument(
        "--continue-diagnosed-errors",
        metavar="REASON",
        help=(
            "Record a diagnosis and measure remaining first attempts after Agent "
            "provider_contract or answer generation HTTP 502 errors; no retries. "
            "Other failures and ambiguous requests still stop."
        ),
    )
    args = p.parse_args(argv)
    if args.continue_diagnosed_errors is not None and (
        args.stage not in {"agent", "answers", "all"}
        or not args.continue_diagnosed_errors.strip()
        or len(args.continue_diagnosed_errors) > 1000
    ):
        raise ValueError("A bounded diagnosis is required for Agent/answer measurement")
    manifest, cases, fingerprint = load(args.data_dir)
    if args.stage == "validate":
        print(
            json.dumps(
                {
                    "fingerprint": fingerprint,
                    "case_count": len(cases),
                    "by_category": dict(Counter(c["case_type"] for c in cases)),
                    "by_split": dict(Counter(c["split"] for c in cases)),
                    "batches": len(batches(cases)),
                }
            )
        )
        return 0
    args.output_dir.mkdir(parents=True, exist_ok=True)
    state_path = args.output_dir / "state.json"
    if args.stage == "report":
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state["fingerprint"] != fingerprint:
            raise ValueError("Report and frozen dataset differ")
        report(cases, state, args.output_dir)
        return 0
    if args.stage == "policy":
        state = open_state(
            state_path, fingerprint, {"workspace_id": None, "mode": "offline_policy_only"}
        )
        offline_policy(cases, state)
        save_json(state_path, state)
        report(cases, state, args.output_dir)
        return 0
    if not args.acknowledge_egress:
        raise ValueError(
            "Live stages require --acknowledge-egress for synthetic data and existing providers"
        )
    parsed = urlparse(args.base_url)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
        or parsed.username
        or parsed.password
    ):
        raise ValueError("This local benchmark accepts only a loopback HTTP product URL")
    environment = {**(dotenv_values(args.env_file) if args.env_file else {}), **os.environ}
    token, email, password = (
        environment.get(k)
        for k in ("WORKBENCH_ACCESS_TOKEN", "WORKBENCH_EMAIL", "WORKBENCH_PASSWORD")
    )
    with httpx.Client(
        base_url=args.base_url, timeout=150, follow_redirects=False, trust_env=False
    ) as client:
        if not token:
            if not email or not password:
                raise ValueError(
                    "Normal product login credentials are missing; no live calls executed"
                )
            response = client.post("/api/auth/login", json={"email": email, "password": password})
            response.raise_for_status()
            token = response.json()["access_token"]
        client.headers["Authorization"] = f"Bearer {token}"
        workspaces = client.get("/api/workspaces")
        workspaces.raise_for_status()
        available = workspaces.json()
        workspace_id = args.workspace_id or environment.get("WORKBENCH_WORKSPACE_ID")
        if not workspace_id and len(available) == 1:
            workspace_id = available[0]["id"]
        if not workspace_id or workspace_id not in {v["id"] for v in available}:
            raise ValueError("Select a Workspace from normal authorized membership")
        state = open_state(
            state_path,
            fingerprint,
            {"workspace_id": workspace_id, "base_url": args.base_url, "mode": "live_product"},
        )
        op = Operations(client, state, state_path)
        if args.continue_diagnosed_errors:
            state.setdefault("diagnosis_log", []).append(
                {
                    "at": utc_now(),
                    "stage": args.stage,
                    "reason": args.continue_diagnosed_errors.strip(),
                    "allowed_errors": ["provider_contract", "generation_http_502"],
                    "mode": "remaining first attempts; failures retained; no retries",
                }
            )
            op.persist()
        try:
            if args.stage in {"prepare", "all"}:
                prepare(op, manifest, cases, args.data_dir)
            if args.stage != "prepare":
                verify_resources(op, manifest, cases)
                # Independent component probes first. Agent runs follow, with frozen product limits.
                for stage in (
                    ("retrieval", "answers", "agent") if args.stage == "all" else (args.stage,)
                ):
                    probe_configuration(op, cases)
                    if stage == "agent":
                        evaluate_agent(op, cases, args.continue_diagnosed_errors)
                    else:
                        rag(op, cases, stage, args.continue_diagnosed_errors)
        finally:
            report(cases, state, args.output_dir)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, httpx.HTTPError) as error:
        # Never print payloads, credentials, server error bodies or an exception chain.
        print(
            f"Benchmark stopped: {type(error).__name__}; inspect prerequisites/checkpoint",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
