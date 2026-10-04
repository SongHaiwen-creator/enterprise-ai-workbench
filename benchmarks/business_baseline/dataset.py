"""Validate source integrity before importing or paying for any measurement."""

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from uuid import UUID

from app.schemas.evaluation import CaseCreate

DATA = Path(__file__).parent / "data"
PLACEHOLDER = str(UUID(int=1))
COUNTS = {"knowledge_qa": 48, "tool_calling": 24, "permission_boundary": 24, "refusal_behavior": 12}


def payload(case, resources):
    category = case["case_type"]
    body = {
        "name": case["id"],
        "description": case["purpose"],
        "case_type": category,
        "test_input": case["test_input"],
        "expected_behavior": case["expected_behavior"],
    }
    if category == "knowledge_qa" or (
        category == "refusal_behavior"
        and case["expected_behavior"]["routing_intent"] == "knowledge_qa"
    ):
        body["knowledge_base_id"] = resources["kb"]
    if category == "tool_calling" and case["tool_key"]:
        body["tool_id"] = resources["tools"][case["tool_key"]]
    # Nullable fields in typed expectations are required keys (not omitted fields).
    return CaseCreate.model_validate(body).model_dump(mode="json")


def load(root=DATA):
    root = Path(root)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    cases = json.loads((root / "cases.json").read_text(encoding="utf-8"))
    if manifest["synthetic"] is not True or manifest["version"] != "synthetic-employee-v1":
        raise ValueError("Only the reviewed v1 synthetic corpus is supported")
    documents = {}
    for doc in manifest["documents"]:
        name = doc["file_name"]
        if Path(name).name != name or not name.endswith(".txt") or doc["id"] in documents:
            raise ValueError("Invalid or duplicate document")
        documents[doc["id"]] = (root / "docs" / name).read_text(encoding="utf-8")
    if len(documents) != 12 or Counter(c["case_type"] for c in cases) != COUNTS:
        raise ValueError("Unexpected v1 coverage")
    if len({d["file_name"] for d in manifest["documents"]}) != len(documents):
        raise ValueError("Duplicate file names")
    ids, questions, families = set(), set(), defaultdict(set)
    resources = {
        "kb": PLACEHOLDER,
        "tools": {c["tool_key"]: PLACEHOLDER for c in cases if c.get("tool_key")},
    }
    for case in cases:
        if case["id"] in ids or case["test_input"] in questions:
            raise ValueError("Duplicate case or question")
        ids.add(case["id"])
        questions.add(case["test_input"])
        if case["split"] not in {"development", "holdout"}:
            raise ValueError("Invalid split")
        families[case["family"]].add(case["split"])
        payload(case, resources)
        expected = case.get("expected_doc_ids", [])
        if len(set(expected)) != len(expected) or not set(expected).issubset(documents):
            raise ValueError("Invalid evidence references")
        if case["case_type"] == "knowledge_qa":
            if not expected or not case["gold_answer"] or not case["facts"]:
                raise ValueError("Knowledge question lacks gold")
            evidence = case["evidence"]
            if {e["doc_id"] for e in evidence} != set(expected):
                raise ValueError("Gold documents and evidence disagree")
            if [e["quote"] for e in evidence] != case["facts"]:
                raise ValueError("Facts require their own supporting quotes")
            for item in evidence:
                if not item["quote"] or item["quote"] not in documents[item["doc_id"]]:
                    raise ValueError("Gold quote is not in its source")
    if any(len(splits) != 1 for splits in families.values()):
        raise ValueError("Scenario family leaks across splits")
    # Git changes line endings across Windows/Linux. Freeze actual JSON values
    # and normalized text, so the same benchmark has the same portable identity.
    canonical = json.dumps(
        {"manifest": manifest, "cases": cases, "documents": documents},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return manifest, cases, hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def batches(cases):
    groups = defaultdict(list)
    for case in cases:
        groups[(case["case_type"], case["split"])].append(case)
    return [
        (f"{category}-{split}-{i // 5 + 1:02}", rows[i : i + 5])
        for (category, split), rows in sorted(groups.items())
        for i in range(0, len(rows), 5)
    ]
