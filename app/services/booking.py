from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.context import Context, audit, schedule
from app.domain.errors import DomainError
from app.domain.pooling import insert
from app.domain.trips import pickup_window
from app.domain.types import Point, Service
from app.models import (
    Booking,
    Candidate,
    Driver,
    Offer,
    Plan,
    ScheduledTrip,
    SeatHold,
    TripRequest,
    User,
)
from app.services.candidate import driver_available
from app.services.common import booking_view, locked
from app.services.pooling import apply_result, plan_from_row, rider_from_request, serialize_result


def escrow_command(
    session: Session,
    context: Context,
    booking: Booking,
    action: str,
    params: dict[str, Any],
    suffix: str | None = None,
) -> None:
    key = f"escrow:{booking.id}:{suffix or action}"
    sequence = booking.data.get("escrow_command_sequence", 0) + 1
    predecessor = booking.data.get("escrow_last_command")
    booking.data = {**booking.data, "escrow_command_sequence": sequence, "escrow_last_command": key}
    schedule(
        session,
        "ESCROW_COMMAND",
        booking.id,
        context.clock.now(),
        key,
        {
            "action": action,
            "params": params,
            "operation_id": key,
            "sequence": sequence,
            "predecessor": predecessor,
        },
    )


def confirm(session: Session, context: Context, booking: Booking) -> None:
    booking.ride_status = "CONFIRMED"
    booking.confirmed_at = context.clock.now()
    booking.price_status = (
        "POOL_SEARCHING" if booking.service_code == Service.CAR_URBAN_POOL else "FIXED_LOCKED"
    )
    if booking.service_code != Service.CAR_URBAN_POOL:
        booking.final_price_vnd = booking.quoted_price_cap_vnd
    booking.escrow_status = "DEPOSIT_PENDING"
    action = (
        "DEPOSIT_POOL"
        if booking.service_code == Service.CAR_URBAN_POOL
        else "DEPOSIT_INTERCITY"
        if booking.service_code == Service.CAR_INTERCITY_POOL
        else "DEPOSIT_FIXED"
    )
    escrow_command(
        session,
        context,
        booking,
        action,
        {
            "passenger": booking.user_id,
            "driver": booking.driver_id,
            "amount_vnd": booking.quoted_price_cap_vnd,
            "service_code": booking.service_code,
            "trip_id": booking.ride_plan_id or booking.scheduled_trip_id or "",
            "quote_vnd": booking.pool_quote_price_vnd,
            "target_driver_vnd": booking.data.get("private_fare_vnd", 0) * 80 // 100,
        },
    )
    schedule(session, "ESCROW_TIMEOUT", booking.id, context.clock.now() + 120)
    audit(session, "BOOKING_CONFIRMED", booking.id, context.clock.now())


def choose(session: Session, context: Context, user: User, run_id: str, candidate_id: str) -> dict:
    candidate = session.get(Candidate, candidate_id)
    if candidate is None or candidate.run_id != run_id:
        raise DomainError("NOT_FOUND", status=404)
    request = locked(session, TripRequest, candidate.request_id)
    if request.user_id != user.id:
        raise DomainError("NOT_FOUND", status=404)
    if candidate.expires_at <= context.clock.now():
        raise DomainError("STALE_CANDIDATE")
    if session.scalar(
        select(Booking).where(
            Booking.request_id == request.id,
            Booking.ride_status.in_(["HELD", "CONFIRMED", "RIDE_STARTED", "COMPLETED"]),
        )
    ):
        raise DomainError("REQUEST_ALREADY_BOOKED")
    details = candidate.data
    booking = Booking(
        request_id=request.id,
        user_id=user.id,
        service_code=candidate.service_code,
        pricing_version=candidate.pricing_version,
        seat_count=request.data["passenger_count"],
        quoted_price_cap_vnd=details["unmatched"],
        pool_quote_price_vnd=details["quote"],
        current_estimated_price_vnd=details["matched_estimate"],
        created_at=context.clock.now(),
        data={"private_fare_vnd": details.get("private_fare_vnd", 0), "candidate_id": candidate.id},
    )
    session.add(booking)
    session.flush()
    if candidate.source_type == "SCHEDULED_INTERCITY_TRIP":
        trip = locked(session, ScheduledTrip, candidate.target_id)
        driver = locked(session, Driver, trip.driver_id)
        if (
            trip.status != "OPEN_FOR_BOOKING"
            or not 72 * 3600 <= trip.departure_time - context.clock.now() <= 168 * 3600
        ):
            raise DomainError("BOOKING_CLOSED")
        if trip.plan_version != candidate.source_plan_version:
            raise DomainError("STALE_CANDIDATE")
        if trip.seats_booked + booking.seat_count > trip.seats_total:
            raise DomainError("INSUFFICIENT_SEATS")
        from app.services.intercity import optimize_order

        if optimize_order(session, context, trip, request) is None:
            raise DomainError("CANDIDATE_NO_LONGER_FEASIBLE")
        if not driver.active or driver.kyc_status != "VERIFIED" or not driver.accepts_intercity:
            raise DomainError("DRIVER_NOT_ELIGIBLE")
        booking.scheduled_trip_id, booking.driver_id = trip.id, trip.driver_id
        trip.seats_booked += booking.seat_count
        trip.plan_version += 1
        confirm(session, context, booking)
    elif candidate.source_type == "EXISTING_POOL_PLAN":
        initial_plan = session.get(Plan, candidate.target_id)
        driver = locked(session, Driver, initial_plan.driver_id)
        plan = locked(session, Plan, candidate.target_id)
        if plan.plan_version != candidate.source_plan_version:
            raise DomainError("STALE_CANDIDATE")
        if (
            not driver.active
            or not driver.online
            or not driver.pool_enabled
            or driver.kyc_status != "VERIFIED"
        ):
            raise DomainError("DRIVER_NOT_ELIGIBLE")
        pure = plan_from_row(session, context, plan)
        rider = rider_from_request(request)
        points = [pure.current, *[s.point for s in pure.stops], rider.pickup, rider.dropoff]
        result = insert(pure, rider, context.routing.matrix("car", points))
        if result is None:
            raise DomainError("CANDIDATE_NO_LONGER_FEASIBLE")
        booking.ride_plan_id, booking.driver_id = plan.id, plan.driver_id
        confirm(session, context, booking)
        session.flush()
        apply_result(session, plan, serialize_result(result))
        plan.plan_version += 1
        audit(session, "CORIDER_AUTO_ADDED", booking.id, context.clock.now())
    else:
        alternatives = list(
            session.scalars(
                select(Candidate)
                .where(
                    Candidate.run_id == run_id,
                    Candidate.service_code == candidate.service_code,
                    Candidate.source_type == "NEW_SINGLE_VEHICLE",
                )
                .order_by(Candidate.id)
            )
        )
        alternatives.sort(key=lambda c: (c.id != candidate.id, -c.data["score"], c.id))
        booking.data = {
            **booking.data,
            "cascade_candidates": [c.id for c in alternatives[:3]],
            "cascade_index": 0,
        }
        if not next_offer(session, context, booking):
            raise DomainError("NO_FEASIBLE_SUPPLY")
    session.flush()
    return booking_view(session, booking)


def next_offer(session: Session, context: Context, booking: Booking) -> bool:
    lock_cascade_drivers(session, booking)
    candidates = booking.data["cascade_candidates"]
    index = booking.data.get("cascade_index", 0)
    while index < len(candidates):
        candidate = session.get(Candidate, candidates[index])
        driver = locked(session, Driver, candidate.target_id)
        data = candidate.data
        booking.data = {**booking.data, "cascade_index": index + 1}
        index += 1
        if (
            not driver.online
            or not driver.active
            or not driver_available(session, driver.id, data["busy_start"], data["busy_end"])
        ):
            continue
        if candidate.service_code != booking.service_code:
            raise DomainError("OFFER_SERVICE_MISMATCH", status=500)
        request = session.get(TripRequest, booking.request_id)
        if booking.service_code == Service.CAR_URBAN_POOL and (
            not driver.pool_enabled or driver.kyc_status != "VERIFIED"
        ):
            continue
        if "INTERCITY" in booking.service_code and (
            not driver.accepts_intercity or driver.kyc_status != "VERIFIED"
        ):
            continue
        # Revalidate the selected driver's current approach and pickup window.
        earliest, latest, _ = __import__(
            "app.domain.trips", fromlist=["pickup_window"]
        ).pickup_window(request.data, booking.service_code, request.created_at)
        approach = context.routing.route(
            "motorbike" if driver.vehicle_type == "BIKE" else "car",
            Point(driver.lat, driver.lon),
            Point(**request.data["pickup"]),
        )
        if max(earliest, context.clock.now() + approach.minutes * 60) > latest:
            continue
        plan = Plan(
            driver_id=driver.id,
            service_code=booking.service_code,
            status="PLAN_CREATED",
            pricing_version=booking.pricing_version,
            data={
                "current": {"lat": driver.lat, "lon": driver.lon},
                "completed_stop_index": -1,
                "elapsed_km": 0,
                "elapsed_minutes": 0,
                "tracking": {},
                "busy_start": data["busy_start"],
                "busy_end": data["busy_end"],
                "pickup_time": max(earliest, data["pickup_time"]),
                "stops": [
                    {"rider_id": request.id, "kind": kind, "point": request.data[point]}
                    for kind, point in (("PICKUP", "pickup"), ("DROPOFF", "dropoff"))
                ],
            },
        )
        session.add(plan)
        session.flush()
        timeout = 60 if "INTERCITY" in booking.service_code else 20
        plan.plan_version += 1
        offer = Offer(
            booking_id=booking.id,
            driver_id=driver.id,
            plan_id=plan.id,
            expires_at=context.clock.now() + timeout,
            hold_expires_at=context.clock.now() + timeout + 15,
            held_version=plan.plan_version,
            attempt=index,
        )
        session.add(offer)
        session.flush()
        session.add(
            SeatHold(request_id=request.id, offer_id=offer.id, expires_at=offer.hold_expires_at)
        )
        booking.ride_plan_id, booking.driver_id = plan.id, driver.id
        booking.quoted_price_cap_vnd = data["unmatched"]
        booking.pool_quote_price_vnd = data["quote"]
        booking.current_estimated_price_vnd = data["matched_estimate"]
        booking.data = {**booking.data, "private_fare_vnd": data.get("private_fare_vnd", 0)}
        schedule(session, "OFFER_TIMEOUT", offer.id, offer.expires_at)
        return True
    booking.ride_status = "EXPIRED"
    return False


def lock_cascade_drivers(session: Session, booking: Booking) -> None:
    candidates = [session.get(Candidate, key) for key in booking.data.get("cascade_candidates", [])]
    ids = sorted({candidate.target_id for candidate in candidates if candidate is not None})
    if ids:
        session.scalars(
            select(Driver).where(Driver.id.in_(ids)).order_by(Driver.id).with_for_update()
        ).all()


def respond_offer(
    session: Session, context: Context, user: User, offer_id: str, accept: bool
) -> dict:
    existing = session.get(Offer, offer_id)
    if not existing or existing.driver_id != user.id:
        raise DomainError("NOT_FOUND", status=404)
    initial_booking = session.get(Booking, existing.booking_id)
    lock_cascade_drivers(session, initial_booking)
    plan = locked(session, Plan, existing.plan_id)
    offer = locked(session, Offer, offer_id)
    booking = locked(session, Booking, offer.booking_id)
    if offer.status != "PENDING" or booking.ride_status != "HELD":
        raise DomainError("OFFER_NOT_PENDING")
    if offer.expires_at <= context.clock.now():
        raise DomainError("OFFER_EXPIRED")
    hold = session.scalar(select(SeatHold).where(SeatHold.offer_id == offer.id).with_for_update())
    if not hold or hold.status != "ACTIVE" or hold.expires_at <= context.clock.now():
        raise DomainError("SEAT_HOLD_EXPIRED")
    if plan.plan_version != offer.held_version:
        raise DomainError("STALE_CANDIDATE")
    if accept:
        driver = locked(session, Driver, user.id)
        request = session.get(TripRequest, booking.request_id)
        if not driver.active or not driver.online:
            raise DomainError("DRIVER_NOT_ELIGIBLE")
        if booking.service_code == Service.CAR_URBAN_POOL and (
            not driver.pool_enabled or driver.kyc_status != "VERIFIED"
        ):
            raise DomainError("DRIVER_NOT_ELIGIBLE")
        if "INTERCITY" in booking.service_code and (
            not driver.accepts_intercity or driver.kyc_status != "VERIFIED"
        ):
            raise DomainError("DRIVER_NOT_ELIGIBLE")
        earliest, latest, _ = pickup_window(request.data, booking.service_code, request.created_at)
        leg = context.routing.route(
            "motorbike" if driver.vehicle_type == "BIKE" else "car",
            Point(driver.lat, driver.lon),
            Point(**request.data["pickup"]),
        )
        if max(earliest, context.clock.now() + leg.minutes * 60) > latest:
            raise DomainError("PICKUP_WINDOW_VIOLATION")
    hold.status = "CONSUMED" if accept else "RELEASED"
    offer.status = "ACCEPTED" if accept else "REJECTED"
    plan.plan_version += 1
    if accept:
        plan.status = (
            "PLAN_OPEN_SEARCHING"
            if booking.service_code == Service.CAR_URBAN_POOL
            else "PLAN_CLOSED_TO_NEW"
        )
        confirm(session, context, booking)
    else:
        plan.status = "PLAN_ABORTED"
        session.flush()
        next_offer(session, context, booking)
    audit(
        session, "OFFER_ACCEPTED" if accept else "OFFER_REJECTED", booking.id, context.clock.now()
    )
    session.flush()
    return booking_view(session, booking)
