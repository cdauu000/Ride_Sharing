import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.jobs import tick
from app.models import Job
from tests.conftest import intent, login_as, mutate


def test_auth_ownership_and_role_escalation(client: TestClient, accounts: dict) -> None:
    assert client.get("/api/auth/me").status_code == 401
    response = client.post(
        "/api/auth/register",
        json={
            "email": "attacker@test.example",
            "password": "LongPassword1234!",
            "name": "Attacker",
            "role": "ADMIN",
        },
    )
    assert response.status_code == 422
    login_as(client, accounts["passenger"])
    request = mutate(client, "/api/trip-requests", intent()).json()
    login_as(client, accounts["other"])
    assert client.get(f"/api/trip-requests/{request['id']}/recommendations").status_code == 404
    assert client.get("/api/admin/users").status_code == 403


@pytest.mark.parametrize("same_timestamp", [False, True])
def test_booking_escrow_complete_and_idempotency(
    client: TestClient, accounts: dict, monkeypatch: pytest.MonkeyPatch, same_timestamp: bool
) -> None:
    if same_timestamp:
        now = client.app.state.context.clock.now()
        monkeypatch.setattr(client.app.state.context.clock, "now", lambda: now)
    login_as(client, accounts["passenger"])
    response = mutate(client, "/api/trip-requests", intent())
    assert response.status_code == 201, response.text
    request = response.json()
    response = client.get(f"/api/trip-requests/{request['id']}/recommendations")
    assert response.status_code == 200, response.text
    run = response.json()
    assert {c["service_code"] for c in run["items"]} == {
        "BIKE_URBAN",
        "CAR_URBAN_PRIVATE",
        "CAR_URBAN_POOL",
    }
    candidate = next(c for c in run["items"] if c["service_code"] == "BIKE_URBAN")
    path = f"/api/recommendations/{run['run_id']}/select"
    response = mutate(client, path, {"candidate_id": candidate["id"]}, "repeat-key-123")
    assert response.status_code == 200, response.text
    booking = response.json()
    assert (
        mutate(client, path, {"candidate_id": candidate["id"]}, "repeat-key-123").json()["id"]
        == booking["id"]
    )
    assert mutate(client, path, {"candidate_id": "different"}, "repeat-key-123").status_code == 422
    login_as(client, accounts["bike"])
    response = mutate(client, f"/api/offers/{booking['offer_id']}/accept")
    assert response.status_code == 200, response.text
    assert (
        mutate(client, f"/api/rides/{booking['ride_plan_id']}/start").json()["detail"]["code"]
        == "ESCROW_NOT_DEPOSITED"
    )
    tick(client.app.state.context)
    assert mutate(client, f"/api/rides/{booking['ride_plan_id']}/start").status_code == 200
    for index in (0, 1):
        response = mutate(client, f"/api/rides/{booking['ride_plan_id']}/stops/{index}/complete")
        assert response.status_code == 200, response.text
    assert mutate(client, f"/api/rides/{booking['ride_plan_id']}/complete").status_code == 200
    outcome = tick(client.app.state.context)
    with client.app.state.context.db.transaction() as session:
        failures = [
            (j.job_type, j.data, j.last_error)
            for j in session.scalars(select(Job).where(Job.status == "FAILED_RETRY"))
        ]
    assert outcome["failed"] == 0, failures
    login_as(client, accounts["passenger"])
    final = client.get(f"/api/bookings/{booking['id']}").json()
    assert final["ride_status"] == "COMPLETED" and final["escrow_status"] == "RELEASED"
    price = client.get(f"/api/bookings/{booking['id']}/price-breakdown").json()
    assert price["settlement"]["total_driver_payout_vnd"] == 64800
    assert price["settlement"]["tx_hash"] is None


def test_luggage_and_hard_budget_filter(client: TestClient, accounts: dict) -> None:
    login_as(client, accounts["passenger"])
    request = mutate(
        client, "/api/trip-requests", intent(has_luggage=True, budget_max=160000)
    ).json()
    assert "BIKE_URBAN" not in request["allowed_service_codes"]
    run = client.get(f"/api/trip-requests/{request['id']}/recommendations").json()
    assert not run["items"]  # Pool worst-case is174000; the estimate alone is insufficient.


def test_held_cancel_never_creates_escrow(client: TestClient, accounts: dict) -> None:
    login_as(client, accounts["passenger"])
    request = mutate(client, "/api/trip-requests", intent(vehicle_preference="BIKE")).json()
    run = client.get(f"/api/trip-requests/{request['id']}/recommendations").json()
    booking = mutate(
        client,
        f"/api/recommendations/{run['run_id']}/select",
        {"candidate_id": run["items"][0]["id"]},
    ).json()
    response = mutate(client, f"/api/bookings/{booking['id']}/cancel")
    assert response.status_code == 200, response.text
    assert response.json()["escrow_status"] == "NONE"
    with client.app.state.context.db.transaction() as session:
        assert session.scalar(select(Job).where(Job.job_type == "ESCROW_COMMAND")) is None
