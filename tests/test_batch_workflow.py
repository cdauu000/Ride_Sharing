from fastapi.testclient import TestClient
from sqlalchemy import select

from app.jobs import tick
from app.models import Booking, Driver, Offer, Plan, SeatHold, User, uid
from app.services.batch import run_batch
from tests.conftest import intent, login_as, mutate
from tests.test_pool_workflow import select_pool


def test_batch_moves_only_pending_offer_to_verified_open_pool(
    client: TestClient, accounts: dict
) -> None:
    context = client.app.state.context
    with context.db.transaction() as session:
        first_driver = session.get(User, accounts["driver"]["id"])
        second = User(
            id=uid(),
            email="batch-driver@test.example",
            name="Batch driver",
            role="DRIVER",
            gender="UNKNOWN",
            password_hash=first_driver.password_hash,
            created_at=context.clock.now(),
        )
        session.add(second)
        session.flush()
        session.add(
            Driver(
                id=second.id,
                vehicle_type="CAR4",
                license_plate="TEST-BATCH-2",
                capacity=4,
                location_at=context.clock.now(),
                kyc_status="VERIFIED",
                online=True,
                active=True,
                pool_enabled=True,
                accepts_intercity=True,
                lat=20.983,
                lon=105.731,
            )
        )
    a = select_pool(client, accounts["passenger"], intent())
    login_as(client, accounts["driver"])
    assert mutate(client, f"/api/offers/{a['offer_id']}/accept").status_code == 200
    assert tick(context)["failed"] == 0
    login_as(client, accounts["other"])
    request = mutate(
        client,
        "/api/trip-requests",
        intent(pickup={"lat": 20.983, "lon": 105.731}, dropoff={"lat": 20.995, "lon": 105.807}),
    ).json()
    menu = client.get(f"/api/trip-requests/{request['id']}/recommendations").json()
    candidate = next(
        row
        for row in menu["items"]
        if row["service_code"] == "CAR_URBAN_POOL" and row["source_type"] != "EXISTING_POOL_PLAN"
    )
    response = mutate(
        client, f"/api/recommendations/{menu['run_id']}/select", {"candidate_id": candidate["id"]}
    )
    assert response.status_code == 200, response.text
    b = response.json()
    assert b["ride_status"] == "HELD" and b["ride_plan_id"] != a["ride_plan_id"]
    with context.db.transaction() as session:
        report = run_batch(session, context)
        assert report["assigned"] == 1
    assert tick(context)["failed"] == 0
    with context.db.transaction() as session:
        unchanged = session.get(Booking, a["id"])
        moved = session.get(Booking, b["id"])
        assert unchanged.ride_plan_id == moved.ride_plan_id == a["ride_plan_id"]
        assert unchanged.escrow_status == moved.escrow_status == "DEPOSITED"
        assert moved.ride_status == "CONFIRMED"
        assert session.get(Plan, b["ride_plan_id"]).status == "PLAN_ABORTED"
        assert session.get(Offer, b["offer_id"]).status == "REASSIGNED_BY_BATCH"
        assert (
            session.scalar(select(SeatHold).where(SeatHold.offer_id == b["offer_id"])).status
            == "RELEASED"
        )
        assert (unchanged.current_estimated_price_vnd, moved.current_estimated_price_vnd) == (
            143000,
            105000,
        )
        assert run_batch(session, context)["assigned"] == 0
