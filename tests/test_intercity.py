from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config import baseline
from app.domain.errors import DomainError
from app.jobs import tick
from app.models import Booking, Candidate, ScheduledTrip, TripRequest, User, uid
from app.services.booking import choose
from tests.conftest import intent, login_as, mutate


def publish(client: TestClient, accounts: dict, days: float = 4, price: int | None = None) -> dict:
    login_as(client, accounts["driver"])
    now = client.app.state.context.clock.now()
    departure = datetime.fromtimestamp(now, UTC) + timedelta(days=days)
    response = mutate(
        client,
        "/api/driver/pool-trips",
        {
            "corridor_id": "HN_HADONG__HY_TP",
            "origin": {"lat": 20.961, "lon": 105.747},
            "destination": {"lat": 20.646, "lon": 106.051},
            "departure_time": departure.isoformat(),
            "min_seats_to_run": 3,
            "seat_price_vnd": price,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def book_pool(client: TestClient, account: dict, trip: dict, seats: int = 1) -> dict:
    login_as(client, account)
    departure = datetime.fromisoformat(trip["departure_time"])
    payload = intent(
        dropoff={"lat": 20.646, "lon": 106.051},
        passenger_count=seats,
        booking_type="SCHEDULED",
        preferred_departure=departure.isoformat(),
        earliest_departure=(departure - timedelta(minutes=30)).isoformat(),
        latest_departure=(departure + timedelta(minutes=30)).isoformat(),
    )
    response = mutate(client, "/api/trip-requests", payload)
    assert response.status_code == 201, response.text
    request = response.json()
    response = client.get(f"/api/trip-requests/{request['id']}/recommendations")
    assert response.status_code == 200, response.text
    run = response.json()
    candidate = next(
        c
        for c in run["items"]
        if c["service_code"] == "CAR_INTERCITY_POOL" and c["scheduled_trip_id"] == trip["id"]
    )
    response = mutate(
        client, f"/api/recommendations/{run['run_id']}/select", {"candidate_id": candidate["id"]}
    )
    assert response.status_code == 200, response.text
    return response.json()


def trip_status(client: TestClient, key: str) -> str:
    with client.app.state.context.db.transaction() as session:
        return session.get(ScheduledTrip, key).status


def test_confirm_three_seats_preserve_after_late_cancel(client: TestClient, accounts: dict) -> None:
    trip = publish(client, accounts)
    first = book_pool(client, accounts["passenger"], trip, 2)
    book_pool(client, accounts["other"], trip, 1)
    assert tick(client.app.state.context)["failed"] == 0
    client.app.state.context.clock.offset += 24 * 3600 + 1
    assert tick(client.app.state.context)["failed"] == 0
    assert trip_status(client, trip["id"]) == "CONFIRMED"
    client.app.state.context.clock.offset += 36 * 3600
    login_as(client, accounts["passenger"])
    response = mutate(client, f"/api/bookings/{first['id']}/cancel")
    assert response.status_code == 200, response.text
    assert response.json()["cancellation_fee_vnd"] == 200000
    assert tick(client.app.state.context)["failed"] == 0
    assert trip_status(client, trip["id"]) == "CONFIRMED"
    assert client.get(f"/api/bookings/{first['id']}").json()["escrow_status"] == "REFUNDED"


def test_low_demand_unanimous_topup_and_under_min_cancellation(
    client: TestClient, accounts: dict
) -> None:
    trip = publish(client, accounts)
    booking = book_pool(client, accounts["passenger"], trip, 2)
    assert tick(client.app.state.context)["failed"] == 0
    client.app.state.context.clock.offset += 24 * 3600 + 1
    assert tick(client.app.state.context)["failed"] == 0
    assert trip_status(client, trip["id"]) == "TOPUP_OFFERED"
    login_as(client, accounts["passenger"])
    offer = client.get("/api/intercity/topup-offers").json()[0]
    assert offer["amount_vnd"] == 236000
    response = mutate(
        client, f"/api/intercity/topup-offers/{offer['id']}/respond", {"decision": "ACCEPT"}
    )
    assert response.status_code == 200, response.text
    assert tick(client.app.state.context)["failed"] == 0
    assert trip_status(client, trip["id"]) == "CONFIRMED_TOPUP"
    updated = client.get(f"/api/bookings/{booking['id']}").json()
    assert updated["final_price_vnd"] == 636000 and updated["price_status"] == "TOPUP_LOCKED"


def test_declined_topup_deadline_full_refund(client: TestClient, accounts: dict) -> None:
    trip = publish(client, accounts)
    booking = book_pool(client, accounts["passenger"], trip)
    tick(client.app.state.context)
    client.app.state.context.clock.offset += 24 * 3600 + 1
    tick(client.app.state.context)
    login_as(client, accounts["passenger"])
    offer = client.get("/api/intercity/topup-offers").json()[0]
    assert (
        mutate(
            client, f"/api/intercity/topup-offers/{offer['id']}/respond", {"decision": "DECLINE"}
        ).status_code
        == 200
    )
    client.app.state.context.clock.offset += 12 * 3600
    result = tick(client.app.state.context)
    assert result["failed"] == 0
    assert trip_status(client, trip["id"]) == "CANCELLED_LOW_DEMAND"
    detail = client.get(f"/api/bookings/{booking['id']}/price-breakdown").json()
    assert detail["escrow"]["refunded_vnd"] == 200000


def test_late_booking_rejected_after_close(client: TestClient, accounts: dict) -> None:
    publish(client, accounts)
    client.app.state.context.clock.offset += 24 * 3600 + 120
    login_as(client, accounts["passenger"])
    departure = datetime.fromtimestamp(client.app.state.context.clock.now() + 71 * 3600, UTC)
    request = mutate(
        client,
        "/api/trip-requests",
        intent(
            dropoff={"lat": 20.646, "lon": 106.051},
            booking_type="SCHEDULED",
            preferred_departure=departure.isoformat(),
            earliest_departure=(departure - timedelta(minutes=30)).isoformat(),
            latest_departure=(departure + timedelta(minutes=30)).isoformat(),
        ),
    ).json()
    assert "CAR_INTERCITY_POOL" not in request["allowed_service_codes"]
    assert "CAR_INTERCITY_PRIVATE" in request["allowed_service_codes"]


def test_twenty_concurrent_attempts_last_seat_no_oversell(
    client: TestClient, accounts: dict
) -> None:
    trip = publish(client, accounts)
    context = client.app.state.context
    calls = []
    with context.db.transaction() as session:
        target = session.get(ScheduledTrip, trip["id"])
        target.seats_booked = 3
        password = session.get(User, accounts["passenger"]["id"]).password_hash
        departure = datetime.fromisoformat(trip["departure_time"])
        for index in range(20):
            user = User(
                id=uid(),
                email=f"race{index}@test.example",
                name="race",
                password_hash=password,
                role="PASSENGER",
                gender="UNKNOWN",
                created_at=context.clock.now(),
            )
            session.add(user)
            session.flush()
            request = TripRequest(
                id=uid(),
                user_id=user.id,
                mode="INTERCITY",
                created_at=context.clock.now(),
                allowed=["CAR_INTERCITY_POOL"],
                rejections={},
                data={
                    **intent(
                        dropoff={"lat": 20.646, "lon": 106.051},
                        booking_type="SCHEDULED",
                        passenger_count=1,
                    ),
                    "preferred_departure": departure.isoformat(),
                    "earliest_departure": (departure - timedelta(minutes=30)).isoformat(),
                    "latest_departure": (departure + timedelta(minutes=30)).isoformat(),
                    "max_passenger_detour_ratio": 0.3,
                    "same_gender_coride": False,
                    "max_walk_m": 0,
                    "is_raining": False,
                    "has_luggage": False,
                    "car_direct_km": 65,
                    "car_direct_min": 95,
                    "max_in_vehicle_time_min": None,
                    "verified_gender": "UNKNOWN",
                },
            )
            session.add(request)
            session.flush()
            candidate = Candidate(
                id=uid(),
                request_id=request.id,
                run_id=uid(),
                service_code="CAR_INTERCITY_POOL",
                target_id=trip["id"],
                source_type="SCHEDULED_INTERCITY_TRIP",
                source_plan_version=target.plan_version,
                pricing_version=baseline()["pricing_version"],
                expires_at=context.clock.now() + 120,
                data={"unmatched": 200000, "quote": 200000, "matched_estimate": 200000},
            )
            session.add(candidate)
            calls.append((user.id, candidate.run_id, candidate.id))
    barrier = Barrier(20)

    def attempt(args: tuple[str, str, str]) -> str:
        barrier.wait()
        try:
            with context.db.transaction() as session:
                choose(session, context, session.get(User, args[0]), args[1], args[2])
            return "SUCCESS"
        except DomainError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(attempt, calls))
    assert results.count("SUCCESS") == 1, results
    assert set(results) <= {"SUCCESS", "STALE_CANDIDATE", "INSUFFICIENT_SEATS"}
    with context.db.transaction() as session:
        assert session.get(ScheduledTrip, trip["id"]).seats_booked == 4
        assert session.scalar(select(func.count()).select_from(Booking)) == 1
