from fastapi.testclient import TestClient
from sqlalchemy import select

from app.jobs import tick
from app.models import Driver, ScheduledTrip, User, uid
from tests.conftest import login_as, mutate
from tests.research.test_survey import payload as survey_payload
from tests.test_intercity import book_pool, publish, trip_status


def test_admin_views_kyc_anonymous_survey_and_session_revoke(
    client: TestClient, accounts: dict
) -> None:
    login_as(client, accounts["passenger"])
    assert client.post("/api/surveys/responses", json=survey_payload()).status_code == 201
    response = client.post("/api/surveys/responses", json=survey_payload())
    assert response.status_code == 201
    login_as(client, accounts["admin"])
    for path in (
        "fund",
        "metrics",
        "users",
        "jobs",
        "models",
        "batch-runs",
        "pool-trips",
        "safety-incidents",
    ):
        response = client.get("/api/admin/" + path)
        assert response.status_code == 200, (path, response.text)
    summary = client.get("/api/admin/surveys").json()
    assert summary["valid_respondents"] == 2 and summary["real_survey_ready"] is False
    response = mutate(
        client, f"/api/admin/drivers/{accounts['driver']['id']}/kyc-review", {"status": "REJECTED"}
    )
    assert response.status_code == 200, response.text
    login_as(client, accounts["driver"])
    settings = client.get("/api/driver/settings").json()
    assert not settings["pool_enabled"] and not settings["accepts_intercity"]
    assert client.post("/api/auth/refresh").status_code == 200
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_merge_refund_and_two_hour_free_cancellation_window(
    client: TestClient, accounts: dict
) -> None:
    context = client.app.state.context
    with context.db.transaction() as session:
        original = session.get(User, accounts["driver"]["id"])
        user = User(
            id=uid(),
            email="merger@test.example",
            name="merger",
            role="DRIVER",
            password_hash=original.password_hash,
            created_at=context.clock.now(),
            gender="UNKNOWN",
        )
        session.add(user)
        session.flush()
        session.add(
            Driver(
                id=user.id,
                vehicle_type="CAR4",
                capacity=4,
                license_plate="MERGER-1",
                online=True,
                active=True,
                kyc_status="VERIFIED",
                pool_enabled=True,
                accepts_intercity=True,
                accepts_urban=True,
                lat=20.961,
                lon=105.747,
            )
        )
        second = {"id": user.id, "email": user.email, "password": "Test-password-2026!"}
    source = publish(client, accounts)
    target = publish(client, {**accounts, "driver": second}, price=180000)
    booking = book_pool(client, accounts["passenger"], source, 2)
    book_pool(client, accounts["other"], target, 1)
    assert tick(context)["failed"] == 0
    context.clock.offset += 24 * 3600 + 10
    assert tick(context)["failed"] == 0
    with context.db.transaction() as session:
        merged = session.scalar(select(ScheduledTrip).where(ScheduledTrip.status == "MERGED"))
        assert merged is not None
        receiver = session.get(ScheduledTrip, merged.data["merged_into_trip_id"])
        target_id = receiver.id
        assert receiver.status == "MERGE_PENDING_CONFIRMATION"
    login_as(client, accounts["passenger"])
    # The moved passenger may cancel freely; confirmed seats are re-counted after the grace period.
    cancelled = mutate(client, f"/api/bookings/{booking['id']}/cancel")
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["cancellation_fee_vnd"] == 0
    assert tick(context)["failed"] == 0
    context.clock.offset += 2 * 3600 + 1
    assert tick(context)["failed"] == 0
    assert trip_status(client, target_id) == "TOPUP_OFFERED"
