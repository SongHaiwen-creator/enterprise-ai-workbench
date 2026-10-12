from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.models import Chunk, Document, DocumentFamily, KnowledgeBase, Membership, User, Workspace
from app.models.enums import DocumentFileType, MembershipRole
from app.schemas.document import DocumentActivation
from app.schemas.knowledge_base import KnowledgeBaseUpdate
from app.services import documents, evaluation_snapshot, retrieval
from app.services.document_extraction import PreparedDocumentUpload
from app.services.exceptions import ConflictError, ForbiddenError
from app.services.knowledge_bases import update_knowledge_base
from tests.integration.test_document_versions import Embeddings

pytestmark = pytest.mark.integration


@pytest.fixture
def committed(postgres_engine):
    engine = postgres_engine
    with Session(engine) as session:
        user = User(email=f"race-{uuid4()}@example.com", name="Synthetic administrator")
        workspace = Workspace(name="Version race", slug=f"race-{uuid4()}")
        session.add_all([user, workspace])
        session.flush()
        member = Membership(
            user_id=user.id,
            workspace_id=workspace.id,
            role=MembershipRole.KNOWLEDGE_ADMIN,
            status="active",
        )
        kb = KnowledgeBase(workspace_id=workspace.id, name="Version races", created_by=user.id)
        session.add_all([member, kb])
        session.commit()
        ids = workspace.id, kb.id, user.id
        old = documents.upload_document(
            session, *ids, PreparedDocumentUpload("old.txt", DocumentFileType.TXT, b"Old policy")
        )
        old_id, family_id = old.id, old.family_id
        retrieval.index_document(session, ids[0], ids[1], old_id, Embeddings(), actor_id=ids[2])
    try:
        yield engine, ids, old_id, family_id
    finally:
        with Session(engine) as session:
            session.execute(
                update(DocumentFamily)
                .where(DocumentFamily.workspace_id == ids[0])
                .values(current_document_id=None)
            )
            session.execute(delete(Chunk).where(Chunk.workspace_id == ids[0]))
            session.execute(delete(Document).where(Document.workspace_id == ids[0]))
            session.execute(delete(DocumentFamily).where(DocumentFamily.workspace_id == ids[0]))
            session.execute(delete(KnowledgeBase).where(KnowledgeBase.workspace_id == ids[0]))
            session.execute(delete(Membership).where(Membership.workspace_id == ids[0]))
            session.execute(delete(Workspace).where(Workspace.id == ids[0]))
            session.execute(delete(User).where(User.id == ids[2]))
            session.commit()


def candidate(committed):
    engine, ids, _, family_id = committed
    with Session(engine) as session:
        row = documents.upload_document(
            session,
            *ids,
            PreparedDocumentUpload("candidate.md", DocumentFileType.MARKDOWN, b"Candidate policy"),
            family_id=family_id,
        )
        return row.id


def test_concurrent_version_allocation(committed):
    engine, ids, _, family_id = committed
    barrier = Barrier(2)

    def upload():
        with Session(engine) as session:
            barrier.wait(timeout=10)
            row = documents.upload_document(
                session,
                *ids,
                PreparedDocumentUpload("next.txt", DocumentFileType.TXT, b"Next policy"),
                family_id=family_id,
            )
            return row.version

    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(upload) for _ in range(2)]
        assert sorted(f.result(timeout=20) for f in futures) == [2, 3]
    with Session(engine) as session:
        assert session.get(DocumentFamily, family_id).current_document_id == committed[2]


def test_competing_activation_only_one_wins(committed):
    engine, ids, _, family_id = committed
    target = candidate(committed)
    with Session(engine) as session:
        retrieval.index_document(session, ids[0], ids[1], target, Embeddings(), actor_id=ids[2])
        revision = session.get(DocumentFamily, family_id).revision
    barrier = Barrier(2)

    def activate():
        with Session(engine) as session:
            barrier.wait(timeout=10)
            try:
                documents.activate_document(
                    session,
                    ids[0],
                    ids[1],
                    family_id,
                    DocumentActivation(document_id=target, expected_revision=revision),
                    ids[2],
                    "text-embedding-3-small",
                    1536,
                )
                return "success"
            except ConflictError:
                return "conflict"

    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(activate) for _ in range(2)]
        assert sorted(f.result(timeout=20) for f in futures) == ["conflict", "success"]
    with Session(engine) as session:
        family = session.get(DocumentFamily, family_id)
        assert family.current_document_id == target and family.revision == revision + 1


def test_concurrent_first_index_freezes_one_complete_set(committed):
    engine, ids, _, family_id = committed
    target = candidate(committed)
    barrier = Barrier(2)

    class Waiting(Embeddings):
        def embed_texts(self, texts):
            barrier.wait(timeout=10)
            # Prove the provider phase holds no KB write lock in either Session.
            with Session(engine) as session:
                session.execute(
                    select(KnowledgeBase).where(KnowledgeBase.id == ids[1]).with_for_update()
                )
            return super().embed_texts(texts)

    def index():
        with Session(engine) as session:
            return retrieval.index_document(
                session, ids[0], ids[1], target, Waiting(), actor_id=ids[2]
            )

    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(index) for _ in range(2)]
        results = [f.result(timeout=20) for f in futures]
    assert results[0] == results[1]
    with Session(engine) as session:
        chunks = session.scalars(select(Chunk).where(Chunk.document_id == target)).all()
        assert len(chunks) == 1
        assert session.get(DocumentFamily, family_id).current_document_id == committed[2]


def test_provider_phase_revocation_cannot_publish(committed):
    engine, ids, _, _ = committed
    target = candidate(committed)

    class Revokes(Embeddings):
        def embed_texts(self, texts):
            with Session(engine) as session:
                member = session.scalar(
                    select(Membership).where(
                        Membership.workspace_id == ids[0], Membership.user_id == ids[2]
                    )
                )
                member.status = "disabled"
                session.commit()
            return super().embed_texts(texts)

    with Session(engine) as session:
        with pytest.raises(ForbiddenError):
            retrieval.index_document(session, ids[0], ids[1], target, Revokes(), actor_id=ids[2])
        assert session.scalars(select(Chunk).where(Chunk.document_id == target)).all() == []
        assert session.get(Document, target).indexed_at is None


def test_kb_disable_during_provider_cannot_publish(committed):
    engine, ids, _, _ = committed
    target = candidate(committed)

    class Disables(Embeddings):
        def embed_texts(self, texts):
            with Session(engine) as session:
                base = session.scalar(
                    select(KnowledgeBase).where(KnowledgeBase.id == ids[1]).with_for_update()
                )
                base.status = "disabled"
                session.commit()
            return super().embed_texts(texts)

    with Session(engine) as session:
        with pytest.raises(ConflictError):
            retrieval.index_document(session, ids[0], ids[1], target, Disables(), actor_id=ids[2])
        assert session.get(Document, target).indexed_at is None


def test_final_persistence_failure_rolls_back_first_index(committed, monkeypatch):
    engine, ids, _, _ = committed
    target = candidate(committed)
    with Session(engine) as session:
        original, calls = session.commit, []

        def commit():
            calls.append(True)
            if len(calls) == 2:
                raise RuntimeError("simulated final write failure")
            original()

        monkeypatch.setattr(session, "commit", commit)
        with pytest.raises(RuntimeError, match="final write failure"):
            retrieval.index_document(session, ids[0], ids[1], target, Embeddings(), actor_id=ids[2])
        assert session.scalars(select(Chunk).where(Chunk.document_id == target)).all() == []
        assert session.get(Document, target).indexed_at is None


def test_corpus_capture_is_one_statement(committed, monkeypatch):
    from types import SimpleNamespace

    engine, ids, old_id, family_id = committed
    target = candidate(committed)
    with Session(engine) as session:
        retrieval.index_document(session, ids[0], ids[1], target, Embeddings(), actor_id=ids[2])
    with Session(engine) as session:
        original, statements = session.execute, []

        def execute(statement, *args, **kwargs):
            result = original(statement, *args, **kwargs)
            statements.append(statement)
            # Switch just after the corpus SQL has captured its snapshot.
            with Session(engine) as writer:
                revision = writer.get(DocumentFamily, family_id).revision
                documents.activate_document(
                    writer,
                    ids[0],
                    ids[1],
                    family_id,
                    DocumentActivation(document_id=target, expected_revision=revision),
                    ids[2],
                    "text-embedding-3-small",
                    1536,
                )
            return result

        monkeypatch.setattr(session, "execute", execute)
        snapshot = evaluation_snapshot.knowledge_context(
            session,
            ids[0],
            ids[1],
            SimpleNamespace(embedding_model="text-embedding-3-small", embedding_dimensions=1536),
        )
        assert len(statements) == 1
        assert [d["id"] for d in snapshot["corpus"]["documents"]] == [str(old_id)]
        assert {c["document_id"] for c in snapshot["corpus"]["chunks"]} == {str(old_id)}


def test_late_first_parse_cannot_overwrite_explicitly_activated_replacement(committed, monkeypatch):
    engine, ids, _, _ = committed
    started, release = Event(), Event()
    original = documents.extract_text

    def parse(file_type, content):
        if content == b"Slow first version":
            started.set()
            assert release.wait(timeout=20)
        return original(file_type, content)

    monkeypatch.setattr(documents, "extract_text", parse)

    def upload_first():
        with Session(engine) as session:
            return documents.upload_document(
                session,
                *ids,
                PreparedDocumentUpload(
                    "slow-first.txt", DocumentFileType.TXT, b"Slow first version"
                ),
            ).id

    try:
        with ThreadPoolExecutor(1) as pool:
            future = pool.submit(upload_first)
            assert started.wait(timeout=10)
            with Session(engine) as session:
                family = session.scalar(
                    select(DocumentFamily).where(
                        DocumentFamily.workspace_id == ids[0],
                        DocumentFamily.display_name == "slow-first.txt",
                    )
                )
                family_id = family.id
                candidate = documents.upload_document(
                    session,
                    *ids,
                    PreparedDocumentUpload(
                        "fast-replacement.txt", DocumentFileType.TXT, b"Fast replacement"
                    ),
                    family_id=family_id,
                )
                target = candidate.id
                retrieval.index_document(
                    session, ids[0], ids[1], target, Embeddings(), actor_id=ids[2]
                )
                revision = session.get(DocumentFamily, family_id).revision
                documents.activate_document(
                    session,
                    ids[0],
                    ids[1],
                    family_id,
                    DocumentActivation(document_id=target, expected_revision=revision),
                    ids[2],
                    "text-embedding-3-small",
                    1536,
                )
            release.set()
            old_id = future.result(timeout=15)
            with Session(engine) as session:
                assert session.get(Document, old_id).status == "ready"
                assert session.get(DocumentFamily, family_id).current_document_id == target
    finally:
        release.set()


def test_knowledge_base_lock_timeout_is_safe_and_rolls_back(committed):
    engine, ids, _, _ = committed
    with Session(engine) as holder:
        holder.scalar(select(KnowledgeBase).where(KnowledgeBase.id == ids[1]).with_for_update())
        with Session(engine) as contender:
            with pytest.raises(ConflictError, match="Document version operation conflict"):
                update_knowledge_base(
                    contender, ids[0], ids[1], KnowledgeBaseUpdate(status="disabled")
                )
            assert contender.get(KnowledgeBase, ids[1]).status == "active"
