from collections.abc import Generator, Sequence
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.embeddings import get_embedding_provider
from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.main import app
from app.models import Chunk, Document, KnowledgeBase, Membership, User, Workspace
from app.models.enums import (
    DocumentFileType,
    DocumentStatus,
    KnowledgeBaseStatus,
    MembershipRole,
    MembershipStatus,
    WorkspaceStatus,
)
from app.security.tokens import create_access_token
from app.services import retrieval as retrieval_service
from app.services.embeddings import EmbeddingProviderError

pytestmark = pytest.mark.integration
JWT_SECRET = "retrieval-api-secret-longer-than-thirty-two-bytes"
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536


def embedding_for(text: str) -> list[float]:
    lowered = text.lower()
    if "travel" in lowered:
        prefix = [1.0, 0.0]
    elif "security" in lowered:
        prefix = [0.0, 1.0]
    else:
        prefix = [0.5, 0.5]
    return [*prefix, *([0.0] * (EMBEDDING_DIMENSIONS - len(prefix)))]


class FakeEmbeddingProvider:
    model = EMBEDDING_MODEL
    dimensions = EMBEDDING_DIMENSIONS

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        batch = list(texts)
        self.calls.append(batch)
        return [embedding_for(text) for text in batch]


class FailingEmbeddingProvider(FakeEmbeddingProvider):
    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        del texts
        raise EmbeddingProviderError("Embedding provider request failed")


class WrongDimensionEmbeddingProvider(FakeEmbeddingProvider):
    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]


class ZeroEmbeddingProvider(FakeEmbeddingProvider):
    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        return [[0.0] * self.dimensions for _ in texts]


@pytest.fixture
def auth_settings(database_urls: tuple[object, object]) -> Settings:
    database_url, test_database_url = database_urls
    return Settings(
        database_url=str(database_url),
        test_database_url=str(test_database_url),
        jwt_secret_key=JWT_SECRET,
        openai_api_key=None,
        _env_file=None,
    )


@pytest.fixture
def fake_provider() -> FakeEmbeddingProvider:
    return FakeEmbeddingProvider()


@pytest.fixture
def client(
    db_session: Session,
    auth_settings: Settings,
    fake_provider: FakeEmbeddingProvider,
) -> Generator[TestClient, None, None]:
    def override_db_session() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_settings] = lambda: auth_settings
    app.dependency_overrides[get_embedding_provider] = lambda: fake_provider
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_settings, None)
        app.dependency_overrides.pop(get_embedding_provider, None)


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
    extracted_text: str | None = "Travel policy text",
) -> Document:
    document = Document(
        workspace_id=workspace.id,
        knowledge_base_id=knowledge_base.id,
        file_name=file_name,
        file_type=DocumentFileType.TXT,
        status=status,
        extracted_text=extracted_text,
        processing_error=("Processing failed" if status is DocumentStatus.FAILED else None),
        created_by=creator.id,
    )
    session.add(document)
    session.flush()
    return document


def add_chunk(
    session: Session,
    workspace: Workspace,
    document: Document,
    *,
    content: str,
    chunk_index: int = 0,
) -> Chunk:
    chunk = Chunk(
        workspace_id=workspace.id,
        document_id=document.id,
        content=content,
        chunk_index=chunk_index,
        embedding_model=EMBEDDING_MODEL,
        embedding=embedding_for(content),
    )
    session.add(chunk)
    session.flush()
    return chunk


def bearer(user: User, settings: Settings) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, settings)}"}


def base_path(workspace: Workspace, knowledge_base: KnowledgeBase) -> str:
    return f"/api/workspaces/{workspace.id}/knowledge-bases/{knowledge_base.id}"


def index_path(
    workspace: Workspace,
    knowledge_base: KnowledgeBase,
    document: Document,
) -> str:
    return f"{base_path(workspace, knowledge_base)}/documents/{document.id}/index"


@pytest.mark.parametrize("suffix", ["/search", f"/documents/{uuid4()}/index"])
def test_retrieval_routes_require_authentication(client: TestClient, suffix: str) -> None:
    response = client.post(
        f"/api/workspaces/{uuid4()}/knowledge-bases/{uuid4()}{suffix}",
        json={"query": "travel"} if suffix == "/search" else None,
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}


@pytest.mark.parametrize(
    "role",
    [MembershipRole.KNOWLEDGE_ADMIN, MembershipRole.SYSTEM_ADMIN],
)
def test_authorized_administrator_can_index_document(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    fake_provider: FakeEmbeddingProvider,
    role: MembershipRole,
) -> None:
    caller = create_user(db_session, email=f"index-{role.value}@company.com")
    workspace = create_workspace(db_session, slug=f"index-{role.value}")
    add_membership(db_session, caller, workspace, role=role)
    knowledge_base = create_knowledge_base(db_session, workspace, caller)
    document = create_document(
        db_session,
        workspace,
        knowledge_base,
        caller,
        extracted_text="a" * 1000 + "travel" * 100,
    )

    response = client.post(
        index_path(workspace, knowledge_base, document),
        headers=bearer(caller, auth_settings),
    )

    assert response.status_code == 200
    assert response.json()["document_id"] == str(document.id)
    assert response.json()["chunk_count"] == 2
    assert response.json()["embedding_model"] == EMBEDDING_MODEL
    assert response.json()["embedding_dimensions"] == EMBEDDING_DIMENSIONS
    assert response.json()["indexed_at"] is not None
    chunks = db_session.scalars(
        select(Chunk).where(Chunk.document_id == document.id).order_by(Chunk.chunk_index)
    ).all()
    assert [chunk.chunk_index for chunk in chunks] == [0, 1]
    assert [chunk.workspace_id for chunk in chunks] == [workspace.id, workspace.id]
    assert chunks[0].content == "a" * 1000
    assert chunks[1].content.startswith("a" * 200)
    assert fake_provider.calls == [[chunk.content for chunk in chunks]]


@pytest.mark.parametrize(
    "role",
    [MembershipRole.EMPLOYEE, MembershipRole.AGENT_ADMIN],
)
def test_indexing_requires_knowledge_administrator(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    role: MembershipRole,
) -> None:
    caller = create_user(db_session, email=f"denied-{role.value}@company.com")
    workspace = create_workspace(db_session, slug=f"denied-{role.value}")
    add_membership(db_session, caller, workspace, role=role)
    knowledge_base = create_knowledge_base(db_session, workspace, caller)
    document = create_document(db_session, workspace, knowledge_base, caller)

    response = client.post(
        index_path(workspace, knowledge_base, document),
        headers=bearer(caller, auth_settings),
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Knowledge administrator role required"}


@pytest.mark.parametrize(
    "membership_status",
    [None, MembershipStatus.INVITED, MembershipStatus.DISABLED],
)
def test_indexing_requires_active_membership(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    membership_status: MembershipStatus | None,
) -> None:
    caller = create_user(db_session, email=f"index-membership-{membership_status}@company.com")
    workspace = create_workspace(
        db_session,
        slug=f"index-membership-{membership_status}-{uuid4()}",
    )
    if membership_status is not None:
        add_membership(
            db_session,
            caller,
            workspace,
            role=MembershipRole.KNOWLEDGE_ADMIN,
            status=membership_status,
        )
    knowledge_base = create_knowledge_base(db_session, workspace, caller)
    document = create_document(db_session, workspace, knowledge_base, caller)

    response = client.post(
        index_path(workspace, knowledge_base, document),
        headers=bearer(caller, auth_settings),
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Not authorized for this workspace"}


def test_disabled_workspace_denies_indexing(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
) -> None:
    caller = create_user(db_session, email="disabled-workspace-index@company.com")
    workspace = create_workspace(
        db_session,
        slug="disabled-workspace-index",
        status=WorkspaceStatus.DISABLED,
    )
    add_membership(db_session, caller, workspace, role=MembershipRole.KNOWLEDGE_ADMIN)
    knowledge_base = create_knowledge_base(db_session, workspace, caller)
    document = create_document(db_session, workspace, knowledge_base, caller)

    response = client.post(
        index_path(workspace, knowledge_base, document),
        headers=bearer(caller, auth_settings),
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Not authorized for this workspace"}


def test_reindex_replaces_chunks_without_duplication(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
) -> None:
    caller = create_user(db_session, email="reindex@company.com")
    workspace = create_workspace(db_session, slug="reindex")
    add_membership(db_session, caller, workspace, role=MembershipRole.KNOWLEDGE_ADMIN)
    knowledge_base = create_knowledge_base(db_session, workspace, caller)
    document = create_document(db_session, workspace, knowledge_base, caller)
    old_chunk = add_chunk(db_session, workspace, document, content="Old security content")

    response = client.post(
        index_path(workspace, knowledge_base, document),
        headers=bearer(caller, auth_settings),
    )

    assert response.status_code == 200
    chunks = db_session.scalars(select(Chunk).where(Chunk.document_id == document.id)).all()
    assert len(chunks) == 1
    assert chunks[0].id != old_chunk.id
    assert chunks[0].content == "Travel policy text"


def test_chunking_failure_preserves_existing_chunks(
    db_session: Session,
    fake_provider: FakeEmbeddingProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    caller = create_user(db_session, email="chunking-failure@company.com")
    workspace = create_workspace(db_session, slug="chunking-failure")
    knowledge_base = create_knowledge_base(db_session, workspace, caller)
    document = create_document(db_session, workspace, knowledge_base, caller)
    old_chunk = add_chunk(db_session, workspace, document, content="Existing content")
    old_chunk_id = old_chunk.id
    db_session.commit()

    def fail_chunking(text: str) -> list[str]:
        del text
        raise RuntimeError("simulated chunking failure")

    monkeypatch.setattr(retrieval_service, "split_document_text", fail_chunking)
    with pytest.raises(RuntimeError, match="simulated chunking failure"):
        retrieval_service.index_document(
            db_session,
            workspace.id,
            knowledge_base.id,
            document.id,
            fake_provider,
        )
    db_session.rollback()

    persisted = db_session.scalars(
        select(Chunk).where(Chunk.document_id == document.id)
    ).all()
    assert [chunk.id for chunk in persisted] == [old_chunk_id]


def test_provider_failure_preserves_existing_chunks_and_is_sanitized(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
) -> None:
    caller = create_user(db_session, email="provider-failure@company.com")
    workspace = create_workspace(db_session, slug="provider-failure")
    add_membership(db_session, caller, workspace, role=MembershipRole.KNOWLEDGE_ADMIN)
    knowledge_base = create_knowledge_base(db_session, workspace, caller)
    document = create_document(db_session, workspace, knowledge_base, caller)
    old_chunk = add_chunk(db_session, workspace, document, content="Existing content")
    app.dependency_overrides[get_embedding_provider] = FailingEmbeddingProvider

    response = client.post(
        index_path(workspace, knowledge_base, document),
        headers=bearer(caller, auth_settings),
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "Embedding provider request failed"}
    persisted = db_session.scalars(
        select(Chunk).where(Chunk.document_id == document.id)
    ).all()
    assert [chunk.id for chunk in persisted] == [old_chunk.id]


def test_invalid_embedding_response_preserves_existing_chunks(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
) -> None:
    caller = create_user(db_session, email="invalid-vector@company.com")
    workspace = create_workspace(db_session, slug="invalid-vector")
    add_membership(db_session, caller, workspace, role=MembershipRole.KNOWLEDGE_ADMIN)
    knowledge_base = create_knowledge_base(db_session, workspace, caller)
    document = create_document(db_session, workspace, knowledge_base, caller)
    old_chunk = add_chunk(db_session, workspace, document, content="Existing content")
    app.dependency_overrides[get_embedding_provider] = WrongDimensionEmbeddingProvider

    response = client.post(
        index_path(workspace, knowledge_base, document),
        headers=bearer(caller, auth_settings),
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "Embedding provider request failed"}
    persisted = db_session.scalars(
        select(Chunk).where(Chunk.document_id == document.id)
    ).all()
    assert [chunk.id for chunk in persisted] == [old_chunk.id]


def test_zero_query_embedding_returns_sanitized_provider_failure(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
) -> None:
    caller = create_user(db_session, email="zero-query-vector@company.com")
    workspace = create_workspace(db_session, slug="zero-query-vector")
    add_membership(db_session, caller, workspace)
    knowledge_base = create_knowledge_base(db_session, workspace, caller)
    app.dependency_overrides[get_embedding_provider] = ZeroEmbeddingProvider

    response = client.post(
        f"{base_path(workspace, knowledge_base)}/search",
        headers=bearer(caller, auth_settings),
        json={"query": "travel"},
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "Embedding provider request failed"}


def test_persistence_failure_rolls_back_chunk_replacement(
    db_session: Session,
    fake_provider: FakeEmbeddingProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    caller = create_user(db_session, email="persistence-failure@company.com")
    workspace = create_workspace(db_session, slug="persistence-failure")
    knowledge_base = create_knowledge_base(db_session, workspace, caller)
    document = create_document(db_session, workspace, knowledge_base, caller)
    old_chunk = add_chunk(db_session, workspace, document, content="Existing content")
    old_chunk_id = old_chunk.id
    db_session.commit()

    def fail_commit() -> None:
        raise RuntimeError("simulated commit failure")

    monkeypatch.setattr(db_session, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="simulated commit failure"):
        retrieval_service.index_document(
            db_session,
            workspace.id,
            knowledge_base.id,
            document.id,
            fake_provider,
        )
    db_session.rollback()

    persisted = db_session.scalars(
        select(Chunk).where(Chunk.document_id == document.id)
    ).all()
    assert [chunk.id for chunk in persisted] == [old_chunk_id]


def test_missing_provider_configuration_returns_service_unavailable(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
) -> None:
    caller = create_user(db_session, email="missing-provider@company.com")
    workspace = create_workspace(db_session, slug="missing-provider")
    add_membership(db_session, caller, workspace)
    knowledge_base = create_knowledge_base(db_session, workspace, caller)
    app.dependency_overrides.pop(get_embedding_provider, None)

    response = client.post(
        f"{base_path(workspace, knowledge_base)}/search",
        headers=bearer(caller, auth_settings),
        json={"query": "travel"},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "Embedding provider is not configured"}


@pytest.mark.parametrize(
    ("status", "extracted_text"),
    [
        (DocumentStatus.UPLOADED, "Text"),
        (DocumentStatus.PROCESSING, "Text"),
        (DocumentStatus.FAILED, None),
        (DocumentStatus.DISABLED, "Text"),
        (DocumentStatus.READY, None),
    ],
)
def test_only_ready_extracted_documents_can_be_indexed(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    status: DocumentStatus,
    extracted_text: str | None,
) -> None:
    caller = create_user(db_session, email=f"state-{status.value}-{extracted_text}@company.com")
    workspace = create_workspace(db_session, slug=f"state-{status.value}-{uuid4()}")
    add_membership(db_session, caller, workspace, role=MembershipRole.KNOWLEDGE_ADMIN)
    knowledge_base = create_knowledge_base(db_session, workspace, caller)
    document = create_document(
        db_session,
        workspace,
        knowledge_base,
        caller,
        status=status,
        extracted_text=extracted_text,
    )

    response = client.post(
        index_path(workspace, knowledge_base, document),
        headers=bearer(caller, auth_settings),
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Document is not ready for indexing"}


@pytest.mark.parametrize("role", list(MembershipRole))
def test_active_members_can_search_ranked_workspace_results(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    role: MembershipRole,
) -> None:
    caller = create_user(db_session, email=f"search-{role.value}@company.com")
    workspace = create_workspace(db_session, slug=f"search-{role.value}")
    add_membership(db_session, caller, workspace, role=role)
    knowledge_base = create_knowledge_base(db_session, workspace, caller)
    security_document = create_document(
        db_session,
        workspace,
        knowledge_base,
        caller,
        file_name="security.txt",
        extracted_text="Security policy",
    )
    travel_document = create_document(
        db_session,
        workspace,
        knowledge_base,
        caller,
        file_name="travel.txt",
        extracted_text="Travel policy",
    )
    add_chunk(db_session, workspace, security_document, content="Security policy")
    travel_chunk = add_chunk(db_session, workspace, travel_document, content="Travel policy")

    response = client.post(
        f"{base_path(workspace, knowledge_base)}/search",
        headers=bearer(caller, auth_settings),
        json={"query": "  travel reimbursement  ", "limit": 1},
    )

    assert response.status_code == 200
    assert response.json() == {
        "query": "travel reimbursement",
        "results": [
            {
                "chunk_id": str(travel_chunk.id),
                "document_id": str(travel_document.id),
                "file_name": "travel.txt",
                "document_version": 1,
                "chunk_index": 0,
                "content": "Travel policy",
                "cosine_distance": pytest.approx(0.0),
            }
        ],
    }


def test_search_default_and_maximum_limits_are_deterministic_for_ties(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
) -> None:
    caller = create_user(db_session, email="search-limits@company.com")
    workspace = create_workspace(db_session, slug="search-limits")
    add_membership(db_session, caller, workspace)
    knowledge_base = create_knowledge_base(db_session, workspace, caller)
    document = create_document(db_session, workspace, knowledge_base, caller)
    for chunk_index in range(21):
        add_chunk(
            db_session,
            workspace,
            document,
            content=f"Travel tie {chunk_index}",
            chunk_index=chunk_index,
        )

    default_response = client.post(
        f"{base_path(workspace, knowledge_base)}/search",
        headers=bearer(caller, auth_settings),
        json={"query": "travel"},
    )
    maximum_response = client.post(
        f"{base_path(workspace, knowledge_base)}/search",
        headers=bearer(caller, auth_settings),
        json={"query": "travel", "limit": 20},
    )

    assert default_response.status_code == 200
    assert [result["chunk_index"] for result in default_response.json()["results"]] == list(
        range(5)
    )
    assert maximum_response.status_code == 200
    assert [result["chunk_index"] for result in maximum_response.json()["results"]] == list(
        range(20)
    )


def test_search_returns_empty_results_when_no_documents_are_indexed(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
) -> None:
    caller = create_user(db_session, email="empty-search@company.com")
    workspace = create_workspace(db_session, slug="empty-search")
    add_membership(db_session, caller, workspace)
    knowledge_base = create_knowledge_base(db_session, workspace, caller)

    response = client.post(
        f"{base_path(workspace, knowledge_base)}/search",
        headers=bearer(caller, auth_settings),
        json={"query": "travel"},
    )

    assert response.status_code == 200
    assert response.json() == {"query": "travel", "results": []}


def test_search_excludes_disabled_and_cross_workspace_documents(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
) -> None:
    caller = create_user(db_session, email="isolated-search@company.com")
    workspace = create_workspace(db_session, slug="isolated-search")
    foreign_workspace = create_workspace(db_session, slug="foreign-search")
    add_membership(db_session, caller, workspace)
    knowledge_base = create_knowledge_base(db_session, workspace, caller)
    foreign_knowledge_base = create_knowledge_base(db_session, foreign_workspace, caller)
    allowed = create_document(db_session, workspace, knowledge_base, caller)
    disabled = create_document(
        db_session,
        workspace,
        knowledge_base,
        caller,
        file_name="disabled.txt",
        status=DocumentStatus.DISABLED,
    )
    foreign = create_document(db_session, foreign_workspace, foreign_knowledge_base, caller)
    allowed_chunk = add_chunk(db_session, workspace, allowed, content="Travel allowed")
    add_chunk(db_session, workspace, disabled, content="Travel disabled")
    add_chunk(db_session, foreign_workspace, foreign, content="Travel foreign")

    response = client.post(
        f"{base_path(workspace, knowledge_base)}/search",
        headers=bearer(caller, auth_settings),
        json={"query": "travel"},
    )

    assert response.status_code == 200
    assert [item["chunk_id"] for item in response.json()["results"]] == [
        str(allowed_chunk.id)
    ]


@pytest.mark.parametrize("operation", ["index", "search"])
def test_disabled_knowledge_base_cannot_be_indexed_or_searched(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    operation: str,
) -> None:
    caller = create_user(db_session, email=f"disabled-kb-{operation}@company.com")
    workspace = create_workspace(db_session, slug=f"disabled-kb-{operation}")
    add_membership(db_session, caller, workspace, role=MembershipRole.KNOWLEDGE_ADMIN)
    knowledge_base = create_knowledge_base(
        db_session,
        workspace,
        caller,
        status=KnowledgeBaseStatus.DISABLED,
    )
    document = create_document(db_session, workspace, knowledge_base, caller)
    path = (
        index_path(workspace, knowledge_base, document)
        if operation == "index"
        else f"{base_path(workspace, knowledge_base)}/search"
    )

    response = client.post(
        path,
        headers=bearer(caller, auth_settings),
        json={"query": "travel"} if operation == "search" else None,
    )

    assert response.status_code == 409
    expected = (
        "Cannot index a disabled knowledge base"
        if operation == "index"
        else "Cannot search a disabled knowledge base"
    )
    assert response.json() == {"detail": expected}


@pytest.mark.parametrize(
    "membership_status",
    [None, MembershipStatus.INVITED, MembershipStatus.DISABLED],
)
def test_search_requires_active_membership(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    membership_status: MembershipStatus | None,
) -> None:
    caller = create_user(db_session, email=f"membership-{membership_status}@company.com")
    workspace = create_workspace(db_session, slug=f"membership-{membership_status}-{uuid4()}")
    if membership_status is not None:
        add_membership(db_session, caller, workspace, status=membership_status)
    knowledge_base = create_knowledge_base(db_session, workspace, caller)

    response = client.post(
        f"{base_path(workspace, knowledge_base)}/search",
        headers=bearer(caller, auth_settings),
        json={"query": "travel"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Not authorized for this workspace"}


def test_disabled_workspace_denies_search(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
) -> None:
    caller = create_user(db_session, email="disabled-workspace-search@company.com")
    workspace = create_workspace(
        db_session,
        slug="disabled-workspace-search",
        status=WorkspaceStatus.DISABLED,
    )
    add_membership(db_session, caller, workspace)
    knowledge_base = create_knowledge_base(db_session, workspace, caller)

    response = client.post(
        f"{base_path(workspace, knowledge_base)}/search",
        headers=bearer(caller, auth_settings),
        json={"query": "travel"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Not authorized for this workspace"}


def test_cross_workspace_document_id_does_not_leak_chunks(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
) -> None:
    caller = create_user(db_session, email="cross-workspace-index@company.com")
    workspace = create_workspace(db_session, slug="cross-workspace-index")
    foreign_workspace = create_workspace(db_session, slug="foreign-workspace-index")
    add_membership(db_session, caller, workspace, role=MembershipRole.KNOWLEDGE_ADMIN)
    knowledge_base = create_knowledge_base(db_session, workspace, caller)
    foreign_knowledge_base = create_knowledge_base(db_session, foreign_workspace, caller)
    foreign_document = create_document(
        db_session,
        foreign_workspace,
        foreign_knowledge_base,
        caller,
    )
    foreign_chunk = add_chunk(
        db_session,
        foreign_workspace,
        foreign_document,
        content="Foreign private content",
    )

    response = client.post(
        f"{base_path(workspace, knowledge_base)}/documents/{foreign_document.id}/index",
        headers=bearer(caller, auth_settings),
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Document not found"}
    assert db_session.get(Chunk, foreign_chunk.id) is not None


def test_document_id_from_another_knowledge_base_is_not_accessible(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
) -> None:
    caller = create_user(db_session, email="cross-knowledge-base-index@company.com")
    workspace = create_workspace(db_session, slug="cross-knowledge-base-index")
    add_membership(db_session, caller, workspace, role=MembershipRole.KNOWLEDGE_ADMIN)
    knowledge_base = create_knowledge_base(db_session, workspace, caller)
    other_knowledge_base = create_knowledge_base(db_session, workspace, caller)
    other_document = create_document(
        db_session,
        workspace,
        other_knowledge_base,
        caller,
    )
    other_chunk = add_chunk(
        db_session,
        workspace,
        other_document,
        content="Other knowledge base private content",
    )

    response = client.post(
        f"{base_path(workspace, knowledge_base)}/documents/{other_document.id}/index",
        headers=bearer(caller, auth_settings),
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Document not found"}
    assert db_session.get(Chunk, other_chunk.id) is not None


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"query": ""},
        {"query": "travel", "limit": 0},
        {"query": "travel", "limit": 21},
        {"query": "travel", "unexpected": True},
    ],
)
def test_search_validates_request(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    payload: dict[str, object],
) -> None:
    caller = create_user(db_session, email=f"invalid-search-{uuid4()}@company.com")
    workspace = create_workspace(db_session, slug=f"invalid-search-{uuid4()}")
    add_membership(db_session, caller, workspace)
    knowledge_base = create_knowledge_base(db_session, workspace, caller)

    response = client.post(
        f"{base_path(workspace, knowledge_base)}/search",
        headers=bearer(caller, auth_settings),
        json=payload,
    )

    assert response.status_code == 422
