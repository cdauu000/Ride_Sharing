from dataclasses import asdict
from fractions import Fraction
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.context import Context
from app.domain.pooling import EvaluatedPlan, PoolPlan, Rider, Stop
from app.domain.pricing import fixed_fare
from app.domain.trips import pickup_window
from app.domain.types import Point, Service
from app.models import Booking, Driver, Plan, TripRequest


def rider_from_request(request: TripRequest, service: str = Service.CAR_URBAN_POOL) -> Rider:
    data = request.data
    earliest, latest, _ = pickup_window(data, service, request.created_at)
    return Rider(
        request.id,
        Point(**data["pickup"]),
        Point(**data["dropoff"]),
        data["passenger_count"],
        earliest,
        latest,
        data["car_direct_km"],
        data["car_direct_min"],
        fixed_fare(Service.CAR_URBAN_PRIVATE, data["car_direct_km"], data["car_direct_min"]),
        data["budget_max"],
        max_detour=data["max_passenger_detour_ratio"],
        max_minutes=data.get("max_in_vehicle_time_min"),
        latest_arrival=__import__("datetime")
        .datetime.fromisoformat(data["latest_arrival"])
        .timestamp()
        if data.get("latest_arrival")
        else None,
        gender=data.get("verified_gender", "UNKNOWN"),
        same_gender=data["same_gender_coride"],
    )


def plan_from_row(session: Session, context: Context, row: Plan) -> PoolPlan:
    driver = session.get(Driver, row.driver_id)
    data = row.data
    riders = []
    for booking in session.scalars(
        select(Booking).where(Booking.ride_plan_id == row.id).order_by(Booking.id)
    ):
        if booking.ride_status.startswith("CANCELLED") or booking.ride_status == "EXPIRED":
            continue
        request = session.get(TripRequest, booking.request_id)
        rider = rider_from_request(request)
        tracking = data.get("tracking", {}).get(request.id, {})
        rider_data = asdict(rider)
        rider_data.update(
            pickup=rider.pickup,
            dropoff=rider.dropoff,
            traveled_km=tracking.get("traveled_km", 0),
            actual_pickup=tracking.get("actual_pickup"),
            old_exact=Fraction(booking.data["fare"]["exact"]) if booking.data.get("fare") else None,
            frozen=booking.price_status == "MATCHED_LOCKED",
            frozen_charged=booking.final_price_vnd,
        )
        riders.append(Rider(**rider_data))
    return PoolPlan(
        Point(**data.get("current", {"lat": driver.lat, "lon": driver.lon})),
        context.clock.now(),
        tuple(riders),
        tuple(Stop(s["rider_id"], s["kind"], Point(**s["point"])) for s in data["stops"]),
        completed_stop_index=data.get("completed_stop_index", -1),
        elapsed_km=data.get("elapsed_km", 0),
        elapsed_minutes=data.get("elapsed_minutes", 0),
        max_driver_detour_km=driver.max_driver_detour_km,
        max_driver_detour_min=driver.max_driver_detour_min,
        max_additional_pickups=driver.max_additional_pickups,
        status=row.status,
    )


def serialize_result(result: EvaluatedPlan) -> dict[str, Any]:
    return {
        "stops": [
            {"rider_id": s.rider_id, "kind": s.kind, "point": asdict(s.point)}
            for s in result.plan.stops
        ],
        "total_km": result.total_km,
        "total_minutes": result.total_minutes,
        "fares": result.fares,
        "detours": result.detours,
        "overlaps": [list(pair) for pair in sorted(result.overlaps)],
        "pickup_times": result.pickup_times,
        "dropoff_times": result.dropoff_times,
    }


def apply_result(session: Session, plan: Plan, result: dict[str, Any]) -> None:
    plan.data = {**plan.data, **result}
    for booking in session.scalars(select(Booking).where(Booking.ride_plan_id == plan.id)):
        if booking.request_id in result["fares"] and booking.price_status == "POOL_SEARCHING":
            fare = result["fares"][booking.request_id]
            booking.data = {**booking.data, "fare": fare}
            booking.current_estimated_price_vnd = fare["charged"]
