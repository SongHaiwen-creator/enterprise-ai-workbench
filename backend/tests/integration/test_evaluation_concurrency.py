import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models import EvaluationCase, EvaluationDataset
from app.models.enums import MembershipRole
from app.schemas.evaluation import CaseCreate, CaseUpdate, DatasetCreate, DatasetUpdate
from app.services import evaluation
from app.services.exceptions import ConflictError
from tests.evaluation_support import case_body
from tests.integration.test_knowledge_base_api import add_membership, create_user, create_workspace

pytestmark = pytest.mark.integration


@pytest.fixture
def committed(postgres_engine, database_urls):
    assert database_urls[1].database == "enterprise_ai_workbench_test"
    factory = sessionmaker(postgres_engine, expire_on_commit=False, autoflush=False)
    with factory() as session:
        user = create_user(session, email=f"concurrency-{uuid4()}@example.test")
        workspace = create_workspace(session, slug=f"concurrency-{uuid4()}")
        add_membership(session, user, workspace, role=MembershipRole.AGENT_ADMIN)
        parent = evaluation.create_dataset(
            session, workspace.id, user.id, DatasetCreate(name="Dataset")
        )
        child = evaluation.create_case(
            session, workspace.id, parent.id, user.id, CaseCreate.model_validate(case_body())
        )
    try:
        yield factory, user.id, workspace.id, parent.id, child.id
    finally:
        # Isolated, uniquely named test fixtures only; avoid polluting later suite counts.
        with factory() as session:
            session.query(EvaluationCase).filter_by(workspace_id=workspace.id).delete()
            session.query(EvaluationDataset).filter_by(workspace_id=workspace.id).delete()
            session.commit()


def test_partial_patches_merge_after_row_lock(committed):
    factory, _, workspace, parent, child = committed
    started = threading.Event()
    with factory() as first, ThreadPoolExecutor(max_workers=1) as executor:
        row = evaluation.get_case(first, workspace, parent, child, lock=True)
        row.name = "First update"

        def second():
            with factory() as session:
                # Prime stale state: populate_existing must refresh it after waiting.
                stale = session.get(EvaluationCase, child)
                assert stale.name == "Synthetic case"
                started.set()
                evaluation.update_case(
                    session, workspace, parent, child, CaseUpdate(description="Second update")
                )

        future = executor.submit(second)
        assert started.wait(2)
        assert not future.done()
        first.commit()
        future.result(timeout=10)
    with factory() as session:
        actual = session.get(EvaluationCase, child)
        assert actual.name == "First update"
        assert actual.description == "Second update"


def test_disable_serializes_case_creation(committed):
    factory, creator, workspace, parent, _ = committed
    started = threading.Event()
    with factory() as first, ThreadPoolExecutor(max_workers=1) as executor:
        dataset = evaluation.get_dataset(first, workspace, parent, lock=True)
        dataset.status = "disabled"

        def create():
            with factory() as session:
                stale = session.get(EvaluationDataset, parent)
                assert stale.status == "active"
                started.set()
                return evaluation.create_case(
                    session, workspace, parent, creator, CaseCreate.model_validate(case_body())
                )

        future = executor.submit(create)
        assert started.wait(2)
        assert not future.done()
        first.commit()
        with pytest.raises(ConflictError, match="disabled"):
            future.result(timeout=10)
    with factory() as session:
        assert (
            len(
                session.scalars(
                    select(EvaluationCase).where(EvaluationCase.dataset_id == parent)
                ).all()
            )
            == 1
        )


def test_lock_timeout_is_safe_and_rolls_back(committed):
    factory, _, workspace, parent, _ = committed
    with factory() as first, factory() as second:
        evaluation.get_dataset(first, workspace, parent, lock=True)
        with pytest.raises(ConflictError, match="Evaluation resource is busy"):
            evaluation.update_dataset(
                second, workspace, parent, DatasetUpdate(name="Never committed")
            )
        assert not second.in_transaction()
        first.rollback()
        assert second.get(EvaluationDataset, parent).name == "Dataset"
