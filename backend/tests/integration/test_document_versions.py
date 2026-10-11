import hashlib
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.api.dependencies.embeddings import get_embedding_provider, get_index_embedding_provider
from app.main import app
from app.models import Chunk, Document, DocumentFamily, Membership
from app.models.enums import MembershipRole, MembershipStatus
from app.services import documents, evaluation_snapshot
from app.services.embeddings import EmbeddingProviderError
from tests.integration.test_document_api import (
    add_membership,
    auth_settings,
    bearer,
    client,
    create_knowledge_base,
    create_user,
    create_workspace,
    pdf_bytes,
)

pytestmark = pytest.mark.integration
# Reuse the existing session/auth fixtures, never another database.
__all__ = ["auth_settings", "client"]


class Embeddings:
    model = "text-embedding-3-small"
    dimensions = 1536

    def __init__(self):
        self.calls = []
        self.fail = False

    def embed_texts(self, texts):
        self.calls.append(list(texts))
        if self.fail:
            raise EmbeddingProviderError("Embedding provider request failed")
        return [[1.0] + [0.0] * 1535 for _ in texts]


@pytest.fixture
def scenario(db_session, client, auth_settings):
    user = create_user(db_session, email=f"versions-{uuid4()}@example.com")
    workspace = create_workspace(db_session, slug=f"versions-{uuid4()}")
    add_membership(db_session, user, workspace, role=MembershipRole.KNOWLEDGE_ADMIN)
    kb = create_knowledge_base(db_session, workspace, user)
    db_session.commit()
    base = f"/api/workspaces/{workspace.id}/knowledge-bases/{kb.id}"
    provider = Embeddings()
    app.dependency_overrides[get_embedding_provider] = lambda: provider
    app.dependency_overrides[get_index_embedding_provider] = app.dependency_overrides[
        get_embedding_provider
    ]
    try:
        yield client, db_session, auth_settings, user, workspace, kb, base, provider
    finally:
        app.dependency_overrides.pop(get_embedding_provider, None)
        app.dependency_overrides.pop(get_index_embedding_provider, None)


def upload(s, *, family=None, name="policy.txt", content=b"Original policy"):
    client, _, settings, user, _, _, base, _ = s
    path = f"{base}/document-families/{family}/versions" if family else f"{base}/documents"
    return client.post(path, headers=bearer(user, settings), files={"file": (name, content)})


def index(s, document):
    client, _, settings, user, _, _, base, _ = s
    return client.post(f"{base}/documents/{document['id']}/index", headers=bearer(user, settings))


def family(s, family_id):
    client, _, settings, user, _, _, base, _ = s
    return client.get(
        f"{base}/document-families/{family_id}", headers=bearer(user, settings)
    ).json()


def activate(s, document, *, revision=None):
    client, _, settings, user, _, _, base, _ = s
    family_id = document["family_id"]
    revision = family(s, family_id)["revision"] if revision is None else revision
    return client.post(
        f"{base}/document-families/{family_id}/activate",
        headers=bearer(user, settings),
        json={"document_id": document["id"], "expected_revision": revision},
    )


def search(s):
    client, _, settings, user, _, _, base, _ = s
    return client.post(
        f"{base}/search", headers=bearer(user, settings), json={"query": "policy"}
    ).json()["results"]


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("policy.txt", b"Original policy"),
        ("policy.md", b"# Original policy"),
        ("policy.pdf", pdf_bytes()),
    ],
)
def test_initial_version_and_persistent_frozen_index(scenario, name, content):
    s = scenario
    response = upload(s, name=name, content=content)
    assert response.status_code == 201, response.text
    old = response.json()
    assert old["is_current"] and old["indexing"] is None and old["version"] == 1
    assert "extracted_text" not in old
    result = index(s, old)
    assert result.status_code == 200, result.text
    chunk_ids = [chunk.id for chunk in s[1].scalars(select(Chunk)).all()]
    call_count = len(s[-1].calls)
    again = index(s, old)
    assert again.status_code == 200 and again.json() == result.json()
    assert len(s[-1].calls) == call_count
    assert [chunk.id for chunk in s[1].scalars(select(Chunk)).all()] == chunk_ids
    detail = s[0].get(f"{s[6]}/documents/{old['id']}", headers=bearer(s[3], s[2])).json()
    assert detail["indexing"]["chunk_count"] == 1
    stored = s[1].get(Document, old["id"])
    assert detail["content_sha256"] == hashlib.sha256(stored.extracted_text.encode()).hexdigest()


def test_replacement_activation_rollback_disable_and_history(scenario):
    s = scenario
    old = upload(s).json()
    assert index(s, old).status_code == 200
    original_chunks = [c.id for c in s[1].scalars(select(Chunk)).all()]
    new = upload(s, family=old["family_id"], name="updated.md", content=b"New policy").json()
    assert new["version"] == 2 and not new["is_current"]
    assert activate(s, new).status_code == 409
    assert [row["document_id"] for row in search(s)] == [old["id"]]
    assert index(s, new).status_code == 200
    assert [row["document_id"] for row in search(s)] == [old["id"]]
    revision = family(s, old["family_id"])["revision"]
    assert activate(s, new, revision=revision).status_code == 200
    assert activate(s, old, revision=revision).status_code == 409
    assert [row["document_id"] for row in search(s)] == [new["id"]]
    assert search(s)[0]["family_id"] == old["family_id"]
    fresh = family(s, old["family_id"])["revision"]
    assert activate(s, new, revision=fresh).json()["revision"] == fresh
    headers = bearer(s[3], s[2])
    assert (
        s[0]
        .patch(f"{s[6]}/documents/{new['id']}", headers=headers, json={"status": "disabled"})
        .status_code
        == 200
    )
    assert search(s) == []
    assert activate(s, old).status_code == 200
    assert search(s)[0]["document_id"] == old["id"]
    assert all(s[1].get(Chunk, chunk_id) is not None for chunk_id in original_chunks)
    assert s[0].get(f"{s[6]}/documents/{new['id']}", headers=headers).json()["is_current"] is False
    assert (
        s[0]
        .patch(f"{s[6]}/documents/{new['id']}", headers=headers, json={"status": "ready"})
        .status_code
        == 200
    )
    assert search(s)[0]["document_id"] == old["id"]


def test_failed_parse_and_index_never_publish_and_keep_numbers(scenario):
    s = scenario
    old = upload(s).json()
    assert index(s, old).status_code == 200
    failed = upload(s, family=old["family_id"], content=b"\xff").json()
    assert failed["status"] == "failed" and failed["version"] == 2
    assert failed["content_sha256"] is None and failed["indexing"] is None
    assert activate(s, failed).status_code == 409
    candidate = upload(s, family=old["family_id"], content=b"Candidate").json()
    assert candidate["version"] == 3
    s[-1].fail = True
    assert index(s, candidate).status_code == 502
    s[-1].fail = False
    assert search(s)[0]["document_id"] == old["id"]
    assert family(s, old["family_id"])["current_document_id"] == old["id"]


def test_same_name_is_new_family_and_wrong_family_target_is_not_found(scenario):
    s = scenario
    a, b = upload(s).json(), upload(s).json()
    assert a["family_id"] != b["family_id"] and a["version"] == b["version"] == 1
    assert index(s, b).status_code == 200
    response = s[0].post(
        f"{s[6]}/document-families/{a['family_id']}/activate",
        headers=bearer(s[3], s[2]),
        json={"document_id": b["id"], "expected_revision": family(s, a["family_id"])["revision"]},
    )
    assert response.status_code == 404


@pytest.mark.parametrize("revision", [0, -1, True, "1", 1.1, None])
def test_strict_activation_and_safe_validation(scenario, revision):
    s = scenario
    old = upload(s).json()
    response = s[0].post(
        f"{s[6]}/document-families/{old['family_id']}/activate",
        headers=bearer(s[3], s[2]),
        json={"document_id": old["id"], "expected_revision": revision, "secret": "do not echo"},
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid document version request"}


@pytest.mark.parametrize("role", [MembershipRole.EMPLOYEE, MembershipRole.AGENT_ADMIN])
def test_read_metadata_but_no_version_mutations(scenario, role):
    s = scenario
    old = upload(s).json()
    membership = s[1].scalar(select(Membership).where(Membership.user_id == s[3].id))
    membership.role = role
    s[1].commit()
    headers = bearer(s[3], s[2])
    assert s[0].get(f"{s[6]}/document-families", headers=headers).status_code == 200
    assert upload(s, family=old["family_id"]).status_code == 403
    assert activate(s, old).status_code == 403
    assert index(s, old).status_code == 403


def test_snapshot_uses_current_only_and_keeps_frozen_identity(scenario):
    s = scenario
    old = upload(s).json()
    assert index(s, old).status_code == 200
    new = upload(s, family=old["family_id"], content=b"Candidate").json()
    assert index(s, new).status_code == 200
    before = evaluation_snapshot.knowledge_context(s[1], s[4].id, s[5].id, s[2])
    assert before["snapshot_version"] == 2
    assert [d["id"] for d in before["corpus"]["documents"]] == [old["id"]]
    assert index(s, old).status_code == 200
    assert evaluation_snapshot.knowledge_context(s[1], s[4].id, s[5].id, s[2]) == before
    assert activate(s, new).status_code == 200
    after = evaluation_snapshot.knowledge_context(s[1], s[4].id, s[5].id, s[2])
    assert [d["id"] for d in after["corpus"]["documents"]] == [new["id"]]
    assert after != before


def test_parser_revocation_leaves_unpublished_record(scenario, monkeypatch):
    s = scenario
    original = documents.extract_text

    def revoked(*args):
        s[3].status = "disabled"
        s[1].commit()
        return original(*args)

    monkeypatch.setattr(documents, "extract_text", revoked)
    assert upload(s).status_code == 403
    row = s[1].scalar(select(Document))
    assert row.status == "processing" and row.extracted_text is None
    assert s[1].get(DocumentFamily, row.family_id).current_document_id is None


def test_frozen_index_reads_do_not_initialize_unconfigured_sdk(scenario, monkeypatch):
    from app.api.dependencies import embeddings

    s = scenario
    old = upload(s).json()
    assert index(s, old).status_code == 200
    app.dependency_overrides.pop(get_index_embedding_provider)
    monkeypatch.setattr(
        embeddings,
        "create_openai_embedding_provider",
        lambda _: pytest.fail("Frozen index must not initialize SDK"),
    )
    response = index(s, old)
    assert response.status_code == 200
    assert response.json()["chunk_count"] == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"content_sha256": None},
        {"content_sha256": "invalid"},
        {"extracted_text": None},
        {"indexed_dimensions": None},
        {"indexed_chunk_count": 0},
        {"indexed_model": None},
        {"status": "failed"},
    ],
)
def test_index_content_constraints_reject_null_and_invalid_combinations(scenario, changes):
    s = scenario
    old = upload(s).json()
    assert index(s, old).status_code == 200
    with pytest.raises(IntegrityError), s[1].begin_nested():
        s[1].execute(update(Document).where(Document.id == old["id"]).values(**changes))
    assert search(s)[0]["document_id"] == old["id"]


def test_current_pointer_composite_fk_cannot_target_another_family(scenario):
    s = scenario
    a, b = upload(s).json(), upload(s).json()
    with pytest.raises(IntegrityError), s[1].begin_nested():
        s[1].execute(
            update(DocumentFamily)
            .where(DocumentFamily.id == a["family_id"])
            .values(current_document_id=b["id"])
        )
    assert family(s, a["family_id"])["current_document_id"] == a["id"]


def test_cross_workspace_and_kb_paths_cannot_resolve_versions(scenario):
    s = scenario
    old = upload(s).json()
    other = create_workspace(s[1], slug=f"other-{uuid4()}")
    add_membership(s[1], s[3], other, role=MembershipRole.KNOWLEDGE_ADMIN)
    kb = create_knowledge_base(s[1], other, s[3])
    wrong_kb = create_knowledge_base(s[1], s[4], s[3])
    s[1].commit()
    headers = bearer(s[3], s[2])
    for workspace, base in [(other, kb), (s[4], wrong_kb)]:
        path = f"/api/workspaces/{workspace.id}/knowledge-bases/{base.id}"
        family_path = f"{path}/document-families/{old['family_id']}"
        assert s[0].get(family_path, headers=headers).status_code == 404
        assert s[0].get(f"{family_path}/versions", headers=headers).status_code == 404
        assert (
            s[0]
            .post(
                f"{family_path}/versions",
                headers=headers,
                files={"file": ("next.txt", b"New policy")},
            )
            .status_code
            == 404
        )
        assert (
            s[0]
            .post(
                f"{family_path}/activate",
                headers=headers,
                json={"document_id": old["id"], "expected_revision": 3},
            )
            .status_code
            == 404
        )
        assert s[0].get(f"{path}/documents/{old['id']}", headers=headers).status_code == 404


@pytest.mark.parametrize("suffix", ["", "/versions", "/activate"])
def test_family_routes_require_authenticated_membership(scenario, suffix):
    s = scenario
    old = upload(s).json()
    path = f"{s[6]}/document-families/{old['family_id']}{suffix}"
    method = "post" if suffix == "/activate" else "get"
    assert s[0].request(method, path).status_code == 401
    member = s[1].scalar(select(Membership).where(Membership.user_id == s[3].id))
    member.status = MembershipStatus.DISABLED
    s[1].commit()
    assert s[0].request(method, path, headers=bearer(s[3], s[2])).status_code == 403


def test_system_administrator_can_prepare_and_activate(scenario):
    s = scenario
    member = s[1].scalar(select(Membership).where(Membership.user_id == s[3].id))
    member.role = MembershipRole.SYSTEM_ADMIN
    s[1].commit()
    old = upload(s).json()
    replacement = upload(s, family=old["family_id"]).json()
    assert index(s, replacement).status_code == 200
    assert activate(s, replacement).status_code == 200


def test_failed_first_upload_has_no_current_and_replacement_requires_activation(scenario):
    s = scenario
    old = upload(s, content=b"\xff").json()
    assert family(s, old["family_id"])["current_document_id"] is None
    replacement = upload(s, family=old["family_id"]).json()
    assert replacement["version"] == 2 and not replacement["is_current"]
    assert index(s, replacement).status_code == 200 and search(s) == []
    assert activate(s, replacement).status_code == 200
    assert search(s)[0]["document_id"] == replacement["id"]


def test_top_k_filters_closer_candidate_and_history_before_ranking(scenario):
    s = scenario
    old = upload(s).json()
    assert index(s, old).status_code == 200
    replacement = upload(s, family=old["family_id"]).json()
    s[-1].embed_texts = lambda texts: [[0.0, 1.0] + [0.0] * 1534 for _ in texts]
    assert index(s, replacement).status_code == 200
    result = search(s)
    assert len(result) == 1 and result[0]["document_id"] == old["id"]
    assert result[0]["cosine_distance"] == pytest.approx(1.0)
    assert activate(s, replacement).status_code == 200
    result = search(s)
    assert len(result) == 1 and result[0]["document_id"] == replacement["id"]
    assert result[0]["cosine_distance"] == pytest.approx(0.0)
