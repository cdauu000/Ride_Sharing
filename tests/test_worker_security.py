from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.jobs import tick
from app.models import Driver, Job, Plan
from tests.conftest import intent, login_as, mutate


def create_booking(client: TestClient, account: dict, service: str) -> dict:
    login_as(client, account)
    request = mutate(client, "/api/trip-requests", intent()).json()
    run = client.get(f"/api/trip-requests/{request['id']}/recommendations").json()
    candidate = next(c for c in run["items"] if c["service_code"] == service)
    return mutate(
        client, f"/api/recommendations/{run['run_id']}/select", {"candidate_id": candidate["id"]}
    ).json()


def test_accept_rechecks_revoked_kyc_and_no_show_wait(client: TestClient, accounts: dict) -> None:
    booking = create_booking(client, accounts["passenger"], "CAR_URBAN_POOL")
    with client.app.state.context.db.transaction() as session:
        session.get(Driver, accounts["driver"]["id"]).kyc_status = "REJECTED"
    login_as(client, accounts["driver"])
    response = mutate(client, f"/api/offers/{booking['offer_id']}/accept")
    assert response.json()["detail"]["code"] == "DRIVER_NOT_ELIGIBLE"


def test_failed_deposit_timeout_releases_trip(client: TestClient, accounts: dict) -> None:
    booking = create_booking(client, accounts["passenger"], "BIKE_URBAN")
    login_as(client, accounts["bike"])
    assert mutate(client, f"/api/offers/{booking['offer_id']}/accept").status_code == 200
    context = client.app.state.context
    with context.db.transaction() as session:
        for job in session.scalars(select(Job).where(Job.job_type == "ESCROW_COMMAND")):
            job.run_at = context.clock.now() + 10000
    context.clock.offset += 121
    tick(context)
    login_as(client, accounts["passenger"])
    result = client.get(f"/api/bookings/{booking['id']}").json()
    assert result["ride_status"] == "CANCELLED_BY_SYSTEM"
    with context.db.transaction() as session:
        assert session.get(Plan, booking["ride_plan_id"]).status == "PLAN_ABORTED"


def test_no_show_requires_arrival_evidence_and_five_minutes(
    client: TestClient, accounts: dict
) -> None:
    booking = create_booking(client, accounts["passenger"], "BIKE_URBAN")
    login_as(client, accounts["bike"])
    mutate(client, f"/api/offers/{booking['offer_id']}/accept")
    tick(client.app.state.context)
    assert mutate(client, f"/api/bookings/{booking['id']}/no-show").status_code == 409
    update = client.put(
        "/api/driver/location",
        json={"lat": 20.961, "lon": 105.747},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert update.status_code == 200, update.text
    arrived = mutate(
        client, f"/api/rides/{booking['ride_plan_id']}/arrived", {"booking_id": booking["id"]}
    )
    assert arrived.status_code == 200, arrived.text
    assert mutate(client, f"/api/bookings/{booking['id']}/no-show").status_code == 409
    client.app.state.context.clock.offset += 481
    response = mutate(client, f"/api/bookings/{booking['id']}/no-show")
    assert response.status_code == 200, response.text
    assert response.json()["cancellation_fee_vnd"] == 16200


def test_share_privacy_and_forged_webhook(client: TestClient, accounts: dict) -> None:
    booking = create_booking(client, accounts["passenger"], "BIKE_URBAN")
    share = mutate(client, f"/api/bookings/{booking['id']}/share-link").json()
    login_as(client, accounts["other"])
    assert client.get(f"/api/bookings/{booking['id']}/tracking").status_code == 404
    public = client.get(f"/api/shared/{share['token']}").json()
    assert "pickup" not in public and "dropoff" not in public and "email" not in public
    assert client.post("/api/escrow/webhook", json={"event_id": "forged"}).status_code == 401
