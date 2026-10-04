import pytest
from pydantic import ValidationError

from app.schemas.bad_case import BadCaseCreate, BadCaseUpdate, HumanValues
from app.services.bad_cases import TRANSITIONS


@pytest.mark.parametrize(
    "field,value",
    [
        ("title", ""),
        ("title", " " * 5),
        ("title", "x" * 256),
        ("title", None),
        ("title", 12),
        ("description", ""),
        ("description", "x" * 5001),
        ("description", "secret\0"),
        ("description", None),
        ("category", "unknown"),
        ("category", None),
        ("possible_cause", 4),
        ("possible_cause", "x" * 5001),
        ("possible_cause", "secret\0"),
        ("workspace_id", "foreign"),
        ("origin_kind", "manual_review"),
        ("status", "resolved"),
        ("source_run_case_id", "foreign"),
        ("created_by", "fake"),
    ],
)
def test_create_rejects_invalid_and_server_fields(field, value):
    with pytest.raises(ValidationError):
        BadCaseCreate.model_validate(
            {"title": "Synthetic", "description": "Redacted", field: value}
        )


@pytest.mark.parametrize(
    "patch",
    [
        {},
        {"expected_revision": 1},
        {"expected_revision": True, "title": "Valid"},
        {"expected_revision": "1", "title": "Valid"},
        {"expected_revision": 0, "title": "Valid"},
        {"expected_revision": 1, "status": None},
        {"expected_revision": 1, "title": None},
        {"expected_revision": 1, "description": None},
        {"expected_revision": 1, "category": None},
        {"expected_revision": 1, "change_reason": "No change"},
        {"expected_revision": 1, "handling_note": "\0"},
        {"expected_revision": 1, "status": "unknown"},
        {"expected_revision": 1, "title": "Valid", "change_reason": "x" * 1001},
    ],
)
def test_patch_is_strict(patch):
    with pytest.raises(ValidationError):
        BadCaseUpdate.model_validate(patch)


def test_text_normalization_and_merged_resolution():
    value = BadCaseCreate(title=" Synthetic ", description=" Line 1\nLine 2 ", possible_cause=" ")
    assert value.title == "Synthetic" and value.possible_cause is None
    assert value.description == "Line 1\nLine 2"
    for state in ("open", "investigating", "resolved", "dismissed"):
        for note in (None, "Human conclusion"):
            values = {**value.model_dump(), "status": state, "resolution_note": note}
            if (state in {"resolved", "dismissed"}) == (note is not None):
                HumanValues.model_validate(values)
            else:
                with pytest.raises(ValidationError):
                    HumanValues.model_validate(values)
    assert TRANSITIONS["resolved"] == {"open"}
    assert TRANSITIONS["dismissed"] == {"open"}
