from copy import deepcopy

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.context import Context, audit
from app.domain.errors import DomainError
from app.domain.pricing import cancellation
from app.domain.types import Point, Service
from app.models import Booking, Offer, Plan, ScheduledTrip, SeatHold, TripRequest, User
from app.services.booking import escrow_command
from app.services.common import TERMINAL, booking_view, locked, owned_booking
from app.services.intercity import RUNNING_TRIP_STATES, active_bookings


def plan_bookings(session: Session, plan: Plan) -> list[Booking]:
    return list(
        session.scalars(select(Booking).where(Booking.ride_plan_id == plan.id).order_by(Booking.id))
    )


def start(session: Session, context: Context, user: User, target_id: str) -> dict:
    plan = session.get(Plan, target_id)
    if plan:
        plan = locked(session, Plan, target_id)
        if plan.driver_id != user.id:
            raise DomainError("NOT_FOUND", status=404)
        if plan.status not in {"PLAN_OPEN_SEARCHING", "PLAN_CLOSED_TO_NEW"} or plan.data.get(
            "started"
        ):
            raise DomainError("RIDE_NOT_STARTABLE")
        bookings = [b for b in plan_bookings(session, plan) if b.ride_status == "CONFIRMED"]
    else:
        trip = locked(session, ScheduledTrip, target_id)
        if trip.driver_id != user.id:
            raise DomainError("NOT_FOUND", status=404)
        if trip.status != "PICKUP_ORDER_FIXED" or context.clock.now() < trip.departure_time:
            raise DomainError("TRIP_NOT_READY_TO_DEPART")
        bookings = active_bookings(session, trip.id)
    if not bookings or any(
        b.escrow_status not in {"DEPOSITED", "LOCKED", "TOPPED_UP"} for b in bookings
    ):
        raise DomainError("ESCROW_NOT_DEPOSITED")
    if plan:
        plan.data = {**plan.data, "started": True}
        plan.plan_version += 1
    else:
        trip.status = "DEPARTED"
        trip.plan_version += 1
    # Start operation records the assigned journey. Actual boarding remains per stop.
    for booking in bookings:
        escrow_command(session, context, booking, "START", {})
        booking.data = {**booking.data, "journey_started": True}
    audit(session, "RIDE_STARTED", target_id, context.clock.now())
    return {"id": target_id, "status": "RIDE_STARTED"}


def lock_price(session: Session, context: Context, booking: Booking, matched: bool) -> None:
    if booking.price_status != "POOL_SEARCHING":
        return
    declined = booking.unmatched_cause == "DRIVER_DECLINED"
    if matched and not declined and booking.data.get("fare"):
        booking.price_status = "MATCHED_LOCKED"
        booking.final_price_vnd = booking.data["fare"]["charged"]
    else:
        booking.price_status = "UNMATCHED_LOCKED"
        booking.final_price_vnd = (
            booking.pool_quote_price_vnd if declined else booking.quoted_price_cap_vnd
        )
    booking.current_estimated_price_vnd = booking.final_price_vnd
    booking.data = {**booking.data, "pool_lock_at": context.clock.now()}
    escrow_command(
        session,
        context,
        booking,
        "LOCK",
        {
            "final_vnd": booking.final_price_vnd,
            "matched": booking.price_status == "MATCHED_LOCKED",
            "driver_declined": declined,
        },
    )
    audit(session, "POOL_LOCK_POINT_REACHED", booking.id, context.clock.now())


def complete_stop(
    session: Session, context: Context, user: User, target_id: str, stop_id: str
) -> dict:
    plan = session.get(Plan, target_id)
    if plan:
        plan = locked(session, Plan, target_id)
        if plan.driver_id != user.id or not plan.data.get("started"):
            raise DomainError("RIDE_NOT_STARTED")
        data = deepcopy(plan.data)
        bookings = plan_bookings(session, plan)
    else:
        trip = locked(session, ScheduledTrip, target_id)
        if trip.driver_id != user.id or trip.status != "DEPARTED":
            raise DomainError("RIDE_NOT_STARTED")
        data = deepcopy(trip.data)
        bookings = active_bookings(session, trip.id)
    index = data.get("completed_stop_index", -1) + 1
    if str(index) != stop_id or index >= len(data.get("stops", [])):
        raise DomainError("STOP_OUT_OF_ORDER")
    stop = data["stops"][index]
    booking = next((b for b in bookings if b.request_id == stop["rider_id"]), None)
    if booking is None or booking.ride_status in TERMINAL:
        raise DomainError("STOP_BOOKING_NOT_ACTIVE")
    previous = Point(**data.get("current", stop["point"]))
    point = Point(**stop["point"])
    leg = context.routing.route(
        "motorbike" if booking.service_code == Service.BIKE_URBAN else "car", previous, point
    )
    tracking = data.setdefault("tracking", {})
    onboard = [b for b in bookings if tracking.get(b.request_id, {}).get("onboard", False)]
    for existing in onboard:
        tracking[existing.request_id]["traveled_km"] = (
            tracking[existing.request_id].get("traveled_km", 0) + leg.km
        )
        if leg.km > 0 and len(onboard) >= 2:
            existing.data = {**existing.data, "ever_coridden": True}
    if index > 0:
        data["elapsed_km"] = data.get("elapsed_km", 0) + leg.km
        data["elapsed_minutes"] = data.get("elapsed_minutes", 0) + leg.minutes + 1
    row = tracking.setdefault(booking.request_id, {"traveled_km": 0})
    if stop["kind"] == "PICKUP":
        if booking.escrow_status not in {"DEPOSITED", "LOCKED", "TOPPED_UP"}:
            raise DomainError("ESCROW_NOT_DEPOSITED")
        if not booking.data.get("journey_started"):
            escrow_command(session, context, booking, "START", {})
            booking.data = {**booking.data, "journey_started": True}
        row.update(actual_pickup=context.clock.now(), onboard=True)
        booking.data = {**booking.data, "actual_pickup_at": context.clock.now()}
        booking.ride_status = "RIDE_STARTED"
        request = session.get(TripRequest, booking.request_id)
        if booking.service_code == Service.CAR_URBAN_POOL and request.data["car_direct_km"] <= 3:
            lock_price(session, context, booking, booking.data.get("ever_coridden", False))
    else:
        if not row.get("onboard"):
            raise DomainError("PASSENGER_NOT_ONBOARD")
        if booking.service_code == Service.CAR_URBAN_POOL:
            lock_price(session, context, booking, booking.data.get("ever_coridden", False))
        row["onboard"] = False
        booking.ride_status = "COMPLETED"
        booking.data = {**booking.data, "completed_at": context.clock.now()}
        escrow_command(session, context, booking, "COMPLETE", {})
        escrow_command(session, context, booking, "RELEASE", {})
    data["current"] = stop["point"]
    data["completed_stop_index"] = index
    if plan:
        plan.data = data
        plan.plan_version += 1
        check_lock_points(session, context, plan)
    else:
        trip.data = data
        trip.plan_version += 1
    audit(session, "STOP_COMPLETED", target_id, context.clock.now(), {"stop_index": index})
    return {
        "id": target_id,
        "completed_stop_index": index,
        "booking": booking_view(session, booking),
    }


def check_lock_points(session: Session, context: Context, plan: Plan) -> None:
    bookings = plan_bookings(session, plan)
    data = plan.data
    current = Point(**data["current"])
    remaining = data["stops"][data.get("completed_stop_index", -1) + 1 :]
    matrix = context.routing.matrix("car", [current, *[Point(**s["point"]) for s in remaining]])
    for booking in bookings:
        if booking.price_status != "POOL_SEARCHING" or booking.ride_status != "RIDE_STARTED":
            continue
        km, position = 0.0, current
        for stop in remaining:
            point = Point(**stop["point"])
            km += matrix.leg(position, point).km
            position = point
            if stop["rider_id"] == booking.request_id and stop["kind"] == "DROPOFF":
                break
        request = session.get(TripRequest, booking.request_id)
        detour = data.get("detours", {}).get(booking.request_id, 0)
        occupancy = {
            b.request_id: b.seat_count
            for b in bookings
            if data.get("tracking", {}).get(b.request_id, {}).get("onboard")
        }
        full_segments = []
        for stop in remaining:
            if stop["rider_id"] == booking.request_id and stop["kind"] == "DROPOFF":
                full_segments.append(sum(occupancy.values()) == 4)
                break
            full_segments.append(sum(occupancy.values()) == 4)
            if stop["kind"] == "PICKUP":
                member = next((b for b in bookings if b.request_id == stop["rider_id"]), None)
                if member:
                    occupancy[member.request_id] = member.seat_count
            else:
                occupancy.pop(stop["rider_id"], None)
        all_full = bool(full_segments) and all(full_segments)
        if km < 3 or request.data["max_passenger_detour_ratio"] - detour < 0.02 or all_full:
            lock_price(session, context, booking, booking.data.get("ever_coridden", False))
    if not any(
        b.price_status == "POOL_SEARCHING" and b.ride_status not in TERMINAL for b in bookings
    ):
        plan.status = "PLAN_CLOSED_TO_NEW"


def complete(session: Session, context: Context, user: User, target_id: str) -> dict:
    plan = session.get(Plan, target_id)
    target = locked(session, Plan if plan else ScheduledTrip, target_id)
    if target.driver_id != user.id:
        raise DomainError("NOT_FOUND", status=404)
    bookings = (
        plan_bookings(session, target)
        if plan
        else list(session.scalars(select(Booking).where(Booking.scheduled_trip_id == target.id)))
    )
    if any(b.ride_status not in TERMINAL for b in bookings):
        raise DomainError("UNFINISHED_STOPS")
    target.status = "PLAN_COMPLETED" if plan else "COMPLETED"
    target.plan_version += 1
    return {"id": target_id, "status": target.status}


def cancel_booking(
    session: Session,
    context: Context,
    user: User,
    booking_id: str,
    driver_fault: bool = False,
    no_show: bool = False,
) -> dict:
    booking = owned_booking(session, user, booking_id, True)
    if booking.ride_status in TERMINAL:
        raise DomainError("BOOKING_ALREADY_TERMINAL")
    if not driver_fault and user.id != booking.user_id and user.role != "ADMIN" and not no_show:
        raise DomainError("FORBIDDEN", status=403)
    request = session.get(TripRequest, booking.request_id)
    trip = (
        session.get(ScheduledTrip, booking.scheduled_trip_id) if booking.scheduled_trip_id else None
    )
    plan = session.get(Plan, booking.ride_plan_id) if booking.ride_plan_id else None
    others = (
        [
            b
            for b in plan_bookings(session, plan)
            if b.id != booking.id and b.ride_status not in TERMINAL
        ]
        if plan
        else []
    )
    now = context.clock.now()
    preferred = trip.departure_time if trip else plan.data["pickup_time"] if plan else now
    fees = cancellation(
        booking.service_code,
        booking.final_price_vnd or booking.quoted_price_cap_vnd,
        booking.pool_quote_price_vnd,
        max(121, now - booking.confirmed_at)
        if booking.data.get("driver_arrived_at")
        else now - booking.confirmed_at
        if booking.confirmed_at
        else -1,
        (preferred - now) / 3600,
        request.data["booking_type"] == "SCHEDULED",
        no_show,
        bool(others),
        driver_fault,
        trip.status in RUNNING_TRIP_STATES if trip else True,
        booking.data.get("merge_free_until", 0) > now,
    )
    booking.ride_status = (
        "NO_SHOW"
        if no_show
        else "CANCELLED_BY_DRIVER"
        if driver_fault
        else "CANCELLED_BY_PASSENGER"
    )
    booking.cancellation_fee_vnd = fees["fee"]
    booking.data = {**booking.data, "cancellation_split": fees}
    booking.data = {**booking.data, "ended_at": now}
    for offer in session.scalars(
        select(Offer).where(Offer.booking_id == booking.id, Offer.status == "PENDING")
    ):
        offer.status = "CANCELLED"
        hold = session.scalar(select(SeatHold).where(SeatHold.offer_id == offer.id))
        hold.status = "RELEASED"
    if booking.escrow_status != "NONE":
        escrow_command(
            session,
            context,
            booking,
            "CANCEL",
            {
                "fee_vnd": fees["fee"],
                "driver_vnd": fees["driver"],
                "platform_vnd": fees["platform"],
                "fund_vnd": fees["fund"],
            },
        )
    if trip:
        trip.seats_booked -= booking.seat_count
        trip.plan_version += 1
    if plan:
        data = deepcopy(plan.data)
        done = data.get("completed_stop_index", -1)
        data["stops"] = data["stops"][: done + 1] + [
            s for s in data["stops"][done + 1 :] if s["rider_id"] != booking.request_id
        ]
        plan.data = data
        plan.plan_version += 1
        if not others:
            plan.status = "PLAN_ABORTED"
        for other in others:
            other.unmatched_cause = (
                "CORIDER_CANCELLED_LATE"
                if other.price_status == "MATCHED_LOCKED"
                else "CORIDER_CANCELLED_EARLY"
            )
            if other.price_status == "MATCHED_LOCKED" and not driver_fault:
                credited = other.data.get("credited_cancellation_vnd", 0) + fees["driver"] // max(
                    1, len(others)
                )
                other.data = {**other.data, "credited_cancellation_vnd": credited}
                escrow_command(
                    session,
                    context,
                    other,
                    "PROTECT_LATE_CANCEL",
                    {"credited_penalty_vnd": credited},
                    f"late-cancel:{booking.id}",
                )
    audit(session, "BOOKING_CANCELLED", booking.id, now, {"fee_vnd": fees["fee"]})
    session.flush()
    return booking_view(session, booking)


def decline_corider(
    session: Session, context: Context, user: User, plan_id: str, booking_id: str, reason_code: str
) -> dict:
    plan = locked(session, Plan, plan_id)
    if plan.driver_id != user.id or plan.service_code != Service.CAR_URBAN_POOL:
        raise DomainError("NOT_FOUND", status=404)
    booking = session.get(Booking, booking_id)
    if booking is None or booking.ride_plan_id != plan.id or booking.ride_status != "CONFIRMED":
        raise DomainError("CORIDER_NOT_DECLINABLE")
    # Safety claims require administrative verification; reporting alone never waives penalties.
    cancel_booking(session, context, user, booking_id, driver_fault=True)
    for existing in plan_bookings(session, plan):
        if (
            existing.id != booking_id
            and existing.ride_status not in TERMINAL
            and existing.price_status == "POOL_SEARCHING"
        ):
            existing.unmatched_cause = "DRIVER_DECLINED"
    plan.status = "PLAN_CLOSED_TO_NEW"
    audit(
        session,
        "DRIVER_DECLINED_COMPATIBLE_CORIDER",
        plan.id,
        context.clock.now(),
        {"reason_code": reason_code},
    )
    return {"id": plan.id, "status": plan.status, "guarantee_eligible": False}
