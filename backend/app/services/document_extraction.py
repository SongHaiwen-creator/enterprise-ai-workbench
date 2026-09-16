import re
import unicodedata
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePath

from fastapi import UploadFile
from pypdf import PdfReader

from app.models.enums import DocumentFileType

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
SUPPORTED_EXTENSIONS = {
    ".pdf": DocumentFileType.PDF,
    ".txt": DocumentFileType.TXT,
    ".md": DocumentFileType.MARKDOWN,
}


class UploadValidationError(ValueError):
    """An upload failed validation before a Document was created."""


class UploadTooLargeError(UploadValidationError):
    """An upload exceeded the bounded MVP size limit."""


class UnsupportedDocumentTypeError(UploadValidationError):
    """An upload has an unsupported file extension."""


class DocumentExtractionError(ValueError):
    """A supported upload could not produce usable text."""


@dataclass(frozen=True)
class PreparedDocumentUpload:
    file_name: str
    file_type: DocumentFileType
    content: bytes


def normalize_file_name(filename: str | None) -> tuple[str, DocumentFileType]:
    if filename is None:
        raise UploadValidationError("A valid file name is required")

    basename = re.split(r"[\\/]", filename)[-1]
    normalized = "".join(
        character for character in basename if unicodedata.category(character) != "Cc"
    ).strip()
    if not normalized or normalized in {".", ".."} or len(normalized) > 255:
        raise UploadValidationError("A valid file name is required")

    extension = PurePath(normalized).suffix.lower()
    try:
        file_type = SUPPORTED_EXTENSIONS[extension]
    except KeyError as exc:
        raise UnsupportedDocumentTypeError("Unsupported document type") from exc
    return normalized, file_type


async def prepare_upload(upload: UploadFile) -> PreparedDocumentUpload:
    file_name, file_type = normalize_file_name(upload.filename)
    content = await upload.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise UploadTooLargeError("Document exceeds the 10 MiB upload limit")
    if not content:
        raise UploadValidationError("Document content cannot be empty")
    return PreparedDocumentUpload(
        file_name=file_name,
        file_type=file_type,
        content=content,
    )


def extract_text(file_type: DocumentFileType, content: bytes) -> str:
    if file_type in {DocumentFileType.TXT, DocumentFileType.MARKDOWN}:
        extracted = _extract_utf8(content)
    else:
        extracted = _extract_pdf(content)

    normalized = extracted.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        raise DocumentExtractionError("No extractable text found")
    return normalized


def _extract_utf8(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DocumentExtractionError("Document is not valid UTF-8 text") from exc


def _extract_pdf(content: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(content))
        if reader.is_encrypted:
            raise DocumentExtractionError("Encrypted PDF files are not supported")
        return "\f".join(page.extract_text() or "" for page in reader.pages)
    except DocumentExtractionError:
        raise
    except Exception as exc:
        raise DocumentExtractionError("PDF could not be parsed") from exc
