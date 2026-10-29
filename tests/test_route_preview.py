import copy
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.domain.errors import DomainError
from app.route_preview import RoadPreview
from app.schemas import Coordinate
from tests.conftest import login_as

A = Coordinate(lat=21.03881, lon=105.78189)
B = Coordinate(lat=20.968238, lon=105.786924)


def response() -> dict[str, Any]:
    return {
        "code": "Ok",
        "routes": [
            {
                "distance": 9291,
                "duration": 890.2,
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[A.lon, A.lat], [105.8, 21.0], [B.lon, B.lat]],
                },
            }
        ],
        "waypoints": [
            {"location": [A.lon, A.lat], "distance": 28.7},
            {"location": [B.lon, B.lat], "distance": 21.4},
        ],
    }


def test_road_distance_is_meters_and_geometry_preserves_lon_lat_order() -> None:
    calls = []

    def reply(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=response())

    service = RoadPreview("https://road.test/routed-car", transport=httpx.MockTransport(reply))
    result = service.route(A, B, "one")
    assert result["distance_m"] == 9291 and result["duration_s"] == 890.2
    assert result["geometry"]["coordinates"][0] == [A.lon, A.lat]
    assert result["waypoints"][0]["distance_m"] == 28.7
    assert calls[0].url.path.endswith("105.781890,21.038810;105.786924,20.968238")
    assert calls[0].url.params["geometries"] == "geojson" and "cookie" not in calls[0].headers
    result["geometry"]["coordinates"].clear()
    assert service.route(A, B, "two")["geometry"]["coordinates"]
    assert len(calls) == 1
    with pytest.raises(DomainError, match="ROUTE_PREVIEW_BUSY"):
        service.route(B, A, "one")


@pytest.mark.parametrize("change", ["nan", "geometry", "waypoints", "type", "negative", "empty"])
def test_malformed_upstream_is_not_a_successful_or_fixture_route(change: str) -> None:
    data = response()
    if change == "nan":
        data["routes"][0]["duration"] = "nan"
    if change == "geometry":
        data["routes"][0]["geometry"]["coordinates"][0][0] = 999
    if change == "waypoints":
        data["waypoints"] = []
    if change == "type":
        data["routes"][0]["geometry"]["type"] = "Point"
    if change == "negative":
        data["routes"][0]["distance"] = -10
    if change == "empty":
        data["routes"] = []
    service = RoadPreview(
        "https://road.test", transport=httpx.MockTransport(lambda _: httpx.Response(200, json=data))
    )
    with pytest.raises(DomainError, match="ROUTE_PREVIEW_UNAVAILABLE"):
        service.route(A, B, "one")


@pytest.mark.parametrize("code", ["NoRoute", "NoSegment", "far"])
def test_no_route_or_far_snapping_does_not_invent_distance(code: str) -> None:
    data = response()
    if code == "far":
        data["waypoints"][0]["distance"] = 1001
    else:
        data = {"code": code}
    service = RoadPreview(
        "https://road.test", transport=httpx.MockTransport(lambda _: httpx.Response(200, json=data))
    )
    with pytest.raises(DomainError, match="ROUTE_NOT_FOUND"):
        service.route(A, B, "one")


def test_cache_expires_and_failed_request_releases_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    now, calls = [100.0], []
    monkeypatch.setattr("app.route_preview.time.monotonic", lambda: now[0])

    def reply(_: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(503) if len(calls) == 1 else httpx.Response(200, json=response())

    service = RoadPreview("https://road.test", transport=httpx.MockTransport(reply))
    with pytest.raises(DomainError, match="UNAVAILABLE"):
        service.route(A, B, "one")
    now[0] += 2
    service.route(A, B, "one")
    service.route(A, B, "one")
    assert len(calls) == 2
    now[0] += 901
    service.route(A, B, "one")
    assert len(calls) == 3


def test_route_api_requires_session_valid_coordinates_and_fixed_endpoint(
    client: TestClient, accounts: dict
) -> None:
    payload = {"pickup": A.model_dump(), "dropoff": B.model_dump()}
    assert client.post("/api/locations/route", json=payload).status_code == 401
    login_as(client, accounts["passenger"])
    client.app.state.context.road_preview = RoadPreview(
        "https://road.test",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=response())),
    )
    assert (
        client.post("/api/locations/route", json={**payload, "url": "http://localhost"}).status_code
        == 422
    )
    invalid = copy.deepcopy(payload)
    invalid["pickup"]["lat"] = 91
    assert client.post("/api/locations/route", json=invalid).status_code == 422
    assert (
        client.post(
            "/api/locations/route", json={"pickup": A.model_dump(), "dropoff": A.model_dump()}
        ).status_code
        == 422
    )
    result = client.post("/api/locations/route", json=payload)
    assert result.status_code == 200 and result.json()["distance_m"] == 9291
    busy = client.post(
        "/api/locations/route", json={"pickup": B.model_dump(), "dropoff": A.model_dump()}
    )
    assert busy.status_code == 429 and int(busy.headers["Retry-After"]) >= 1
