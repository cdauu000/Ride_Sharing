from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import ROOT
from app.domain.errors import DomainError
from app.geocoding import PhotonGeocoder
from app.place_catalog import PlaceCatalog
from tests.conftest import login_as


def feature(**properties: Any) -> dict[str, Any]:
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [105.78189, 21.03881]},
        "properties": {
            "osm_type": "R",
            "osm_id": 123,
            "countrycode": "VN",
            "name": "Đại học Quốc gia",
            "housenumber": "144",
            "street": "Xuân Thủy",
            "city": "Hà Nội",
            **properties,
        },
    }


def geocoder(handler: Any) -> PhotonGeocoder:
    return PhotonGeocoder("https://photon.test/api/", transport=httpx.MockTransport(handler))


@pytest.mark.parametrize(
    "query",
    [
        "Jacal Hotel",
        "Jacayl Hotel Hà Đông",
        "138 Phùng Hưng Hà Nội",
        "Jacal Hotel ở 138 Phùng Hưng",
    ],
)
def test_missing_hotel_aliases_use_auditable_reference_not_fuzzy_nearby_house(query: str) -> None:
    service = PhotonGeocoder(
        "https://unused.test",
        catalog=PlaceCatalog(str(ROOT / "config/local_places.json")),
        transport=httpx.MockTransport(
            lambda _: pytest.fail("Local POI must work without upstream")
        ),
    )
    result = service.search(query, "one")
    assert len(result) == 1 and "138 Phùng Hưng" in result[0]["label"]
    assert result[0]["lat"] == 20.968238 and result[0]["lon"] == 105.786924
    assert result[0]["precision"] == "reference" and result[0]["source"].startswith("https://")


@pytest.mark.parametrize(
    "query", ["139 Phùng Hưng", "Jacal Hotel 138 Phùng Hưng Hoàn Kiếm", "Jacayl Hotel Đà Nẵng"]
)
def test_catalog_does_not_override_conflicting_number_or_location(query: str) -> None:
    assert PlaceCatalog(str(ROOT / "config/local_places.json")).search(query) == []


def test_fuzzy_wrong_house_street_or_unrelated_hotel_is_rejected() -> None:
    features = [
        feature(housenumber="135", street="Phùng Hưng"),
        feature(housenumber="138", street="Xuân Thủy"),
        feature(name="Hotel An Hưng", housenumber="2", street="Phạm Tuấn Tài"),
    ]
    assert PhotonGeocoder._places(features, "138 Phùng Hưng Hà Nội") == []
    assert PhotonGeocoder._places(features, "Jacal Hotel Hà Nội") == []


def test_numbered_street_is_not_mistaken_for_a_requested_house_number() -> None:
    data = feature(name="Đường 32", housenumber="", street="Đường 32", type="street")
    result = PhotonGeocoder._places([data], "Đường 32 Hà Nội")
    assert len(result) == 1 and result[0]["kind"] == "street"


def test_address_with_alley_house_number_keeps_slash_when_matching() -> None:
    assert (
        len(PhotonGeocoder._places([feature(housenumber="144/2")], "144/2 Xuân Thủy Hà Nội")) == 1
    )
    assert PhotonGeocoder._places([feature(housenumber="144/3")], "144/2 Xuân Thủy Hà Nội") == []


def test_search_maps_real_address_and_caches_unicode_equivalent_queries() -> None:
    calls = []

    def reply(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"features": [feature(), feature(countrycode="CN")]})

    service = geocoder(reply)
    result = service.search("144 Xuân Thủy, Hà Nội", "one")
    assert len(result) == 1
    assert result[0]["lat"] == 21.03881 and result[0]["lon"] == 105.78189
    assert "144 Xuân Thủy" in result[0]["label"] and result[0]["kind"] == "address"
    assert calls[0].url.params["countrycode"] == "VN"
    assert "RiseSharing" in calls[0].headers["User-Agent"]
    assert "cookie" not in calls[0].headers
    assert service.search("  144   XUÂN THỦY, HÀ NỘI ", "two") == result
    assert len(calls) == 1


def test_no_results_does_not_invent_a_coordinate() -> None:
    service = geocoder(lambda _: httpx.Response(200, json={"features": []}))
    assert service.search("Không có địa chỉ này", "one") == []


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(503),
        httpx.Response(200, json={"features": "invalid"}),
        httpx.Response(200, text="not json"),
    ],
)
def test_provider_failures_are_safe_and_not_reported_as_empty_success(
    response: httpx.Response,
) -> None:
    service = geocoder(lambda _: response)
    with pytest.raises(DomainError, match="GEOCODER_UNAVAILABLE"):
        service.search("144 Xuân Thủy Hà Nội", "one")


def test_invalid_coordinates_and_foreign_features_are_dropped() -> None:
    invalid = feature()
    invalid["geometry"]["coordinates"] = [999, 21]
    service = geocoder(
        lambda _: httpx.Response(
            200, json={"features": [invalid, feature(countrycode="DE"), feature(housenumber="")]}
        )
    )
    result = service.search("Xuân Thủy Hà Nội", "one")
    assert len(result) == 1 and result[0]["kind"] == "place"


def test_global_request_spacing_allows_cache_but_throttles_new_queries() -> None:
    service = geocoder(lambda _: httpx.Response(200, json={"features": []}))
    service.search("Xuân Thủy Hà Nội", "one")
    assert service.search("Xuân Thủy Hà Nội", "two") == []
    with pytest.raises(DomainError, match="GEOCODER_BUSY"):
        service.search("Nguyễn Trãi Hà Nội", "two")


def test_expired_cache_is_refreshed_and_does_not_reuse_old_coordinates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = [100.0]
    monkeypatch.setattr("app.geocoding.time.monotonic", lambda: now[0])
    calls = []

    def reply(_: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json={"features": [feature()]})

    service = geocoder(reply)
    service.search("144 Xuân Thủy Hà Nội", "one")
    service.search("144 Xuân Thủy Hà Nội", "one")
    assert len(calls) == 1
    now[0] += 3601
    service.search("144 Xuân Thủy Hà Nội", "one")
    assert len(calls) == 2


def test_cached_queries_still_respect_personal_abuse_limit() -> None:
    service = geocoder(lambda _: httpx.Response(200, json={"features": []}))
    for _ in range(20):
        assert service.search("144 Xuân Thủy Hà Nội", "one") == []
    with pytest.raises(DomainError, match="GEOCODER_BUSY"):
        service.search("144 Xuân Thủy Hà Nội", "one")


def test_search_requires_session_validates_input_and_never_accepts_upstream_url(
    client: TestClient, accounts: dict
) -> None:
    assert (
        client.post("/api/locations/search", json={"query": "144 Xuân Thủy Hà Nội"}).status_code
        == 401
    )
    login_as(client, accounts["passenger"])
    for payload in (
        {"query": "  "},
        {"query": "x" * 251},
        {"query": "address", "url": "http://127.0.0.1"},
    ):
        assert client.post("/api/locations/search", json=payload).status_code == 422
    client.app.state.context.geocoding = geocoder(
        lambda _: httpx.Response(200, json={"features": [feature()]})
    )
    result = client.post("/api/locations/search", json={"query": "144 Xuân Thủy Hà Nội"})
    assert result.status_code == 200 and result.json()["items"][0]["kind"] == "address"
    busy = client.post("/api/locations/search", json={"query": "Nguyễn Trãi Hà Nội"})
    assert busy.status_code == 429 and int(busy.headers["Retry-After"]) >= 1
