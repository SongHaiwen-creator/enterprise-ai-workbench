import pytest

from app.models.enums import DocumentFileType
from app.services.document_extraction import (
    UnsupportedDocumentTypeError,
    UploadValidationError,
    extract_text,
    normalize_file_name,
)


def test_file_name_normalization_removes_paths_controls_and_outer_whitespace() -> None:
    file_name, file_type = normalize_file_name("C:\\fakepath\\ policy\x00.PDF ")

    assert file_name == "policy.PDF"
    assert file_type is DocumentFileType.PDF


@pytest.mark.parametrize("file_name", [None, "", ".", "..", "x" * 252 + ".txt"])
def test_file_name_normalization_rejects_invalid_names(file_name: str | None) -> None:
    with pytest.raises(UploadValidationError, match="valid file name"):
        normalize_file_name(file_name)


def test_file_name_normalization_rejects_unsupported_extension() -> None:
    with pytest.raises(UnsupportedDocumentTypeError, match="Unsupported document type"):
        normalize_file_name("policy.docx")


def test_text_extraction_accepts_utf8_bom_and_normalizes_newlines() -> None:
    content = b"\xef\xbb\xbfLine one\r\nLine two\rLine three"

    assert extract_text(DocumentFileType.TXT, content) == "Line one\nLine two\nLine three"
