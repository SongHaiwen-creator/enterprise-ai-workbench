from collections.abc import Generator
from datetime import UTC, datetime
from io import BytesIO
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.main import app
from app.models import Document, KnowledgeBase, Membership, User, Workspace
from app.models.enums import (
    DocumentFileType,
    DocumentStatus,
    KnowledgeBaseStatus,
    MembershipRole,
    MembershipStatus,
    WorkspaceStatus,
)
from app.security.tokens import create_access_token
from app.services.document_extraction import MAX_UPLOAD_BYTES

pytestmark = pytest.mark.integration
JWT_SECRET = "document-api-secret-longer-than-thirty-two-bytes"


@pytest.fixture
def auth_settings(database_urls: tuple[object, object]) -> Settings:
    database_url, test_database_url = database_urls
    return Settings(
        database_url=str(database_url),
        test_database_url=str(test_database_url),
        jwt_secret_key=JWT_SECRET,
        _env_file=None,
    )


@pytest.fixture
def client(
    db_session: Session,
    auth_settings: Settings,
) -> Generator[TestClient, None, None]:
    def override_db_session() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_settings] = lambda: auth_settings
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_settings, None)


def create_user(session: Session, *, email: str) -> User:
    user = User(email=email, name=email.split("@", maxsplit=1)[0].title())
    session.add(user)
    session.flush()
    return user


def create_workspace(
    session: Session,
    *,
    slug: str,
    status: WorkspaceStatus = WorkspaceStatus.ACTIVE,
) -> Workspace:
    workspace = Workspace(name=slug.replace("-", " ").title(), slug=slug, status=status)
    session.add(workspace)
    session.flush()
    return workspace


def add_membership(
    session: Session,
    user: User,
    workspace: Workspace,
    *,
    role: MembershipRole = MembershipRole.EMPLOYEE,
    status: MembershipStatus = MembershipStatus.ACTIVE,
) -> Membership:
    membership = Membership(
        user_id=user.id,
        workspace_id=workspace.id,
        role=role,
        status=status,
        joined_at=datetime.now(UTC) if status is MembershipStatus.ACTIVE else None,
    )
    session.add(membership)
    session.flush()
    return membership


def create_knowledge_base(
    session: Session,
    workspace: Workspace,
    creator: User,
    *,
    status: KnowledgeBaseStatus = KnowledgeBaseStatus.ACTIVE,
) -> KnowledgeBase:
    knowledge_base = KnowledgeBase(
        workspace_id=workspace.id,
        name="Employee Policies",
        status=status,
        created_by=creator.id,
    )
    session.add(knowledge_base)
    session.flush()
    return knowledge_base


def create_document(
    session: Session,
    workspace: Workspace,
    knowledge_base: KnowledgeBase,
    creator: User,
    *,
    file_name: str = "policy.txt",
    status: DocumentStatus = DocumentStatus.READY,
    extracted_text: str | None = "Approved policy text",
) -> Document:
    document = Document(
        workspace_id=workspace.id,
        knowledge_base_id=knowledge_base.id,
        file_name=file_name,
        file_type=DocumentFileType.TXT,
        status=status,
        extracted_text=extracted_text,
        processing_error=("No extractable text found" if status is DocumentStatus.FAILED else None),
        created_by=creator.id,
    )
    session.add(document)
    session.flush()
    return document


def bearer(user: User, settings: Settings) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, settings)}"}


def document_collection(workspace: Workspace, knowledge_base: KnowledgeBase) -> str:
    return f"/api/workspaces/{workspace.id}/knowledge-bases/{knowledge_base.id}/documents"


def text_file(
    name: str = "policy.txt",
    content: bytes = b"Approved policy text",
) -> dict[str, tuple[str, bytes, str]]:
    return {"file": (name, content, "application/octet-stream")}


def pdf_bytes(*, encrypted: bool = False) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_reference = writer._add_object(font)
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_reference})}
    )
    content = DecodedStreamObject()
    content.set_data(b"BT /F1 12 Tf 30 200 Td (Approved PDF policy) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(content)
    if encrypted:
        writer.encrypt("password")
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


@pytest.mark.parametrize(
    ("method", "suffix"),
    [
        ("get", ""),
        ("post", ""),
        ("get", f"/{uuid4()}"),
        ("patch", f"/{uuid4()}"),
    ],
)
def test_document_routes_require_authentication(
    client: TestClient,
    method: str,
    suffix: str,
) -> None:
    path = f"/api/workspaces/{uuid4()}/knowledge-bases/{uuid4()}/documents{suffix}"
    response = client.request(method, path)

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    ("file_name", "content", "expected_type", "expected_text"),
    [
        ("policy.txt", b"Line one\r\nLine two", "txt", "Line one\nLine two"),
        ("policy.md", b"# Policy\n\nApproved", "md", "# Policy\n\nApproved"),
        ("policy.pdf", None, "pdf", "Approved PDF policy"),
    ],
)
@pytest.mark.parametrize(
    "role",
    [MembershipRole.KNOWLEDGE_ADMIN, MembershipRole.SYSTEM_ADMIN],
)
def test_authorized_administrator_can_upload_supported_document(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    file_name: str,
    content: bytes | None,
    expected_type: str,
    expected_text: str,
    role: MembershipRole,
) -> None:
    caller = create_user(db_session, email=f"{role.value}-{expected_type}@company.com")
    workspace = create_workspace(db_session, slug=f"{role.value}-{expected_type}")
    add_membership(db_session, caller, workspace, role=role)
    knowledge_base = create_knowledge_base(db_session, workspace, caller)

    response = client.post(
        document_collection(workspace, knowledge_base),
        headers=bearer(caller, auth_settings),
        files=text_file(file_name, pdf_bytes() if content is None else content),
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["workspace_id"] == str(workspace.id)
    assert payload["knowledge_base_id"] == str(knowledge_base.id)
    assert payload["created_by"] == str(caller.id)
    assert payload["file_name"] == file_name
    assert payload["file_type"] == expected_type
    assert payload["status"] == "ready"
    assert payload["version"] == 1
    assert payload["processing_error"] is None
    assert "extracted_text" not in payload
    persisted = db_session.get(Document, UUID(payload["id"]))
    assert persisted is not None
    assert persisted.extracted_text == expected_text


@pytest.mark.parametrize(
    ("file_name", "content", "expected_error"),
    [
        ("invalid.txt", b"\xff\xfe", "Document is not valid UTF-8 text"),
        ("blank.md", b"  \r\n ", "No extractable text found"),
        ("broken.pdf", b"%PDF-not-valid", "PDF could not be parsed"),
        ("encrypted.pdf", None, "Encrypted PDF files are not supported"),
    ],
)
def test_processing_failure_is_persisted_and_sanitized(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    file_name: str,
    content: bytes | None,
    expected_error: str,
) -> None:
    caller = create_user(db_session, email=f"failed-{uuid4()}@company.com")
    workspace = create_workspace(db_session, slug=f"failed-{uuid4()}")
    add_membership(db_session, caller, workspace, role=MembershipRole.KNOWLEDGE_ADMIN)
    knowledge_base = create_knowledge_base(db_session, workspace, caller)
    upload = pdf_bytes(encrypted=True) if content is None else content

    response = client.post(
        document_collection(workspace, knowledge_base),
        headers=bearer(caller, auth_settings),
        files=text_file(file_name, upload),
    )

    assert response.status_code == 201
    assert response.json()["status"] == "failed"
    assert response.json()["processing_error"] == expected_error
    persisted = db_session.get(Document, UUID(response.json()["id"]))
    assert persisted is not None
    assert persisted.status is DocumentStatus.FAILED
    assert persisted.extracted_text is None
    assert persisted.processing_error == expected_error


@pytest.mark.parametrize(
    ("file_name", "content", "expected_status", "expected_detail"),
    [
        ("empty.txt", b"", 422, "Document content cannot be empty"),
        ("policy.docx", b"content", 415, "Unsupported document type"),
        ("x" * 252 + ".txt", b"content", 422, "A valid file name is required"),
        (
            "large.txt",
            b"x" * (MAX_UPLOAD_BYTES + 1),
            413,
            "Document exceeds the 10 MiB upload limit",
        ),
    ],
    ids=["empty", "unsupported", "missing-name", "oversized"],
)
def test_invalid_upload_is_rejected_before_document_creation(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    file_name: str,
    content: bytes,
    expected_status: int,
    expected_detail: str,
) -> None:
    caller = create_user(db_session, email=f"invalid-{uuid4()}@company.com")
    workspace = create_workspace(db_session, slug=f"invalid-{uuid4()}")
    add_membership(db_session, caller, workspace, role=MembershipRole.KNOWLEDGE_ADMIN)
    knowledge_base = create_knowledge_base(db_session, workspace, caller)

    response = client.post(
        document_collection(workspace, knowledge_base),
        headers=bearer(caller, auth_settings),
        files=text_file(file_name, content),
    )

    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_detail}
    count = db_session.scalar(select(func.count()).select_from(Document))
    assert count == 0


@pytest.mark.parametrize(
    "role",
    [MembershipRole.EMPLOYEE, MembershipRole.AGENT_ADMIN],
)
@pytest.mark.parametrize("method", ["post", "patch"])
def test_document_mutation_requires_knowledge_administrator(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    role: MembershipRole,
    method: str,
) -> None:
    caller = create_user(db_session, email=f"{role.value}-{method}@company.com")
    workspace = create_workspace(db_session, slug=f"{role.value}-{method}-documents")
    add_membership(db_session, caller, workspace, role=role)
    knowledge_base = create_knowledge_base(db_session, workspace, caller)
    document = create_document(db_session, workspace, knowledge_base, caller)
    path = document_collection(workspace, knowledge_base)
    request_kwargs: dict[str, object] = {"files": text_file()}
    if method == "patch":
        path = f"{path}/{document.id}"
        request_kwargs = {"json": {"status": "disabled"}}

    response = client.request(
        method,
        path,
        headers=bearer(caller, auth_settings),
        **request_kwargs,
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Knowledge administrator role required"}


@pytest.mark.parametrize("role", list(MembershipRole))
def test_active_workspace_member_can_read_document_metadata(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    role: MembershipRole,
) -> None:
    caller = create_user(db_session, email=f"reader-{role.value}@company.com")
    workspace = create_workspace(db_session, slug=f"document-reader-{role.value}")
    add_membership(db_session, caller, workspace, role=role)
    knowledge_base = create_knowledge_base(db_session, workspace, caller)
    document = create_document(db_session, workspace, knowledge_base, caller)

    list_response = client.get(
        document_collection(workspace, knowledge_base),
        headers=bearer(caller, auth_settings),
    )
    item_response = client.get(
        f"{document_collection(workspace, knowledge_base)}/{document.id}",
        headers=bearer(caller, auth_settings),
    )

    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [str(document.id)]
    assert item_response.status_code == 200
    assert item_response.json()["id"] == str(document.id)
    assert "extracted_text" not in item_response.json()


def test_document_list_is_ordered_and_includes_all_statuses(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
) -> None:
    caller = create_user(db_session, email="ordered-documents@company.com")
    workspace = create_workspace(db_session, slug="ordered-documents")
    add_membership(db_session, caller, workspace)
    knowledge_base = create_knowledge_base(db_session, workspace, caller)
    create_document(
        db_session,
        workspace,
        knowledge_base,
        caller,
        file_name="zulu.txt",
        status=DocumentStatus.DISABLED,
    )
    create_document(
        db_session,
        workspace,
        knowledge_base,
        caller,
        file_name="alpha.txt",
        status=DocumentStatus.FAILED,
        extracted_text=None,
    )

    response = client.get(
        document_collection(workspace, knowledge_base),
        headers=bearer(caller, auth_settings),
    )

    assert response.status_code == 200
    assert [(item["file_name"], item["status"]) for item in response.json()] == [
        ("alpha.txt", "failed"),
        ("zulu.txt", "disabled"),
    ]


def test_document_list_is_empty_for_knowledge_base_without_documents(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
) -> None:
    caller = create_user(db_session, email="empty-documents@company.com")
    workspace = create_workspace(db_session, slug="empty-documents")
    add_membership(db_session, caller, workspace)
    knowledge_base = create_knowledge_base(db_session, workspace, caller)

    response = client.get(
        document_collection(workspace, knowledge_base),
        headers=bearer(caller, auth_settings),
    )

    assert response.status_code == 200
    assert response.json() == []


def test_administrator_can_disable_and_reenable_ready_document(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
) -> None:
    caller = create_user(db_session, email="document-manager@company.com")
    workspace = create_workspace(db_session, slug="managed-documents")
    add_membership(db_session, caller, workspace, role=MembershipRole.KNOWLEDGE_ADMIN)
    knowledge_base = create_knowledge_base(db_session, workspace, caller)
    document = create_document(db_session, workspace, knowledge_base, caller)
    endpoint = f"{document_collection(workspace, knowledge_base)}/{document.id}"

    disabled = client.patch(
        endpoint,
        headers=bearer(caller, auth_settings),
        json={"status": "disabled"},
    )
    reenabled = client.patch(
        endpoint,
        headers=bearer(caller, auth_settings),
        json={"status": "ready"},
    )

    assert disabled.status_code == 200
    assert disabled.json()["status"] == "disabled"
    assert reenabled.status_code == 200
    assert reenabled.json()["status"] == "ready"
    db_session.refresh(document)
    assert document.extracted_text == "Approved policy text"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"status": None},
        {"status": "failed"},
        {"status": "unknown"},
        {"status": "disabled", "unknown": "value"},
    ],
)
def test_invalid_document_status_payload_is_rejected(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    payload: dict[str, object],
) -> None:
    caller = create_user(db_session, email=f"invalid-status-{uuid4()}@company.com")
    workspace = create_workspace(db_session, slug=f"invalid-status-{uuid4()}")
    add_membership(db_session, caller, workspace, role=MembershipRole.KNOWLEDGE_ADMIN)
    knowledge_base = create_knowledge_base(db_session, workspace, caller)
    document = create_document(db_session, workspace, knowledge_base, caller)

    response = client.patch(
        f"{document_collection(workspace, knowledge_base)}/{document.id}",
        headers=bearer(caller, auth_settings),
        json=payload,
    )

    assert response.status_code == 422
    db_session.refresh(document)
    assert document.status is DocumentStatus.READY


def test_invalid_document_status_transition_returns_conflict(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
) -> None:
    caller = create_user(db_session, email="failed-transition@company.com")
    workspace = create_workspace(db_session, slug="failed-transition")
    add_membership(db_session, caller, workspace, role=MembershipRole.KNOWLEDGE_ADMIN)
    knowledge_base = create_knowledge_base(db_session, workspace, caller)
    document = create_document(
        db_session,
        workspace,
        knowledge_base,
        caller,
        status=DocumentStatus.FAILED,
        extracted_text=None,
    )

    response = client.patch(
        f"{document_collection(workspace, knowledge_base)}/{document.id}",
        headers=bearer(caller, auth_settings),
        json={"status": "disabled"},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Invalid document status transition"}


@pytest.mark.parametrize("membership_status", [None, *list(MembershipStatus)[1:]])
@pytest.mark.parametrize("method", ["get", "post"])
def test_document_access_requires_active_membership(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    membership_status: MembershipStatus | None,
    method: str,
) -> None:
    caller = create_user(db_session, email=f"{membership_status}-{method}-{uuid4()}@company.com")
    workspace = create_workspace(db_session, slug=f"membership-{uuid4()}")
    if membership_status is not None:
        add_membership(
            db_session,
            caller,
            workspace,
            role=MembershipRole.KNOWLEDGE_ADMIN,
            status=membership_status,
        )
    knowledge_base = create_knowledge_base(db_session, workspace, caller)
    kwargs: dict[str, object] = {}
    if method == "post":
        kwargs["files"] = text_file()

    response = client.request(
        method,
        document_collection(workspace, knowledge_base),
        headers=bearer(caller, auth_settings),
        **kwargs,
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Not authorized for this workspace"}


def test_disabled_workspace_denies_document_access(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
) -> None:
    caller = create_user(db_session, email="disabled-document-workspace@company.com")
    workspace = create_workspace(
        db_session,
        slug="disabled-document-workspace",
        status=WorkspaceStatus.DISABLED,
    )
    add_membership(db_session, caller, workspace, role=MembershipRole.KNOWLEDGE_ADMIN)
    knowledge_base = create_knowledge_base(db_session, workspace, caller)

    response = client.get(
        document_collection(workspace, knowledge_base),
        headers=bearer(caller, auth_settings),
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Not authorized for this workspace"}


def test_disabled_knowledge_base_rejects_upload_but_allows_metadata_management(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
) -> None:
    caller = create_user(db_session, email="disabled-knowledge-documents@company.com")
    workspace = create_workspace(db_session, slug="disabled-knowledge-documents")
    add_membership(db_session, caller, workspace, role=MembershipRole.KNOWLEDGE_ADMIN)
    knowledge_base = create_knowledge_base(
        db_session,
        workspace,
        caller,
        status=KnowledgeBaseStatus.DISABLED,
    )
    document = create_document(db_session, workspace, knowledge_base, caller)

    upload = client.post(
        document_collection(workspace, knowledge_base),
        headers=bearer(caller, auth_settings),
        files=text_file(),
    )
    listed = client.get(
        document_collection(workspace, knowledge_base),
        headers=bearer(caller, auth_settings),
    )
    disabled = client.patch(
        f"{document_collection(workspace, knowledge_base)}/{document.id}",
        headers=bearer(caller, auth_settings),
        json={"status": "disabled"},
    )

    assert upload.status_code == 409
    assert upload.json() == {"detail": "Cannot upload to a disabled knowledge base"}
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [str(document.id)]
    assert disabled.status_code == 200


@pytest.mark.parametrize("method", ["get", "patch"])
def test_cross_parent_document_id_does_not_leak_existence(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    method: str,
) -> None:
    caller = create_user(db_session, email=f"cross-parent-{method}@company.com")
    workspace = create_workspace(db_session, slug=f"cross-parent-{method}")
    add_membership(db_session, caller, workspace, role=MembershipRole.KNOWLEDGE_ADMIN)
    allowed_knowledge_base = create_knowledge_base(db_session, workspace, caller)
    other_knowledge_base = KnowledgeBase(
        workspace_id=workspace.id,
        name="Other Knowledge",
        created_by=caller.id,
    )
    db_session.add(other_knowledge_base)
    db_session.flush()
    foreign_document = create_document(
        db_session,
        workspace,
        other_knowledge_base,
        caller,
    )
    kwargs = {"json": {"status": "disabled"}} if method == "patch" else {}

    response = client.request(
        method,
        f"{document_collection(workspace, allowed_knowledge_base)}/{foreign_document.id}",
        headers=bearer(caller, auth_settings),
        **kwargs,
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Document not found"}


def test_cross_workspace_knowledge_base_and_document_are_not_accessible(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
) -> None:
    caller = create_user(db_session, email="cross-workspace-document@company.com")
    allowed_workspace = create_workspace(db_session, slug="allowed-document-workspace")
    foreign_workspace = create_workspace(db_session, slug="foreign-document-workspace")
    add_membership(
        db_session,
        caller,
        allowed_workspace,
        role=MembershipRole.KNOWLEDGE_ADMIN,
    )
    foreign_knowledge_base = create_knowledge_base(
        db_session,
        foreign_workspace,
        caller,
    )

    response = client.get(
        document_collection(allowed_workspace, foreign_knowledge_base),
        headers=bearer(caller, auth_settings),
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Knowledge base not found"}


def test_missing_knowledge_base_and_document_return_not_found(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
) -> None:
    caller = create_user(db_session, email="missing-document@company.com")
    workspace = create_workspace(db_session, slug="missing-document")
    add_membership(db_session, caller, workspace)
    knowledge_base = create_knowledge_base(db_session, workspace, caller)

    missing_knowledge_base = client.get(
        f"/api/workspaces/{workspace.id}/knowledge-bases/{uuid4()}/documents",
        headers=bearer(caller, auth_settings),
    )
    missing_document = client.get(
        f"{document_collection(workspace, knowledge_base)}/{uuid4()}",
        headers=bearer(caller, auth_settings),
    )

    assert missing_knowledge_base.status_code == 404
    assert missing_knowledge_base.json() == {"detail": "Knowledge base not found"}
    assert missing_document.status_code == 404
    assert missing_document.json() == {"detail": "Document not found"}
