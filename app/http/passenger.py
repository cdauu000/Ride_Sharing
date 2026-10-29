from typing import Any

from fastapi import APIRouter
from sqlalchemy import select

from app.domain.errors import DomainError
from app.http.dependencies import Actor, Ctx, Db, Key
from app.models import (
    Booking,
    Driver,
    Payout,
    TripRequest,
)
from app.schemas import (
    SelectCandidate,
    TripIntent,
)
from app.security import require_role
from app.services import booking as booking_service
from app.services import ride
from app.services.candidate import generate
from app.services.common import booking_view, idempotent, owned_booking
from app.services.trip import create_request

router = APIRouter()


@router.post("/trip-requests", response_model=dict[str, Any], status_code=201)
def new_request(
    payload: TripIntent, session: Db, context: Ctx, user: Actor, key: Key = None
) -> dict:
    require_role(user, "PASSENGER")

    def action() -> dict:
        row = create_request(session, context, user, payload)
        return {
            "id": row.id,
            "mode": row.mode,
            "allowed_service_codes": row.allowed,
            "rejection_reasons": row.rejections,
        }

    return idempotent(
        session, context, user, key, "POST /trip-requests", payload.model_dump(mode="json"), action
    )


@router.get("/trip-requests/{request_id}/recommendations", response_model=dict[str, Any])
def recommendations(request_id: str, session: Db, context: Ctx, user: Actor) -> dict:
    row = session.get(TripRequest, request_id)
    if row is None or row.user_id != user.id:
        raise DomainError("NOT_FOUND", status=404)
    return generate(session, context, row)


@router.post("/recommendations/{run_id}/select", response_model=dict[str, Any])
def select_candidate(
    run_id: str, payload: SelectCandidate, session: Db, context: Ctx, user: Actor, key: Key = None
) -> dict:
    require_role(user, "PASSENGER")
    return idempotent(
        session,
        context,
        user,
        key,
        f"POST /recommendations/{run_id}/select",
        payload.model_dump(),
        lambda: booking_service.choose(session, context, user, run_id, payload.candidate_id),
    )


@router.get("/bookings", response_model=list[dict[str, Any]])
def bookings(session: Db, user: Actor) -> list[dict]:
    return [
        booking_view(session, b)
        for b in session.scalars(
            select(Booking)
            .where(Booking.user_id == user.id)
            .order_by(Booking.created_at.desc())
            .limit(100)
        )
    ]


@router.get("/bookings/{booking_id}", response_model=dict[str, Any])
def get_booking(booking_id: str, session: Db, user: Actor) -> dict:
    return booking_view(session, owned_booking(session, user, booking_id))


@router.get("/bookings/{booking_id}/tracking", response_model=dict[str, Any])
def tracking(booking_id: str, session: Db, user: Actor) -> dict:
    row = owned_booking(session, user, booking_id)
    trip = session.get(TripRequest, row.request_id)
    driver = session.get(Driver, row.driver_id) if row.driver_id else None
    return {
        "pickup": trip.data["pickup"],
        "dropoff": trip.data["dropoff"],
        "ride_status": row.ride_status,
        "driver_position": {"lat": driver.lat, "lon": driver.lon}
        if driver and row.ride_status in {"CONFIRMED", "RIDE_STARTED"}
        else None,
    }


@router.get("/bookings/{booking_id}/price-breakdown", response_model=dict[str, Any])
def breakdown(booking_id: str, session: Db, user: Actor) -> dict:
    row = owned_booking(session, user, booking_id)
    payout = session.get(Payout, row.id)
    return {
        "private_fare_vnd": row.data.get("private_fare_vnd", 0),
        "pricing_version": row.pricing_version,
        "pool_quote_price_vnd": row.pool_quote_price_vnd,
        "quoted_price_cap_vnd": row.quoted_price_cap_vnd,
        "current_estimated_price_vnd": row.current_estimated_price_vnd,
        "final_price_vnd": row.final_price_vnd,
        "fare": row.data.get("fare"),
        "settlement": payout.data if payout else None,
        "cancellation_split": row.data.get("cancellation_split"),
        "escrow": row.data.get("escrow"),
        "unmatched_cause": row.unmatched_cause,
    }


@router.post("/bookings/{booking_id}/cancel", response_model=dict[str, Any])
def cancel(booking_id: str, session: Db, context: Ctx, user: Actor, key: Key = None) -> dict:
    return idempotent(
        session,
        context,
        user,
        key,
        f"POST /bookings/{booking_id}/cancel",
        {},
        lambda: ride.cancel_booking(session, context, user, booking_id),
    )
