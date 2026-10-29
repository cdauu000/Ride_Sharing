import hashlib
import json
from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.context import Context
from app.domain.errors import DomainError
from app.domain.locations import location_view
from app.models import Booking, Idempotency, Offer, Plan, ScheduledTrip, TripRequest, User
from app.schemas import BookingView

TERMINAL = {
    "COMPLETED",
    "EXPIRED",
    "CANCELLED_BY_PASSENGER",
    "CANCELLED_BY_DRIVER",
    "CANCELLED_BY_SYSTEM",
    "NO_SHOW",
}


def locked(session: Session, cls: type, key: str) -> Any:
    result = session.scalar(
        select(cls).where(cls.id == key).with_for_update().execution_options(populate_existing=True)
    )
    if result is None:
        raise DomainError("NOT_FOUND", status=404)
    return result


def owned_booking(session: Session, user: User, key: str, lock: bool = False) -> Booking:
    booking = session.get(Booking, key)
    if (
        booking is None
        or user.role != "ADMIN"
        and user.id not in (booking.user_id, booking.driver_id)
    ):
        raise DomainError("NOT_FOUND", status=404)
    if lock:
        if booking.ride_plan_id:
            locked(session, Plan, booking.ride_plan_id)
        if booking.scheduled_trip_id:
            locked(session, ScheduledTrip, booking.scheduled_trip_id)
        booking = locked(session, Booking, key)
    return booking


def booking_view(session: Session, booking: Booking) -> dict[str, Any]:
    result = BookingView.model_validate(
        {
            field: getattr(booking, field)
            for field in BookingView.model_fields
            if field not in {"offer_id", "pickup", "dropoff"}
        }
    ).model_dump()
    offer = session.scalar(
        select(Offer).where(Offer.booking_id == booking.id, Offer.status == "PENDING")
    )
    result["offer_id"] = offer.id if offer else None
    request = session.get(TripRequest, booking.request_id)
    result["pickup"] = location_view(request.data["pickup"], request.data.get("pickup_label"))
    result["dropoff"] = location_view(request.data["dropoff"], request.data.get("dropoff_label"))
    return result


def idempotent(
    session: Session,
    context: Context,
    user: User,
    key: str | None,
    route: str,
    payload: dict[str, Any],
    action: Callable[[], dict],
) -> dict:
    if not key or not 8 <= len(key) <= 128:
        raise DomainError("IDEMPOTENCY_KEY_REQUIRED", status=422)
    # Serializes concurrent retries of one account before checking the unique key.
    locked(session, User, user.id)
    digest = hashlib.sha256(
        json.dumps(
            {"route": route, "payload": payload}, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    prior = session.scalar(
        select(Idempotency).where(Idempotency.user_id == user.id, Idempotency.key == key)
    )
    if prior and prior.expires_at > context.clock.now():
        if prior.payload_hash != digest:
            raise DomainError("IDEMPOTENCY_KEY_PAYLOAD_MISMATCH", status=422)
        return prior.response
    if prior:
        session.delete(prior)
        session.flush()
    result = action()
    session.add(
        Idempotency(
            user_id=user.id,
            key=key,
            payload_hash=digest,
            response=result,
            expires_at=context.clock.now() + 86400,
        )
    )
    return result
