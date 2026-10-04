"""Descriptive benchmark measures. Never infer real-traffic accuracy or ROI."""

from collections import Counter
from statistics import mean

from benchmarks.enterprise_rag.runner import answer_metrics, retrieval_metrics


def ratio(n, d):
    return {"count": n, "denominator": d, "value": n / d if d else None}


def summary(cases, state):
    result = {
        "source": "original synthetic employee-service benchmark v1",
        "gold_review": "agent-authored; business-owner review pending",
        "claim_limit": "descriptive synthetic performance; no real-traffic accuracy or ROI",
        "fingerprint": state["fingerprint"],
        "target": state["target"],
        "configuration": state.get("configuration"),
        "configuration_drift": state.get("configuration_drift", False),
        "groups": {},
    }
    observations = state.get("observations", {})
    for split in ("development", "holdout"):
        result["groups"][split] = {}
        for category in sorted({c["case_type"] for c in cases}):
            group = [c for c in cases if c["split"] == split and c["case_type"] == category]
            counts = Counter(
                observations.get(c["id"], {}).get("result") or "pending" for c in group
            )
            scored = counts["passed"] + counts["failed"]
            result["groups"][split][category] = {
                "planned": len(group),
                "counts": dict(counts),
                "non_error_pass_rate": ratio(counts["passed"], scored),
                "passed_over_planned": ratio(counts["passed"], len(group)),
                "coverage": ratio(scored, len(group)),
                "errors_over_planned": ratio(counts["error"], len(group)),
                "mode": "policy_simulation"
                if category == "permission_boundary"
                else "dry_run"
                if category == "tool_calling"
                else "live_model",
            }
    questions = [
        dict(question_id=c["id"], expected_doc_ids=c.get("expected_doc_ids", []))
        for c in cases
        if c["case_type"] == "knowledge_qa"
        or (
            c["case_type"] == "refusal_behavior"
            and c["expected_behavior"]["routing_intent"] == "knowledge_qa"
        )
    ]
    for split in ("development", "holdout"):
        ids = {c["id"] for c in cases if c["split"] == split}
        qs = [q for q in questions if q["question_id"] in ids]
        retrieval = [v for k, v in state.get("retrieval", {}).items() if k in ids]
        answers = [v for k, v in state.get("answers", {}).items() if k in ids]
        result.setdefault("retrieval", {})[split] = retrieval_metrics(retrieval, qs)
        result.setdefault("answers", {})[split] = answer_metrics(answers, qs)
        for kind in ("retrieval", "answers"):
            requests = result[kind][split]["requests"]
            result[kind][split]["measurement_status"] = (
                "not_started"
                if requests["successful"] + requests["failed"] == 0
                else "partial"
                if requests["pending"]
                else "complete"
            )
    reviews = state.get("reviews", {})
    gold_cases = [c for c in cases if c["case_type"] == "knowledge_qa"]
    for split in ("development", "holdout"):
        group = [c for c in gold_cases if c["split"] == split]
        completed, correct, facts, total_facts = 0, 0, 0, 0
        for c in group:
            review = reviews.get(c["id"], {})
            flags = review.get("fact_supported", [])
            if (
                len(flags) == len(c["facts"])
                and all(type(v) is bool for v in flags)
                and type(review.get("correct")) is bool
                and review.get("reviewer")
                and c["id"] in state.get("answers", {})
                and state["answers"][c["id"]].get("request_status") == "success"
            ):
                completed += 1
                correct += int(review["correct"])
                facts += sum(flags)
                total_facts += len(flags)
        result.setdefault("answer_review", {})[split] = {
            "reviewed": completed,
            "unreviewed": len(group) - completed,
            "correct_over_reviewed": ratio(correct, completed),
            "review_coverage": ratio(completed, len(group)),
            "fact_coverage_over_reviewed": ratio(facts, total_facts),
        }
    latency = [v["latency_ms"] for v in observations.values() if v.get("latency_ms") is not None]
    result["observed_latency_ms"] = {
        "count": len(latency),
        "mean": mean(latency) if latency else None,
    }
    result["failures"] = [
        {
            "id": c["id"],
            "category": c["case_type"],
            "split": c["split"],
            "result": observations.get(c["id"], {}).get("result", "pending"),
            "checks": observations.get(c["id"], {}).get("comparison_checks"),
            "error_category": observations.get(c["id"], {}).get("error_category"),
        }
        for c in cases
        if observations.get(c["id"], {}).get("result") in {"failed", "error"}
    ]
    return result


def markdown(result):
    lines = [
        "# 员工服务业务基准 v1",
        "",
        "数据：原创合成制度与任务；标准答案待业务负责人复核。",
        "结果仅代表本基准，不能推断真实业务准确率或节省工时。",
        "",
        "| 分组 | 类别 | 通过 / 未通过 / 错误 / 待评测 | 非错误通过率 | 通过/计划 |",
        "|---|---|---|---|---|---|",
    ]

    def pct(rate):
        return (
            "未测"
            if rate["value"] is None
            else f"{rate['value']:.1%} ({rate['count']}/{rate['denominator']})"
        )

    for split, categories in result["groups"].items():
        for category, row in categories.items():
            counts = row["counts"]
            values = " / ".join(
                str(counts.get(k, 0)) for k in ("passed", "failed", "error", "pending")
            )
            lines.append(
                f"| {split} | {category} | {values} | {pct(row['non_error_pass_rate'])} "
                f"| {pct(row['passed_over_planned'])} |"
            )
    for split, measures in result["retrieval"].items():
        recall = measures["document_recall_at_5"]
        measured = measures["requests"]["successful"] + measures["requests"]["failed"]
        recall_label = f"{recall['macro_average']:.1%}" if measured else "未评测"
        lines += [
            "",
            f"{split} 检索 Recall@5：{recall_label}；"
            f"成功问题 {measures['successful_answerable_question_count']}/{recall['denominator']}。"
            "失败和未测按未命中计；未测不能作为召回质量结论。",
        ]
    lines += [
        "",
        "答案正确性需有署名复核；未复核不计正确。工具结果为 dry run，权限结果为策略模拟。",
        "",
        "机器可读指标和逐题证据见同目录 summary.json 与 state.json；原始输出不得上传未授权服务。",
    ]
    return "\n".join(lines) + "\n"
