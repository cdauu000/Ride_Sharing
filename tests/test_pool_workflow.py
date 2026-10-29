from fastapi.testclient import TestClient
from sqlalchemy import select

from app.jobs import tick
from app.models import Driver, Offer, User, uid
from tests.conftest import intent, login_as, mutate


def select_pool(client: TestClient, account: dict, payload: dict) -> dict:
    login_as(client, account)
    request = mutate(client, "/api/trip-requests", payload).json()
    run = client.get(f"/api/trip-requests/{request['id']}/recommendations").json()
    pool = [c for c in run["items"] if c["service_code"] == "CAR_URBAN_POOL"]
    pool.sort(key=lambda c: c["source_type"] != "EXISTING_POOL_PLAN")
    assert pool, run
    response = mutate(
        client, f"/api/recommendations/{run['run_id']}/select", {"candidate_id": pool[0]["id"]}
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_pool_real_overlap_locks_and_reconciles_fund(client: TestClient, accounts: dict) -> None:
    a = select_pool(client, accounts["passenger"], intent())
    login_as(client, accounts["driver"])
    assert mutate(client, f"/api/offers/{a['offer_id']}/accept").status_code == 200
    tick(client.app.state.context)
    b = select_pool(
        client,
        accounts["other"],
        intent(pickup={"lat": 20.983, "lon": 105.731}, dropoff={"lat": 20.995, "lon": 105.807}),
    )
    assert b["ride_plan_id"] == a["ride_plan_id"] and b["offer_id"] is None
    assert tick(client.app.state.context)["failed"] == 0
    login_as(client, accounts["driver"])
    assert mutate(client, f"/api/rides/{a['ride_plan_id']}/start").status_code == 200
    for index in range(4):
        response = mutate(client, f"/api/rides/{a['ride_plan_id']}/stops/{index}/complete")
        assert response.status_code == 200, response.text
    assert mutate(client, f"/api/rides/{a['ride_plan_id']}/complete").status_code == 200
    assert tick(client.app.state.context)["failed"] == 0
    login_as(client, accounts["passenger"])
    price_a = client.get(f"/api/bookings/{a['id']}/price-breakdown").json()
    assert price_a["final_price_vnd"] == 143000
    assert price_a["settlement"]["fund_contribution_vnd"] == 4290
    login_as(client, accounts["other"])
    price_b = client.get(f"/api/bookings/{b['id']}/price-breakdown").json()
    assert price_b["final_price_vnd"] == 105000
    assert price_b["settlement"]["fund_contribution_vnd"] == 3150
    login_as(client, accounts["admin"])
    fund = client.get("/api/admin/fund").json()
    assert fund["balance_vnd"] == 5007440


def test_unmatched_pool_guarantee_7300(client: TestClient, accounts: dict) -> None:
    a = select_pool(client, accounts["passenger"], intent(passenger_count=2))
    login_as(client, accounts["driver"])
    mutate(client, f"/api/offers/{a['offer_id']}/accept")
    tick(client.app.state.context)
    mutate(client, f"/api/rides/{a['ride_plan_id']}/start")
    for index in range(2):
        assert (
            mutate(client, f"/api/rides/{a['ride_plan_id']}/stops/{index}/complete").status_code
            == 200
        )
    assert tick(client.app.state.context)["failed"] == 0
    login_as(client, accounts["passenger"])
    price = client.get(f"/api/bookings/{a['id']}/price-breakdown").json()
    assert price["final_price_vnd"] == 174000
    assert price["settlement"]["guarantee_amount_vnd"] == 7300
    assert price["settlement"]["total_driver_payout_vnd"] == 155200


def test_three_offer_fresh_holds_accept_at_second_59(client: TestClient, accounts: dict) -> None:
    context = client.app.state.context
    with context.db.transaction() as session:
        old = session.get(User, accounts["driver"]["id"])
        for index in (2, 3):
            user = User(
                id=uid(),
                email=f"driver{index}@test.example",
                name=f"driver{index}",
                role="DRIVER",
                password_hash=old.password_hash,
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
                    license_plate=f"TEST-{index}",
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
            accounts[f"driver{index}"] = {
                "id": user.id,
                "email": user.email,
                "password": "Test-password-2026!",
            }
    a = select_pool(client, accounts["passenger"], intent())
    context.clock.offset += 20.01
    assert tick(context)["failed"] == 0
    context.clock.offset += 20.01
    assert tick(context)["failed"] == 0
    with context.db.transaction() as session:
        pending = session.scalar(
            select(Offer).where(Offer.booking_id == a["id"], Offer.status == "PENDING")
        )
        assert pending and pending.attempt == 3
        account = next(v for v in accounts.values() if v["id"] == pending.driver_id)
        offer_id = pending.id
    context.clock.offset += 18.9
    login_as(client, account)
    response = mutate(client, f"/api/offers/{offer_id}/accept")
    assert response.status_code == 200, response.text
    assert response.json()["ride_status"] == "CONFIRMED"
