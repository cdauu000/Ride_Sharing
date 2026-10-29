"""Read-only car road previews. Never substitute fixture distances on failure."""

import copy
import hashlib
import json
import math
import threading
import time
from collections import OrderedDict
from typing import Any

import httpx

from app.domain.errors import DomainError
from app.rate_limit import RateLimiter
from app.schemas import Coordinate


class PreviewBusy(DomainError):
    def __init__(self, retry_after: int = 2) -> None:
        super().__init__("ROUTE_PREVIEW_BUSY", status=429)
        self.retry_after = retry_after


class RoadPreview:
    def __init__(
        self,
        url: str,
        redis_url: str | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.url = url.rstrip("/")
        self.transport = transport
        self.lock = threading.Lock()
        self.last_start = -math.inf
        self.inflight = False
        self.cache: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
        self.redis: Any = None
        if redis_url:
            from redis import Redis

            self.redis = Redis.from_url(redis_url, socket_timeout=1)
        self.requests = RateLimiter(self.redis)

    def route(self, pickup: Coordinate, dropoff: Coordinate, user_id: str) -> dict[str, Any]:
        if pickup == dropoff:
            raise DomainError("SAME_LOCATION", status=422)
        coordinates = f"{pickup.lon:.6f},{pickup.lat:.6f};{dropoff.lon:.6f},{dropoff.lat:.6f}"
        key = "road-preview:v1:" + hashlib.sha256((self.url + coordinates).encode()).hexdigest()
        try:
            retry = self.requests.take(f"road-preview-person:{user_id}", 30)
            if retry:
                raise PreviewBusy(retry)
            if self.redis:
                cached = self.redis.get(key)
                if cached:
                    return json.loads(cached)
            with self.lock:
                now = time.monotonic()
                cached = self.cache.get(key)
                if cached and cached[0] > now:
                    self.cache.move_to_end(key)
                    return copy.deepcopy(cached[1])
                if self.inflight or now - self.last_start < 1.1:
                    raise PreviewBusy()
                if self.redis and not self.redis.set("road-preview:slot", "1", nx=True, px=1100):
                    raise PreviewBusy()
                self.last_start = now
                self.inflight = True
            try:
                with httpx.Client(
                    timeout=12, follow_redirects=False, transport=self.transport
                ) as client:
                    response = client.get(
                        f"{self.url}/route/v1/driving/{coordinates}",
                        params={
                            "overview": "full",
                            "geometries": "geojson",
                            "steps": "false",
                            "generate_hints": "false",
                        },
                        headers={
                            "User-Agent": "RiseSharing-RoadPreview/0.1 (local research application)"
                        },
                    )
                    response.raise_for_status()
                    result = self._parse(response.json())
                if self.redis:
                    self.redis.set(key, json.dumps(result), ex=900)
                with self.lock:
                    self.cache[key] = (time.monotonic() + 900, result)
                    self.cache.move_to_end(key)
                    while len(self.cache) > 256:
                        self.cache.popitem(last=False)
                return copy.deepcopy(result)
            finally:
                with self.lock:
                    self.inflight = False
        except DomainError:
            raise
        except Exception as exc:
            raise DomainError("ROUTE_PREVIEW_UNAVAILABLE", status=503) from exc

    @staticmethod
    def _parse(data: Any) -> dict[str, Any]:
        if isinstance(data, dict) and data.get("code") in ("NoRoute", "NoSegment"):
            raise DomainError("ROUTE_NOT_FOUND", status=422)
        if not isinstance(data, dict) or data.get("code") != "Ok":
            raise ValueError("Invalid route response")
        route = data["routes"][0]
        distance, duration = float(route["distance"]), float(route["duration"])
        if not all(math.isfinite(v) and 0 <= v <= 10_000_000 for v in (distance, duration)):
            raise ValueError("Invalid route measures")
        geometry = route["geometry"]
        if geometry["type"] != "LineString" or not 2 <= len(geometry["coordinates"]) <= 50_000:
            raise ValueError("Invalid route geometry")

        def location(raw: Any) -> list[float]:
            lon, lat = raw
            point = Coordinate(lat=lat, lon=lon)
            return [point.lon, point.lat]

        points = [location(raw) for raw in geometry["coordinates"]]
        waypoints = []
        if len(data["waypoints"]) != 2:
            raise ValueError("Invalid waypoints")
        for waypoint in data["waypoints"]:
            snapped = float(waypoint["distance"])
            if not math.isfinite(snapped) or snapped < 0:
                raise ValueError("Invalid snapping distance")
            if snapped > 1000:
                raise DomainError("ROUTE_NOT_FOUND", status=422)
            waypoints.append({"location": location(waypoint["location"]), "distance_m": snapped})
        return {
            "distance_m": distance,
            "duration_s": duration,
            "geometry": {"type": "LineString", "coordinates": points},
            "waypoints": waypoints,
            "profile": "car",
            "attribution": "© OpenStreetMap contributors · OSRM / FOSSGIS",
        }
