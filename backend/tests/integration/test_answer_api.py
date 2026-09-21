from collections.abc import Generator, Sequence
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies.embeddings import get_embedding_provider
from app.api.dependencies.generation import get_generation_provider
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
from app.schemas.answer import AnswerStatus, ModelCitation, ModelGenerationOutput
from app.security.tokens import create_access_token
from app.services.embeddings import EmbeddingProvider
from app.services.generation import (
    EvidenceItem,
    GeneratedAnswer,
    GenerationInputTooLargeError,
    GenerationProviderError,
    GenerationUsage,
)

pytestmark = pytest.mark.integration
JWT_SECRET = "answer-api-secret-longer-than-thirty-two-bytes"
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536


def embedding_for(text: str) -> list[float]:
    if "travel" in text.lower():
        prefix = [1.0, 0.0]
    else:
        prefix = [0.0, 1.0]
    return [*prefix, *([0.0] * (EMBEDDING_DIMENSIONS - len(prefix)))]


class FakeEmbeddingProvider:
    model = EMBEDDING_MODEL
    dimensions = EMBEDDING_DIMENSIONS

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        return [embedding_for(text) for text in texts]


class FakeGenerationProvider:
    model = "gpt-5.6-terra"
    reasoning_effort = "low"
    prompt_version = "grounded-answer-v1"
    retrieval_limit = 5
    max_input_tokens = 12_000
    max_output_tokens = 1_200

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[EvidenceItem]]] = []
        self.result: GeneratedAnswer | None = None
        self.error: Exception | None = None

    def generate(
        self,
        question: str,
        evidence: Sequence[EvidenceItem],
    ) -> GeneratedAnswer:
        items = list(evidence)
        self.calls.append((question, items))
        if self.error is not None:
            raise self.error
        if self.result is not None:
            return self.result
        excerpt = items[0].content[:500]
        return GeneratedAnswer(
            output=ModelGenerationOutput.model_validate(
                {
                    "status": "answered",
                    "answer": "The travel policy is supported by the retrieved evidence.",
                    "citations": [
                        {"evidence_ref": items[0].reference, "excerpt": excerpt}
                    ],
                }
            ),
            usage=GenerationUsage(input_tokens=100, output_tokens=20, total_tokens=120),
        )


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
def fake_generation_provider() -> FakeGenerationProvider:
    return FakeGenerationProvider()


@pytest.fixture
def client(
    db_session: Session,
    auth_settings: Settings,
    fake_generation_provider: FakeGenerationProvider,
) -> Generator[TestClient, None, None]:
    def override_db_session() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_settings] = lambda: auth_settings
    app.dependency_overrides[get_embedding_provider] = FakeEmbeddingProvider
    app.dependency_overrides[get_generation_provider] = lambda: fake_generation_provider
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_settings, None)
        app.dependency_overrides.pop(get_embedding_provider, None)
        app.dependency_overrides.pop(get_generation_provider, None)


def create_user(session: Session, email: str) -> User:
    user = User(email=email, name=email.split("@", maxsplit=1)[0])
    session.add(user)
    session.flush()
    return user


def create_workspace(
    session: Session,
    slug: str,
    *,
    status: WorkspaceStatus = WorkspaceStatus.ACTIVE,
) -> Workspace:
    workspace = Workspace(name=slug.title(), slug=slug, status=status)
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
        name=f"{workspace.slug} policies",
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
    file_name: str,
    status: DocumentStatus = DocumentStatus.READY,
) -> Document:
    document = Document(
        workspace_id=workspace.id,
        knowledge_base_id=knowledge_base.id,
        file_name=file_name,
        file_type=DocumentFileType.TXT,
        status=status,
        extracted_text="Source text",
        created_by=creator.id,
    )
    session.add(document)
    session.flush()
    return document


def add_chunk(
    session: Session,
    workspace: Workspace,
    document: Document,
    content: str,
    *,
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


def headers(user: User, settings: Settings) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, settings)}"}


def answer_path(workspace: Workspace, knowledge_base: KnowledgeBase) -> str:
    return f"/api/workspaces/{workspace.id}/knowledge-bases/{knowledge_base.id}/answer"


def set_up_answerable(
    session: Session,
    *,
    role: MembershipRole = MembershipRole.EMPLOYEE,
) -> tuple[User, Workspace, KnowledgeBase, Document, Chunk]:
    user = create_user(session, f"{role.value}-{uuid4()}@company.com")
    workspace = create_workspace(session, f"answer-{uuid4()}")
    add_membership(session, user, workspace, role=role)
    knowledge_base = create_knowledge_base(session, workspace, user)
    document = create_document(
        session,
        workspace,
        knowledge_base,
        user,
        file_name="travel-policy.txt",
    )
    chunk = add_chunk(
        session,
        workspace,
        document,
        "Travel reimbursement is limited to $100 per day.",
    )
    return user, workspace, knowledge_base, document, chunk


def test_answer_route_requires_authentication(client: TestClient) -> None:
    response = client.post(
        f"/api/workspaces/{uuid4()}/knowledge-bases/{uuid4()}/answer",
        json={"question": "travel policy"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}


@pytest.mark.parametrize("role", list(MembershipRole))
def test_active_members_receive_server_mapped_grounded_citation(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    fake_generation_provider: FakeGenerationProvider,
    role: MembershipRole,
) -> None:
    user, workspace, knowledge_base, document, chunk = set_up_answerable(
        db_session,
        role=role,
    )
    chunk_count = db_session.scalar(select(func.count()).select_from(Chunk))

    response = client.post(
        answer_path(workspace, knowledge_base),
        headers=headers(user, auth_settings),
        json={"question": "  What is the travel policy?  "},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["question"] == "What is the travel policy?"
    assert payload["status"] == "answered"
    assert payload["message"] is None
    assert payload["citations"] == [
        {
            "document_id": str(document.id),
            "file_name": "travel-policy.txt",
            "document_version": 1,
            "chunk_id": str(chunk.id),
            "chunk_index": 0,
            "excerpt": chunk.content,
        }
    ]
    assert payload["generation"] == {
        "model": "gpt-5.6-terra",
        "reasoning_effort": "low",
        "retrieval_limit": 5,
        "prompt_version": "grounded-answer-v1",
        "max_input_tokens": 12000,
        "max_output_tokens": 1200,
        "input_tokens": 100,
        "output_tokens": 20,
        "total_tokens": 120,
    }
    question, evidence = fake_generation_provider.calls[0]
    assert question == "What is the travel policy?"
    assert evidence == [EvidenceItem(reference="E1", content=chunk.content)]
    assert db_session.scalar(select(func.count()).select_from(Chunk)) == chunk_count


def test_empty_retrieval_returns_unsupported_without_generation(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    fake_generation_provider: FakeGenerationProvider,
) -> None:
    user = create_user(db_session, "empty-answer@company.com")
    workspace = create_workspace(db_session, f"empty-{uuid4()}")
    add_membership(db_session, user, workspace)
    knowledge_base = create_knowledge_base(db_session, workspace, user)

    response = client.post(
        answer_path(workspace, knowledge_base),
        headers=headers(user, auth_settings),
        json={"question": "Undocumented setting"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "unsupported"
    assert response.json()["answer"] is None
    assert response.json()["citations"] == []
    assert response.json()["generation"]["total_tokens"] is None
    assert fake_generation_provider.calls == []


def test_model_can_return_normal_unsupported_result(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    fake_generation_provider: FakeGenerationProvider,
) -> None:
    user, workspace, knowledge_base, _, _ = set_up_answerable(db_session)
    fake_generation_provider.result = GeneratedAnswer(
        output=ModelGenerationOutput.model_validate(
            {"status": "unsupported", "answer": None, "citations": []}
        ),
        usage=GenerationUsage(input_tokens=80, output_tokens=10, total_tokens=90),
    )

    response = client.post(
        answer_path(workspace, knowledge_base),
        headers=headers(user, auth_settings),
        json={"question": "Exact setting not present"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "unsupported"
    assert response.json()["answer"] is None
    assert response.json()["citations"] == []
    assert response.json()["generation"]["total_tokens"] == 90


@pytest.mark.parametrize("failure", ["unknown", "excerpt", "duplicate"])
def test_unverifiable_citations_fail_closed(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    fake_generation_provider: FakeGenerationProvider,
    failure: str,
) -> None:
    user, workspace, knowledge_base, _, _ = set_up_answerable(db_session)
    citation = ModelCitation.model_construct(
        evidence_ref="E2" if failure == "unknown" else "E1",
        excerpt="fabricated quote" if failure == "excerpt" else "Travel reimbursement",
    )
    citations = [citation, citation] if failure == "duplicate" else [citation]
    invalid_output = ModelGenerationOutput.model_construct(
        status=AnswerStatus.ANSWERED,
        answer="Unverifiable answer",
        citations=citations,
    )
    fake_generation_provider.result = GeneratedAnswer(output=invalid_output, usage=None)

    response = client.post(
        answer_path(workspace, knowledge_base),
        headers=headers(user, auth_settings),
        json={"question": "What is the travel policy?"},
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "Generation provider request failed"}


def test_disabled_and_foreign_documents_never_reach_generation(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    fake_generation_provider: FakeGenerationProvider,
) -> None:
    user, workspace, knowledge_base, _, allowed_chunk = set_up_answerable(db_session)
    disabled_document = create_document(
        db_session,
        workspace,
        knowledge_base,
        user,
        file_name="disabled.txt",
        status=DocumentStatus.DISABLED,
    )
    add_chunk(db_session, workspace, disabled_document, "Travel disabled private text")
    foreign_workspace = create_workspace(db_session, f"foreign-{uuid4()}")
    foreign_kb = create_knowledge_base(db_session, foreign_workspace, user)
    foreign_document = create_document(
        db_session,
        foreign_workspace,
        foreign_kb,
        user,
        file_name="foreign.txt",
    )
    add_chunk(db_session, foreign_workspace, foreign_document, "Travel foreign private text")

    response = client.post(
        answer_path(workspace, knowledge_base),
        headers=headers(user, auth_settings),
        json={"question": "travel policy"},
    )

    assert response.status_code == 200
    _, evidence = fake_generation_provider.calls[0]
    assert evidence == [EvidenceItem(reference="E1", content=allowed_chunk.content)]


@pytest.mark.parametrize(
    "membership_status",
    [None, MembershipStatus.INVITED, MembershipStatus.DISABLED],
)
def test_answer_requires_active_workspace_membership(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    membership_status: MembershipStatus | None,
) -> None:
    user = create_user(db_session, f"inactive-{uuid4()}@company.com")
    workspace = create_workspace(db_session, f"inactive-{uuid4()}")
    if membership_status is not None:
        add_membership(db_session, user, workspace, status=membership_status)
    knowledge_base = create_knowledge_base(db_session, workspace, user)

    response = client.post(
        answer_path(workspace, knowledge_base),
        headers=headers(user, auth_settings),
        json={"question": "travel policy"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Not authorized for this workspace"}


def test_disabled_knowledge_base_cannot_be_answered(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    fake_generation_provider: FakeGenerationProvider,
) -> None:
    user = create_user(db_session, "disabled-kb-answer@company.com")
    workspace = create_workspace(db_session, f"disabled-kb-{uuid4()}")
    add_membership(db_session, user, workspace)
    knowledge_base = create_knowledge_base(
        db_session,
        workspace,
        user,
        status=KnowledgeBaseStatus.DISABLED,
    )

    response = client.post(
        answer_path(workspace, knowledge_base),
        headers=headers(user, auth_settings),
        json={"question": "travel policy"},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Cannot search a disabled knowledge base"}
    assert fake_generation_provider.calls == []


@pytest.mark.parametrize(
    ("error", "status_code", "detail"),
    [
        (
            GenerationProviderError("Generation provider request failed"),
            502,
            "Generation provider request failed",
        ),
        (
            GenerationInputTooLargeError("Generation input exceeds configured budget"),
            422,
            "Generation input exceeds configured budget",
        ),
    ],
)
def test_generation_failures_are_sanitized(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    fake_generation_provider: FakeGenerationProvider,
    error: Exception,
    status_code: int,
    detail: str,
) -> None:
    user, workspace, knowledge_base, _, _ = set_up_answerable(db_session)
    fake_generation_provider.error = error

    response = client.post(
        answer_path(workspace, knowledge_base),
        headers=headers(user, auth_settings),
        json={"question": "private travel question"},
    )

    assert response.status_code == status_code
    assert response.json() == {"detail": detail}
    assert "private travel question" not in response.text


def test_missing_generation_configuration_returns_503(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
) -> None:
    user, workspace, knowledge_base, _, _ = set_up_answerable(db_session)
    app.dependency_overrides.pop(get_generation_provider, None)

    response = client.post(
        answer_path(workspace, knowledge_base),
        headers=headers(user, auth_settings),
        json={"question": "travel policy"},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "Generation provider is not configured"}


def test_empty_retrieval_does_not_require_generation_configuration(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
) -> None:
    user = create_user(db_session, "empty-no-generation@company.com")
    workspace = create_workspace(db_session, f"empty-no-generation-{uuid4()}")
    add_membership(db_session, user, workspace)
    knowledge_base = create_knowledge_base(db_session, workspace, user)
    app.dependency_overrides.pop(get_generation_provider, None)

    response = client.post(
        answer_path(workspace, knowledge_base),
        headers=headers(user, auth_settings),
        json={"question": "undocumented setting"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "unsupported"
    assert response.json()["generation"]["total_tokens"] is None


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"question": ""},
        {"question": "x" * 2001},
        {"question": "travel", "unexpected": True},
    ],
)
def test_answer_request_validation(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    payload: dict[str, object],
) -> None:
    user, workspace, knowledge_base, _, _ = set_up_answerable(db_session)

    response = client.post(
        answer_path(workspace, knowledge_base),
        headers=headers(user, auth_settings),
        json=payload,
    )

    assert response.status_code == 422


def test_generation_provider_protocol_is_satisfied() -> None:
    provider: EmbeddingProvider = FakeEmbeddingProvider()

    assert provider.model == EMBEDDING_MODEL
