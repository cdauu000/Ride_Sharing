"""Regressions from passenger/driver acceptance, including privacy and money."""

from datetime import datetime

import jwt
import pytest
from fastapi.testclient import TestClient

from app.jobs import tick
from app.rate_limit import RateLimiter, principal
from tests.conftest import intent, login_as, mutate
from tests.test_intercity import book_pool, publish


def test_offer_details_scope_deadline_and_income(client: TestClient, accounts: dict) -> None:
    context = client.app.state.context
    login_as(client, accounts["passenger"])
    request = mutate(
        client, "/api/trip-requests", intent(pickup_label="Cổng trường", dropoff_label="Nhà khách")
    ).json()
    menu = client.get(f"/api/trip-requests/{request['id']}/recommendations").json()
    candidate = next(c for c in menu["items"] if c["service_code"] == "CAR_URBAN_PRIVATE")
    assert datetime.fromisoformat(candidate["expires_at"]).timestamp() > context.clock.now()
    booking = mutate(
        client, f"/api/recommendations/{menu['run_id']}/select", {"candidate_id": candidate["id"]}
    ).json()
    assert booking["pickup"]["label"] == "Cổng trường"
    assert client.get("/api/offers").status_code == 403
    login_as(client, accounts["bike"])
    assert client.get("/api/offers").json() == []
    assert client.get(f"/api/bookings/{booking['id']}").status_code == 404
    login_as(client, accounts["driver"])
    offer = client.get("/api/offers").json()[0]
    assert offer["pickup"]["label"] == "Cổng trường"
    assert offer["dropoff"]["label"] == "Nhà khách"
    assert offer["estimated_driver_payout_vnd"] == 155200
    assert offer["estimated_driver_hourly_vnd"] == 232800
    assert offer["duration_min"] == 40
    assert 0 < datetime.fromisoformat(offer["expires_at"]).timestamp() - context.clock.now() <= 20
    context.clock.offset += 21
    assert client.get("/api/offers").json() == []


def test_start_readiness_and_public_location_privacy(client: TestClient, accounts: dict) -> None:
    context = client.app.state.context
    trip = publish(client, accounts)
    booking = book_pool(client, accounts["passenger"], trip, 2)
    book_pool(client, accounts["other"], trip, 1)
    tick(context)
    login_as(client, accounts["passenger"])
    share = mutate(client, f"/api/bookings/{booking['id']}/share-link").json()
    public = client.get(f"/api/shared/{share['token']}").json()
    assert "pickup" not in public and "dropoff" not in public
    login_as(client, accounts["driver"])
    context.clock.offset += 3 * 86400 + 1
    assert tick(context)["failed"] == 0
    rides = client.get("/api/driver/rides").json()
    ride = next(r for r in rides if r["id"] == trip["id"])
    assert ride["status"] == "PICKUP_ORDER_FIXED" and ride["can_start"] is False
    assert all(s["point"]["label"] for s in ride["stops"])
    early = mutate(client, f"/api/rides/{trip['id']}/start")
    assert early.status_code == 409
    context.clock.offset += 86400
    ride = next(r for r in client.get("/api/driver/rides").json() if r["id"] == trip["id"])
    assert ride["can_start"] is True
    assert mutate(client, f"/api/rides/{trip['id']}/start").status_code == 200


def test_shared_ip_read_quota_does_not_block_another_user_or_logout(
    client: TestClient, accounts: dict
) -> None:
    login_as(client, accounts["passenger"])
    # Same browser/IP, but two verified people have independent allowances.
    for _ in range(300):
        response = client.get("/api/system")
        assert response.status_code == 200
    limited = client.get("/api/system")
    assert limited.status_code == 429
    assert 1 <= int(limited.headers["Retry-After"]) <= 60
    login_as(client, accounts["other"])
    assert client.get("/api/system").status_code == 200
    login_as(client, accounts["passenger"])
    assert mutate(client, "/api/auth/logout").status_code == 200


def test_server_clock_header_matches_advanced_demo(client: TestClient) -> None:
    context = client.app.state.context
    context.clock.offset += 5 * 86400
    response = client.get("/api/system")
    assert response.status_code == 200
    assert abs(float(response.headers["X-Server-Time"]) / 1000 - context.clock.now()) < 1


def test_sliding_quota_and_forged_principal(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = [100.0]
    monkeypatch.setattr("app.rate_limit.time.monotonic", lambda: clock[0])
    limiter = RateLimiter()
    assert limiter.take("one", 2) == limiter.take("one", 2) == 0
    assert limiter.take("one", 2) == 60
    assert limiter.take("two", 2) == 0
    clock[0] += 59.1
    assert limiter.take("one", 2) == 1
    clock[0] += 0.9
    assert limiter.take("one", 2) == 0
    claims = {
        "sub": "one",
        "sid": "session",
        "exp": 9999999999,
        "iss": "rise-sharing",
        "aud": "rise-web",
    }
    token = jwt.encode(claims, "test-secret" * 4, algorithm="HS256")
    assert principal(token, "test-secret" * 4) is not None
    assert principal(token, "different-secret" * 4) is None
    assert principal("invalid", "test-secret" * 4) is None
