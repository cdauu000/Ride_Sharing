from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.export import export_training
from research.data import read_dataset
from research.models import load_bundle
from tests.conftest import intent, login_as, mutate


def test_export_keeps_unresolved_labels_censored_and_removes_identifiers(
    client: TestClient, accounts: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    login_as(client, accounts["passenger"])
    request = mutate(client, "/api/trip-requests", intent()).json()
    run = client.get(f"/api/trip-requests/{request['id']}/recommendations").json()
    candidate = next(c for c in run["items"] if c["service_code"] == "BIKE_URBAN")
    response = mutate(
        client, f"/api/recommendations/{run['run_id']}/select", {"candidate_id": candidate["id"]}
    )
    assert response.status_code == 200
    monkeypatch.setattr("app.export.create_context", lambda settings: client.app.state.context)
    output = tmp_path / "observations"
    export_training(output, "private-test-salt")
    rows = read_dataset(output / "observations.jsonl")
    selected = next(row for row in rows if row.get("selected") == 1)
    assert selected["completed"] is None and selected["ride_started"] is None
    assert "user_id" not in selected and "pickup" not in selected and "dropoff" not in selected
    assert accounts["passenger"]["id"] not in (output / "observations.jsonl").read_text()


@pytest.mark.integration
def test_operator_model_artifact_scores_live_feasible_candidates(
    client: TestClient, accounts: dict
) -> None:
    path = Path("artifacts/models/main_v1")
    if not path.exists():
        pytest.skip("Run the documented research training pipeline to create main_v1 first")
    client.app.state.context.models = load_bundle(path)
    login_as(client, accounts["passenger"])
    request = mutate(client, "/api/trip-requests", intent()).json()
    response = client.get(f"/api/trip-requests/{request['id']}/recommendations")
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert {item["service_code"] for item in items} == {
        "BIKE_URBAN",
        "CAR_URBAN_PRIVATE",
        "CAR_URBAN_POOL",
    }
    assert all("model_version" in item for item in items)
    assert all("features" not in item for item in items)
    login_as(client, accounts["admin"])
    status = client.get("/api/admin/models").json()
    assert status["models"][0]["version"] == "ltr_v9_main_v1"
    assert status["can_multiply_fulfillment"] is False
    assert "oof_folds" not in status["manifest"]
