import json
from pathlib import Path

from shapely.geometry import Point as GeoPoint
from shapely.geometry import shape

from app.config import baseline
from app.domain.errors import DomainError
from app.domain.types import Point, Service
from app.schemas import TripIntent


class ServiceAreas:
    def __init__(self, path: str) -> None:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.areas = {
            item["properties"]["kind"]: shape(item["geometry"]) for item in data["features"]
        }
        self.status = data.get("metadata", {}).get("status", "UNVERIFIED")

    def classify(self, pickup: Point, dropoff: Point, direct_km: float) -> str:
        points = [GeoPoint(p.lon, p.lat) for p in (pickup, dropoff)]
        if not all(self.areas["total"].covers(p) for p in points) or direct_km > 150:
            raise DomainError("OUT_OF_SERVICE_AREA", status=422)
        inside = [self.areas["urban"].covers(p) for p in points]
        if all(inside) or any(inside) and direct_km <= 15:
            return "URBAN"
        if any(inside):
            return "INTERCITY"
        raise DomainError("UNSUPPORTED_INTER_PROVINCE_ROUTE", status=422)


def allowed_services(intent: TripIntent, mode: str, now: float) -> tuple[list[str], dict[str, str]]:
    lead = (
        (intent.preferred_departure.timestamp() - now) / 3600 if intent.preferred_departure else 0
    )
    accepted, rejected = [], {}
    for service in Service:
        if ("INTERCITY" in service) != (mode == "INTERCITY"):
            reason = "SERVICE_AREA_MISMATCH"
        elif (
            intent.vehicle_preference == "BIKE"
            and service != Service.BIKE_URBAN
            or (intent.vehicle_preference == "CAR" and service == Service.BIKE_URBAN)
        ):
            reason = "VEHICLE_PREFERENCE_MISMATCH"
        elif intent.ride_preference != "ANY" and ("POOL" in service) != (
            intent.ride_preference == "POOL"
        ):
            reason = "RIDE_PREFERENCE_MISMATCH"
        elif service == Service.BIKE_URBAN and (intent.passenger_count != 1 or intent.has_luggage):
            reason = "BIKE_PARTY_OR_LUGGAGE"
        elif service == Service.CAR_URBAN_POOL and intent.passenger_count > 2:
            reason = "URBAN_POOL_MAX_TWO_SEATS"
        elif (
            lead < 0
            or lead > (168 if mode == "INTERCITY" else 12)
            or (service == Service.CAR_INTERCITY_POOL and lead < 72)
        ):
            reason = "SERVICE_REJECTED_LEAD_TIME"
        else:
            accepted.append(str(service))
            continue
        rejected[str(service)] = reason
    return accepted, rejected


def pickup_window(data: dict, service: str, created_at: float) -> tuple[float, float, float]:
    if data["booking_type"] == "NOW":
        cfg = baseline()[
            "bike_urban"
            if service == Service.BIKE_URBAN
            else "car_intercity_private"
            if "INTERCITY" in service
            else "car_urban"
        ]
        start, end = cfg["now_pickup_window_min"]
        return created_at + start * 60, created_at + end * 60, created_at + start * 60
    from datetime import datetime

    return tuple(
        datetime.fromisoformat(data[key]).timestamp()
        for key in ("earliest_departure", "latest_departure", "preferred_departure")
    )
