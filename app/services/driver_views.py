"""Driver-only views: operational locations and explicitly conditional estimates."""

from datetime import UTC, datetime
from fractions import Fraction
from typing import Any

from sqlalchemy.orm import Session

from app.context import Context
from app.domain.locations import location_view
from app.domain.pricing import settlement
from app.models import Booking, Candidate, Offer, Plan, TripRequest


def offer_view(session: Session, context: Context, offer: Offer) -> dict[str, Any]:
    booking = session.get(Booking, offer.booking_id)
    request = session.get(TripRequest, booking.request_id)
    plan = session.get(Plan, offer.plan_id)
    candidate = session.get(Candidate, booking.data.get("candidate_id"))
    detail = candidate.data if candidate else {}
    duration = float(detail.get("duration_min") or request.data["car_direct_min"])
    pool = booking.service_code == "CAR_URBAN_POOL"
    charge = booking.current_estimated_price_vnd if pool else booking.quoted_price_cap_vnd
    estimated = settlement(
        booking.service_code, charge, "MATCHED_LOCKED" if pool else "FIXED_LOCKED"
    )
    pickup = max(context.clock.now(), plan.data["pickup_time"])
    return {
        "id": offer.id,
        "booking_id": booking.id,
        "ride_plan_id": offer.plan_id,
        "status": offer.status,
        "service_code": booking.service_code,
        "expires_at": datetime.fromtimestamp(offer.expires_at, UTC).isoformat(),
        "attempt": offer.attempt,
        "pickup": location_view(request.data["pickup"], request.data.get("pickup_label")),
        "dropoff": location_view(request.data["dropoff"], request.data.get("dropoff_label")),
        "seat_count": booking.seat_count,
        "pickup_time": datetime.fromtimestamp(pickup, UTC).isoformat(),
        "pickup_eta_min": round((pickup - context.clock.now()) / 60, 1),
        "duration_min": duration,
        "distance_km": detail.get("distance_km", request.data["car_direct_km"]),
        "estimated_driver_payout_vnd": estimated["driver_total"],
        "estimated_driver_hourly_vnd": int(
            Fraction(estimated["driver_total"] * 60) / Fraction(str(duration))
        )
        if duration > 0
        else None,
        "estimate_basis": "IF_MATCHED" if pool else "FIXED_FARE",
        "unmatched_driver_payout_vnd": settlement(
            booking.service_code,
            booking.quoted_price_cap_vnd,
            "UNMATCHED_LOCKED",
            booking.data.get("private_fare_vnd", 0),
        )["driver_total"]
        if pool
        else None,
    }
