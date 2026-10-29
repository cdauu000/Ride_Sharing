from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.trips import pickup_window
from app.models import Booking, TripRequest


def observed_features(
    session: Session, request: TripRequest, items: list[dict], now: float
) -> list[dict[str, Any]]:
    data = request.data
    prior = list(
        session.scalars(
            select(Booking).where(
                Booking.user_id == request.user_id,
                Booking.ride_status == "COMPLETED",
                Booking.created_at < now,
            )
        )
    )
    prior = [b for b in prior if b.data.get("completed_at", float("inf")) < now]
    recent = (
        session.scalar(
            select(__import__("sqlalchemy").func.count())
            .select_from(TripRequest)
            .where(TripRequest.created_at < now, TripRequest.created_at >= now - 900)
        )
        or 0
    )
    stamp = datetime.fromtimestamp(now, UTC)
    local = stamp.astimezone(__import__("zoneinfo").ZoneInfo("Asia/Ho_Chi_Minh"))
    rows = []
    for item in items:
        earliest, latest, preferred = pickup_window(data, item["service_code"], request.created_at)
        code = item["service_code"]
        rows.append(
            {
                "request_id": request.id,
                "candidate_id": item["id"],
                "timestamp_utc": stamp.isoformat(),
                "user_id": request.user_id,
                "service_code": code,
                "mode": request.mode,
                "booking_type": data["booking_type"],
                "candidate_source_type": item["source_type"],
                "is_raining": int(data["is_raining"]),
                "has_luggage": int(data["has_luggage"]),
                "hour_of_day": local.hour,
                "day_of_week": local.weekday(),
                "origin_zone_id": f"{data['pickup']['lat']:.2f},{data['pickup']['lon']:.2f}",
                "dest_zone_id": f"{data['dropoff']['lat']:.2f},{data['dropoff']['lon']:.2f}",
                "direct_distance_km": item["distance_km"],
                "direct_duration_min": data["car_direct_min"],
                "passenger_count": data["passenger_count"],
                "pickup_window_width_min": (latest - earliest) / 60,
                "budget_min": data["budget_min"],
                "budget_max": data["budget_max"],
                "lead_time_hours": max(0, (preferred - now) / 3600),
                "max_passenger_detour_ratio": data["max_passenger_detour_ratio"],
                "max_walk_m": data["max_walk_m"],
                "effective_price_vnd": item["expected_price"],
                "pool_quote_price_vnd": item["quote"],
                "pool_unmatched_price_vnd": item["unmatched"],
                "fare_matched_est_vnd": item["matched_estimate"],
                "planned_pickup_eta_min": item["pickup_eta_min"],
                "schedule_deviation_min": abs(item["pickup_eta_min"] * 60 + now - preferred) / 60,
                "in_vehicle_duration_min": item["duration_min"],
                "detour_ratio": item["detour_ratio"],
                "walk_m": 0,
                "extra_stops_count": item.get("extra_stops_count", 0),
                "driver_rating_bayesian": 4.5,
                "p_match_oof_est": item.get("p_match_est", 0),
                "p_fulfill_oof_est": item.get("p_fulfill_est", 0.9),
                "is_existing_plan": int(item["source_type"] == "EXISTING_POOL_PLAN"),
                "active_pool_requests_15m_in_origin_zone": recent,
                "open_pool_plans_same_direction_in_radius": int(
                    item["source_type"] == "EXISTING_POOL_PLAN"
                ),
                "user_hist_trip_count": len(prior),
                "user_hist_bike_share": sum(b.service_code == "BIKE_URBAN" for b in prior)
                / max(1, len(prior)),
                "user_hist_pool_share": sum("POOL" in b.service_code for b in prior)
                / max(1, len(prior)),
                "user_hist_private_share": sum("PRIVATE" in b.service_code for b in prior)
                / max(1, len(prior)),
                "pricing_version": item["pricing_version"],
            }
        )
    return rows
