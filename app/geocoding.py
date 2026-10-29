"""Explicit, authenticated address searches; no per-keystroke public requests."""

import hashlib
import json
import math
import threading
import time
import unicodedata
from collections import OrderedDict
from typing import Any

import httpx

from app.domain.errors import DomainError
from app.place_catalog import PlaceCatalog, relevant_address
from app.rate_limit import RateLimiter


class GeocoderBusy(DomainError):
    def __init__(self, retry_after: int = 1) -> None:
        super().__init__("GEOCODER_BUSY", status=429)
        self.retry_after = retry_after


class PhotonGeocoder:
    def __init__(
        self,
        url: str,
        redis_url: str | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
        catalog: PlaceCatalog | None = None,
    ) -> None:
        self.url = url
        self.catalog = catalog
        self.transport = transport
        self.lock = threading.Lock()
        self.inflight = False
        self.last_start = -math.inf
        self.cache: OrderedDict[str, tuple[float, list[dict[str, Any]]]] = OrderedDict()
        self.redis: Any = None
        if redis_url:
            from redis import Redis

            self.redis = Redis.from_url(redis_url, socket_timeout=1)
        self.requests = RateLimiter(self.redis)

    def search(self, query: str, user_id: str) -> list[dict[str, Any]]:
        normalized = " ".join(unicodedata.normalize("NFKC", query).split())
        key = "geocode:v2:" + hashlib.sha256(normalized.casefold().encode()).hexdigest()
        try:
            retry_after = self.requests.take(f"geocode-person:{user_id}", 20)
            if retry_after:
                raise GeocoderBusy(retry_after)
            local = self.catalog.search(normalized) if self.catalog else []
            if local:
                return local
            if self.redis:
                cached = self.redis.get(key)
                if cached is not None:
                    return json.loads(cached)
            with self.lock:
                now = time.monotonic()
                cached = self.cache.get(key)
                if cached and cached[0] > now:
                    self.cache.move_to_end(key)
                    return [dict(item) for item in cached[1]]
                if self.inflight or now - self.last_start < 1.1:
                    raise GeocoderBusy()
                if self.redis and not self.redis.set("geocode:request-slot", "1", nx=True, px=1100):
                    raise GeocoderBusy()
                self.inflight = True
                self.last_start = now
            try:
                # The caller never controls the endpoint, headers or redirects.
                with httpx.Client(
                    timeout=8, follow_redirects=False, transport=self.transport
                ) as client:
                    response = client.get(
                        self.url,
                        params={"q": normalized, "countrycode": "VN", "limit": 8},
                        headers={
                            "User-Agent": "RiseSharing-AddressSearch/0.1 (local research application)"
                        },
                    )
                    response.raise_for_status()
                    data = response.json()
                if not isinstance(data, dict) or not isinstance(data.get("features"), list):
                    raise ValueError("Invalid geocoding response")
                items = self._places(data["features"], normalized)
                if self.redis:
                    self.redis.set(key, json.dumps(items), ex=3600)
                with self.lock:
                    self.cache[key] = (time.monotonic() + 3600, items)
                    self.cache.move_to_end(key)
                    while len(self.cache) > 256:
                        self.cache.popitem(last=False)
                return [dict(item) for item in items]
            finally:
                with self.lock:
                    self.inflight = False
        except DomainError:
            raise
        except Exception as exc:
            # Do not return upstream URLs, query strings or connection details.
            raise DomainError("GEOCODER_UNAVAILABLE", status=503) from exc

    @staticmethod
    def _places(features: list[Any], query: str = "") -> list[dict[str, Any]]:
        result, seen = [], set()
        for feature in features[:40]:
            if not isinstance(feature, dict):
                continue
            properties, geometry = feature.get("properties"), feature.get("geometry")
            if not isinstance(properties, dict) or not isinstance(geometry, dict):
                continue
            if not relevant_address(query, properties):
                continue
            if (
                str(properties.get("countrycode", "")).upper() != "VN"
                or geometry.get("type") != "Point"
            ):
                continue
            try:
                lon, lat = (float(value) for value in geometry["coordinates"])
            except (KeyError, TypeError, ValueError):
                continue
            if (
                not math.isfinite(lat)
                or not math.isfinite(lon)
                or not (-90 <= lat <= 90 and -180 <= lon <= 180)
            ):
                continue

            def text(name: str, values: dict[str, Any] = properties) -> str:
                value = values.get(name)
                return " ".join(value.split())[:200] if isinstance(value, str) else ""

            street = " ".join(filter(None, [text("housenumber"), text("street")]))
            parts = list(
                dict.fromkeys(
                    part
                    for part in [
                        text("name"),
                        street,
                        text("locality"),
                        text("district"),
                        text("city"),
                        text("state"),
                        text("country"),
                    ]
                    if part
                )
            )
            label = ", ".join(parts)[:500]
            identity = (lat, lon, label)
            if not label or identity in seen:
                continue
            seen.add(identity)
            result.append(
                {
                    "id": hashlib.sha256(repr(identity).encode()).hexdigest()[:20],
                    "lat": lat,
                    "lon": lon,
                    "label": label,
                    "kind": "address"
                    if text("housenumber")
                    else "street"
                    if properties.get("type") == "street"
                    else "place",
                }
            )
            if len(result) == 8:
                break
        return result
