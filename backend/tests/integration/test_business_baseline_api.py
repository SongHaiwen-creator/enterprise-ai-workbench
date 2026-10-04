"""Contract-check the complete authored dataset on the dedicated PostgreSQL DB."""

import pytest
from benchmarks.business_baseline.dataset import DATA, batches, load, payload
from benchmarks.business_baseline.runner import (
    Operations,
    open_state,
    prepare,
    probe_configuration,
    verify_resources,
)

from app.api.dependencies.embeddings import get_embedding_provider
from app.api.routes.evaluation_runs import evaluation_providers, evaluation_session
from app.main import app
from app.models.enums import MembershipRole
from tests.integration import test_evaluation_api as evaluation_fixtures

client = evaluation_fixtures.client
scenario = evaluation_fixtures.scenario
settings = evaluation_fixtures.settings

pytestmark = pytest.mark.integration


def test_all_business_cases_import_through_existing_authenticated_apis(
    client, scenario, db_session
):
    _, workspace, membership, original, _, headers = scenario
    membership.role = MembershipRole.SYSTEM_ADMIN
    db_session.commit()
    base = f"/api/workspaces/{workspace.id}"
    kb = client.post(
        f"{base}/knowledge-bases", headers=headers, json={"name": "Synthetic business"}
    )
    assert kb.status_code == 201
    tools = {}
    for key in ("get_reimbursement_status", "get_employee_information", "create_it_access_request"):
        response = client.post(
            f"{base}/tools",
            headers=headers,
            json={"tool_key": key, "name": key, "description": "Synthetic"},
        )
        assert response.status_code == 201
        tools[key] = response.json()["id"]
    _, cases, _ = load()
    imported = 0
    for batch_id, rows in batches(cases):
        response = client.post(
            f"{base}/evaluation-datasets", headers=headers, json={"name": batch_id}
        )
        assert response.status_code == 201
        parent = response.json()["id"]
        for case in rows:
            response = client.post(
                f"{base}/evaluation-datasets/{parent}/cases",
                headers=headers,
                json=payload(case, {"kb": kb.json()["id"], "tools": tools}),
            )
            assert response.status_code == 201, case["id"]
            assert response.json()["expected_behavior"] == case["expected_behavior"]
            imported += 1
        listing = client.get(f"{base}/evaluation-datasets/{parent}/cases", headers=headers).json()
        assert len(listing["items"]) == len(rows) <= 5
    assert imported == 108
    preserved = client.get(
        f"{base}/evaluation-datasets/{original.id}/cases", headers=headers
    ).json()
    assert len(preserved["items"]) == 1


def test_prepare_resume_and_frozen_preflight_on_real_postgres(
    client, scenario, db_session, tmp_path
):
    _, workspace, membership, original, _, headers = scenario
    membership.role = MembershipRole.SYSTEM_ADMIN
    db_session.commit()

    class FakeIndexing:
        model = "text-embedding-3-small"
        dimensions = 1536

        def embed_texts(self, texts):
            return [[1.0] + [0.0] * 1535 for _ in texts]

    app.dependency_overrides[get_embedding_provider] = lambda: FakeIndexing()
    manifest, cases, fingerprint = load()
    state = open_state(tmp_path / "state.json", fingerprint, {"workspace_id": str(workspace.id)})
    client.headers.update(headers)
    op = Operations(client, state, tmp_path / "state.json")
    prepare(op, manifest, cases, DATA)
    verify_resources(op, manifest, cases)

    class NoLiveProviders:
        def __getattr__(self, name):
            pytest.fail(f"Permission configuration probe attempted {name}")

    app.dependency_overrides[evaluation_session] = lambda: db_session
    app.dependency_overrides[evaluation_providers] = lambda: NoLiveProviders()
    probe_configuration(op, cases)
    probe_configuration(op, cases)
    assert len(state["configuration_probes"]) == 2
    assert state["configuration"]["providers"]["generation_model"] == "gpt-5.6-terra"
    before = len(op.read(f"{op.base}/evaluation-datasets", params={"limit": 100})["items"])
    prepare(op, manifest, cases, DATA)
    verify_resources(op, manifest, cases)
    after = len(op.read(f"{op.base}/evaluation-datasets", params={"limit": 100})["items"])
    assert before == after == 27
    assert len(state["resources"]["cases"]) == 108
    assert len(state["resources"]["documents"]) == 12
    preserved = op.read(f"{op.base}/evaluation-datasets/{original.id}/cases")
    assert len(preserved["items"]) == 1
    # Changed human gold is caught before a paid run, without rewriting it.
    first = cases[0]
    dataset_id = next(
        v
        for k, v in state["resources"]["datasets"].items()
        if k.startswith("knowledge_qa-development")
    )
    response = client.patch(
        f"{op.base}/evaluation-datasets/{dataset_id}/cases/{state['resources']['cases'][first['id']]}",
        json={"test_input": "changed question"},
    )
    assert response.status_code == 200
    with pytest.raises(ValueError, match="differs"):
        verify_resources(op, manifest, cases)
