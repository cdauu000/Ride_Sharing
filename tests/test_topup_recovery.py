from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.escrow import EscrowError, EscrowRejected
from app.jobs import tick
from app.models import Booking, Job, ScheduledTrip
from tests.conftest import login_as, mutate
from tests.test_intercity import book_pool, publish, trip_status


def accepted_topups(client: TestClient, accounts: dict) -> tuple[dict, list[dict]]:
    trip = publish(client, accounts)
    bookings = [book_pool(client, accounts[name], trip) for name in ("passenger", "other")]
    context = client.app.state.context
    assert tick(context)["failed"] == 0
    context.clock.offset += 24 * 3600 + 1
    assert tick(context)["failed"] == 0
    for name in ("passenger", "other"):
        login_as(client, accounts[name])
        offer = client.get("/api/intercity/topup-offers").json()[0]
        response = mutate(
            client, f"/api/intercity/topup-offers/{offer['id']}/respond", {"decision": "ACCEPT"}
        )
        assert response.status_code == 200, response.text
    return trip, bookings


def test_partial_topup_rejection_refunds_extras_before_under_min_run(
    client: TestClient, accounts: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    trip, bookings = accepted_topups(client, accounts)
    context = client.app.state.context
    execute = context.escrow.execute
    # Force first top-up to succeed, then a definitive rejection of the second.
    with context.db.transaction() as session:
        topups = list(session.scalars(select(Job).where(Job.job_type == "ESCROW_COMMAND")))
        for job in topups:
            if job.data["action"] == "TOPUP":
                job.run_at = context.clock.now() - (2 if job.target_id == bookings[0]["id"] else 1)

    def rejected_second(command):
        if command.action == "TOPUP" and command.booking_id == bookings[1]["id"]:
            raise EscrowRejected("PASSENGER_TOPUP_REJECTED")
        return execute(command)

    monkeypatch.setattr(context.escrow, "execute", rejected_second)
    assert tick(context)["failed"] == 1
    assert trip_status(client, trip["id"]) == "UNDER_MIN_DRIVER_DECISION"
    for booking in bookings:
        snapshot = context.escrow.get(booking["id"])
        assert snapshot["balance_vnd"] == 200000 and not snapshot["topup_mode"]
        with context.db.transaction() as session:
            row = session.get(Booking, booking["id"])
            assert row.final_price_vnd == 200000 and row.price_status == "FIXED_LOCKED"
    assert context.escrow.get(bookings[0]["id"])["refunded_vnd"] == 118000
    login_as(client, accounts["driver"])
    response = mutate(
        client, f"/api/driver/pool-trips/{trip['id']}/under-min-decision", {"decision": "RUN"}
    )
    assert response.status_code == 200, response.text
    assert trip_status(client, trip["id"]) == "CONFIRMED_UNDER_MIN"


def test_unknown_topup_outcome_stays_blocked_until_original_operation_retried(
    client: TestClient, accounts: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    trip, bookings = accepted_topups(client, accounts)
    context = client.app.state.context
    execute = context.escrow.execute

    def unknown(command):
        if command.action == "TOPUP":
            raise EscrowError("RPC_OUTCOME_UNKNOWN")
        return execute(command)

    monkeypatch.setattr(context.escrow, "execute", unknown)
    assert tick(context)["failed"] == 2
    context.clock.offset += 6 * 3600 + 1
    tick(context)
    login_as(client, accounts["driver"])
    assert (
        mutate(
            client, f"/api/driver/pool-trips/{trip['id']}/under-min-decision", {"decision": "RUN"}
        ).status_code
        == 409
    )
    with context.db.transaction() as session:
        assert session.get(ScheduledTrip, trip["id"]).data["topup_funding"]
        for job in session.scalars(select(Job).where(Job.job_type == "ESCROW_COMMAND")):
            if job.data["action"] == "TOPUP":
                assert job.status != "COMPLETED_NOOP"
                job.run_at = context.clock.now()
    monkeypatch.setattr(context.escrow, "execute", execute)
    assert tick(context)["failed"] == 0
    context.clock.offset += 1
    assert tick(context)["failed"] == 0
    for booking in bookings:
        assert context.escrow.get(booking["id"])["balance_vnd"] == 200000
    assert (
        mutate(
            client, f"/api/driver/pool-trips/{trip['id']}/under-min-decision", {"decision": "RUN"}
        ).status_code
        == 200
    )


def test_admin_retry_preserves_operation_and_is_idempotent(
    client: TestClient, accounts: dict
) -> None:
    context = client.app.state.context
    with context.db.transaction() as session:
        job = Job(
            job_type="RECONCILE",
            target_id="system",
            run_at=context.clock.now(),
            status="DEAD_LETTER",
            attempts=5,
            idempotency_key="reconcile:failed-test",
            data={"immutable": "same-command"},
        )
        session.add(job)
        session.flush()
        job_id = job.id
    login_as(client, accounts["passenger"])
    assert mutate(client, f"/api/admin/jobs/{job_id}/retry").status_code == 403
    login_as(client, accounts["admin"])
    path = f"/api/admin/jobs/{job_id}/retry"
    first = mutate(client, path, key="retry-known-operation")
    assert first.status_code == 200, first.text
    assert mutate(client, path, key="retry-known-operation").json() == first.json()
    assert mutate(client, path).status_code == 409
    with context.db.transaction() as session:
        job = session.get(Job, job_id)
        assert job.data == {"immutable": "same-command"} and job.attempts == 0
        assert job.idempotency_key == "reconcile:failed-test"


def test_intercity_search_date_uses_vietnam_calendar(client: TestClient, accounts: dict) -> None:
    trip = publish(client, accounts)
    context = client.app.state.context
    departure = datetime.fromtimestamp(context.clock.now(), UTC) + timedelta(days=4)
    departure = departure.replace(hour=19, minute=15, second=0)
    with context.db.transaction() as session:
        session.get(ScheduledTrip, trip["id"]).departure_time = departure.timestamp()
    local_day = (departure + timedelta(hours=7)).date().isoformat()
    matches = client.get(f"/api/intercity/pool-trips?date={local_day}").json()
    assert [row["id"] for row in matches] == [trip["id"]]
    assert client.get(f"/api/intercity/pool-trips?date={departure.date().isoformat()}").json() == []
