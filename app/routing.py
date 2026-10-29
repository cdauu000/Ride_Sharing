"""Two-profile OSRM adapter and explicit deterministic development fixtures."""

import hashlib
import json
import math
import time
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.domain.errors import DomainError
from app.domain.types import Leg, Point


def haversine(a: Point, b: Point) -> float:
    lat1, lat2 = math.radians(a.lat), math.radians(b.lat)
    delta = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(math.radians(b.lon - a.lon) / 2) ** 2
    )
    return 6371.0088 * 2 * math.asin(min(1, math.sqrt(delta)))


@dataclass(frozen=True)
class Matrix:
    points: tuple[Point, ...]
    legs: tuple[tuple[Leg | None, ...], ...]

    def leg(self, a: Point, b: Point) -> Leg:
        result = self.legs[self.points.index(a)][self.points.index(b)]
        if result is None:
            raise DomainError("NO_ROUTE", status=422)
        return result


class RoutingProvider(Protocol):
    mode: str

    def matrix(self, profile: str, points: list[Point]) -> Matrix: ...

    def route(self, profile: str, origin: Point, destination: Point) -> Leg: ...


PHENIKAA = Point(20.9610, 105.7470)
LA_PHU = Point(20.9830, 105.7310)
NGUYEN_TRAI = Point(20.9950, 105.8070)
DONG_DA = Point(21.0130, 105.8240)
HUNG_YEN = Point(20.6460, 106.0510)


class FixtureRouting:
    """Illustrative distances. Never represented as an OSM/OSRM measurement."""

    mode = "fixture"

    def route(self, profile: str, origin: Point, destination: Point) -> Leg:
        if origin == destination:
            return Leg(0, 0)
        known = {
            (PHENIKAA, DONG_DA): Leg(14, 35 if profile == "motorbike" else 40),
            (LA_PHU, NGUYEN_TRAI): Leg(9, 28),
            (PHENIKAA, LA_PHU): Leg(5, 12),
            (NGUYEN_TRAI, DONG_DA): Leg(3.5, 10),
            (PHENIKAA, HUNG_YEN): Leg(65, 95),
        }
        if (origin, destination) in known:
            return known[origin, destination]
        km = haversine(origin, destination) * 1.3
        return Leg(round(km, 6), round(km * (2.5 if profile == "motorbike" else 2.9), 6))

    def matrix(self, profile: str, points: list[Point]) -> Matrix:
        unique = tuple(dict.fromkeys(points))
        return Matrix(
            unique, tuple(tuple(self.route(profile, a, b) for b in unique) for a in unique)
        )


class OsrmRouting:
    mode = "osrm"

    def __init__(self, car_url: str, bike_url: str, redis_url: str | None = None) -> None:
        self.urls = {"car": car_url.rstrip("/"), "motorbike": bike_url.rstrip("/")}
        self.client = httpx.Client(timeout=5)
        self.cache = None
        if redis_url:
            from redis import Redis

            self.cache = Redis.from_url(redis_url, socket_timeout=1)

    def matrix(self, profile: str, points: list[Point]) -> Matrix:
        unique = tuple(dict.fromkeys(points))
        if not unique or len(unique) > 200:
            raise DomainError("INVALID_MATRIX_SIZE", status=422)
        coordinates = ";".join(f"{p.lon:.7f},{p.lat:.7f}" for p in unique)
        key = (
            "routing:v1:"
            + hashlib.sha256(
                f"{profile}:{coordinates}:{int(time.time()) // 900}".encode()
            ).hexdigest()
        )
        cached = self.cache.get(key) if self.cache else None
        try:
            if cached:
                data = json.loads(cached)
            else:
                response = self.client.get(
                    f"{self.urls[profile]}/table/v1/driving/{coordinates}",
                    params={"annotations": "distance,duration"},
                )
                response.raise_for_status()
                data = response.json()
                if data.get("code") != "Ok":
                    raise DomainError("NO_ROUTE", status=422)
                if self.cache:
                    self.cache.setex(key, 300, json.dumps(data))
            legs = tuple(
                tuple(
                    None
                    if distance is None or duration is None
                    else Leg(distance / 1000, duration / 60)
                    for distance, duration in zip(ds, ts, strict=True)
                )
                for ds, ts in zip(data["distances"], data["durations"], strict=True)
            )
            return Matrix(unique, legs)
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise DomainError("ROUTING_UNAVAILABLE", "Không lấy được lộ trình OSRM.", 503) from exc

    def route(self, profile: str, origin: Point, destination: Point) -> Leg:
        return self.matrix(profile, [origin, destination]).leg(origin, destination)
