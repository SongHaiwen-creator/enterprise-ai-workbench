from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.evaluation import CaseCreate, CaseUpdate, DatasetCreate, DatasetUpdate
from tests.evaluation_support import case_body

CATEGORIES = ("knowledge_qa", "tool_calling", "permission_boundary", "refusal_behavior")


@pytest.mark.parametrize("category", CATEGORIES)
def test_valid_categories(category):
    body = case_body(category)
    body["name"] = "  Synthetic  "
    body["description"] = "  "
    body["test_input"] = "  First\nSecond  "
    parsed = CaseCreate.model_validate(body)
    assert parsed.name == "Synthetic"
    assert parsed.description is None
    assert parsed.test_input == "First\nSecond"


@pytest.mark.parametrize("category", CATEGORIES)
@pytest.mark.parametrize("mutation", ["extra", "missing", "null", "wrong_type"])
def test_each_expectation_field_is_strict(category, mutation):
    # Check each field rather than allowing one early invalid field to mask another.
    body = case_body(category)
    for key in body["expected_behavior"]:
        changed = case_body(category)
        if mutation == "extra":
            changed["expected_behavior"]["foreign_workspace_id"] = str(uuid4())
        elif mutation == "missing":
            del changed["expected_behavior"][key]
        elif mutation == "null":
            if changed["expected_behavior"][key] is None:
                continue
            changed["expected_behavior"][key] = None
        else:
            changed["expected_behavior"][key] = ["invalid"]
        with pytest.raises(ValidationError):
            CaseCreate.model_validate(changed)


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", ""),
        ("name", " "),
        ("name", "x" * 256),
        ("name", 3),
        ("description", "x" * 5001),
        ("test_input", "x" * 2001),
        ("test_input", " "),
        ("test_input", "x\x00y"),
        ("case_type", "future"),
        ("case_type", []),
        ("id", str(uuid4())),
        ("workspace_id", str(uuid4())),
        ("dataset_id", str(uuid4())),
        ("created_by", str(uuid4())),
        ("status", "active"),
        ("schema_version", 2),
    ],
)
def test_create_bounds_and_server_fields(field, value):
    body = case_body()
    body[field] = value
    with pytest.raises(ValidationError):
        CaseCreate.model_validate(body)


@pytest.mark.parametrize("model", [DatasetUpdate, CaseUpdate])
@pytest.mark.parametrize(
    "body",
    [
        {},
        {"name": None},
        {"status": None},
        {"case_type": "knowledge_qa"},
        {"created_at": "now"},
        {"dataset_id": str(uuid4())},
    ],
)
def test_invalid_patch(model, body):
    with pytest.raises(ValidationError):
        model.model_validate(body)


def test_patch_null_and_omission():
    parsed = CaseUpdate(description=None, agent_id=None)
    assert parsed.model_dump(exclude_unset=True) == {"description": None, "agent_id": None}
    assert DatasetCreate(name="x", description="  ").description is None
    for field in ("test_input", "expected_behavior"):
        with pytest.raises(ValidationError):
            CaseUpdate.model_validate({field: None})


@pytest.mark.parametrize(
    "category,key,value",
    [
        ("knowledge_qa", "citation_requirement", "none"),
        ("permission_boundary", "access_denied", False),
        ("permission_boundary", "access_denied", 1),
        ("permission_boundary", "expected_http_status", "404"),
        ("permission_boundary", "expected_http_status", 200),
        ("permission_boundary", "result_category", "forbidden"),
        ("refusal_behavior", "safe_response_required", False),
        ("refusal_behavior", "safe_response_required", "true"),
        ("refusal_behavior", "response_category", "knowledge_unsupported"),
        ("tool_calling", "approval_required", 0),
        ("tool_calling", "tool_key", "arbitrary"),
        ("tool_calling", "non_execution_reason", None),
    ],
)
def test_combination_and_coercion_rejected(category, key, value):
    body = case_body(category)
    body["expected_behavior"][key] = value
    with pytest.raises(ValidationError):
        CaseCreate.model_validate(body)


@pytest.mark.parametrize("category", CATEGORIES)
def test_invalid_reference_combination(category):
    body = case_body(category)
    body["tool_id"] = str(uuid4())
    with pytest.raises(ValidationError):
        CaseCreate.model_validate(body)


@pytest.mark.parametrize(
    "key", ["get_reimbursement_status", "get_employee_information", "create_it_access_request"]
)
def test_tool_selected_expectations(key):
    body = case_body("tool_calling")
    approval = key == "create_it_access_request"
    body["tool_id"] = str(uuid4())
    body["expected_behavior"].update(
        tool_key=key,
        approval_required=approval,
        outcome="approval_required" if approval else "executed",
        non_execution_reason=None,
    )
    assert CaseCreate.model_validate(body).tool_id
    body["expected_behavior"]["approval_required"] = not approval
    with pytest.raises(ValidationError):
        CaseCreate.model_validate(body)
