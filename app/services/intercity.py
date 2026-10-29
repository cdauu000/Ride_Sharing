from datetime import datetime
from itertools import permutations
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import baseline
from app.context import Context, audit, schedule
from app.domain.errors import DomainError
from app.domain.pricing import fixed_fare, floor_money, seat_reference
from app.domain.trips import pickup_window
from app.domain.types import Point, Service
from app.models import Auxiliary, Booking, Driver, ScheduledTrip, TripRequest, User
from app.routing import Matrix
from app.schemas import PublishTrip
from app.services.booking import escrow_command
from app.services.candidate import driver_available
from app.services.common import locked

RUNNING_TRIP_STATES = {
    "CONFIRMED",
    "CONFIRMED_TOPUP",
    "CONFIRMED_UNDER_MIN",
    "PICKUP_ORDER_FIXED",
    "DEPARTED",
}


def publish(session: Session, context: Context, user: User, payload: PublishTrip) -> ScheduledTrip:
    driver = locked(session, Driver, user.id)
    if (
        driver.vehicle_type != "CAR4"
        or driver.kyc_status != "VERIFIED"
        or not driver.accepts_intercity
    ):
        raise DomainError("DRIVER_NOT_ELIGIBLE", status=403)
    departure = payload.departure_time.timestamp()
    if not 72 * 3600 <= departure - context.clock.now() <= 7 * 86400:
        raise DomainError("INVALID_INTERCITY_LEAD_TIME", status=422)
    origin, dest = Point(**payload.origin.model_dump()), Point(**payload.destination.model_dump())
    leg = context.routing.route("car", origin, dest)
    if context.areas.classify(origin, dest, leg.km) != "INTERCITY":
        raise DomainError("INTERCITY_CORRIDOR_REQUIRED", status=422)
    private = fixed_fare(Service.CAR_INTERCITY_PRIVATE, leg.km, leg.minutes)
    reference = seat_reference(private)
    price = payload.seat_price_vnd or reference
    if price % 1000 or not reference * 9 <= price * 10 <= reference * 11:
        raise DomainError("SEAT_PRICE_OUTSIDE_BAND", status=422)
    if not driver_available(
        session, user.id, departure - 1800, departure + (leg.minutes * 2 + 60) * 60
    ):
        raise DomainError("DRIVER_SCHEDULE_CONFLICT")
    trip = ScheduledTrip(
        driver_id=user.id,
        corridor_id=payload.corridor_id,
        departure_time=departure,
        min_seats_to_run=payload.min_seats_to_run,
        seat_reference_vnd=reference,
        seat_price_vnd=price,
        pricing_version=baseline()["pricing_version"],
        data={
            **payload.model_dump(mode="json"),
            "direct_km": leg.km,
            "direct_min": leg.minutes,
            "private_fare_vnd": private,
        },
    )
    session.add(trip)
    session.flush()
    for kind, hours in (
        ("INTERCITY_CLOSE", 72),
        ("INTERCITY_DRIVER_DEADLINE", 60),
        ("INTERCITY_FIX_ORDER", 24),
    ):
        schedule(session, kind, trip.id, departure - hours * 3600)
    audit(session, "POOL_TRIP_PUBLISHED", trip.id, context.clock.now())
    return trip


def trip_view(trip: ScheduledTrip) -> dict[str, Any]:
    return {
        "id": trip.id,
        "driver_id": trip.driver_id,
        "corridor_id": trip.corridor_id,
        "departure_time": datetime.fromtimestamp(
            trip.departure_time, __import__("datetime").UTC
        ).isoformat(),
        "status": trip.status,
        "seats_total": trip.seats_total,
        "seats_booked": trip.seats_booked,
        "min_seats_to_run": trip.min_seats_to_run,
        "seat_price_vnd": trip.seat_price_vnd,
        "seat_reference_vnd": trip.seat_reference_vnd,
        "plan_version": trip.plan_version,
        "pickup_order_fixed": trip.data.get("pickup_order_fixed", False),
    }


def active_bookings(session: Session, trip_id: str) -> list[Booking]:
    return list(
        session.scalars(
            select(Booking)
            .where(
                Booking.scheduled_trip_id == trip_id,
                Booking.ride_status.in_(["CONFIRMED", "RIDE_STARTED"]),
            )
            .order_by(Booking.id)
        )
    )


def optimize_order(
    session: Session,
    context: Context,
    trip: ScheduledTrip,
    additional_request: TripRequest | None = None,
    matrix: Matrix | None = None,
) -> dict[str, Any] | None:
    bookings = active_bookings(session, trip.id)
    requests = [session.get(TripRequest, b.request_id) for b in bookings]
    if additional_request:
        requests.append(additional_request)
    if not requests:
        return {"stops": [], "minutes": 0, "pickup_times": {}}
    if sum(r.data["passenger_count"] for r in requests) > 4:
        return None
    genders = {r.data.get("verified_gender", "UNKNOWN") for r in requests}
    if (
        len(requests) > 1
        and any(r.data["same_gender_coride"] for r in requests)
        and (len(genders) != 1 or "UNKNOWN" in genders)
    ):
        return None
    origin = Point(**trip.data["origin"])
    points = [origin] + [Point(**r.data[k]) for r in requests for k in ("pickup", "dropoff")]
    matrix = matrix or context.routing.matrix("car", points)
    best = None
    for pickups in permutations(requests):
        for dropoffs in permutations(requests):
            now, position = trip.departure_time, origin
            picked, stops = {}, []
            valid = True
            for kind, sequence in (("PICKUP", pickups), ("DROPOFF", dropoffs)):
                for request in sequence:
                    point = Point(**request.data["pickup" if kind == "PICKUP" else "dropoff"])
                    now += matrix.leg(position, point).minutes * 60
                    if kind == "PICKUP":
                        earliest, latest, _ = pickup_window(
                            request.data, Service.CAR_INTERCITY_POOL, request.created_at
                        )
                        now = max(now, earliest)
                        if now > latest:
                            valid = False
                            break
                        picked[request.id] = now
                    else:
                        limit = (
                            request.data.get("max_in_vehicle_time_min")
                            or request.data["car_direct_min"] * 1.5 + 10
                        )
                        if (
                            (now - picked[request.id]) / 60 > limit
                            or request.data.get("latest_arrival")
                            and now
                            > datetime.fromisoformat(request.data["latest_arrival"]).timestamp()
                        ):
                            valid = False
                            break
                    stops.append(
                        {
                            "rider_id": request.id,
                            "kind": kind,
                            "point": {"lat": point.lat, "lon": point.lon},
                            "planned_time": now,
                        }
                    )
                    now += 60
                    position = point
                if not valid:
                    break
            if valid and (best is None or now < best["finish_time"]):
                best = {
                    "stops": stops,
                    "minutes": (now - trip.departure_time) / 60,
                    "finish_time": now,
                    "pickup_times": picked,
                }
    return best


def close_trip(session: Session, context: Context, trip: ScheduledTrip) -> None:
    if trip.status != "OPEN_FOR_BOOKING":
        return
    trip.plan_version += 1
    if trip.seats_booked >= trip.min_seats_to_run:
        trip.status = "CONFIRMED"
    elif trip.seats_booked == 0:
        trip.status = "CANCELLED_LOW_DEMAND"
    elif not attempt_merge(session, context, trip):
        offer_topup(session, context, trip)
    audit(
        session, "POOL_TRIP_BOOKING_CLOSED", trip.id, context.clock.now(), {"status": trip.status}
    )


def attempt_merge(session: Session, context: Context, source: ScheduledTrip) -> bool:
    others = list(
        session.scalars(
            select(ScheduledTrip)
            .where(
                ScheduledTrip.corridor_id == source.corridor_id,
                ScheduledTrip.id != source.id,
                ScheduledTrip.status.in_(
                    ["OPEN_FOR_BOOKING", "TOPUP_OFFERED", "UNDER_MIN_DRIVER_DECISION"]
                ),
            )
            .order_by(ScheduledTrip.id)
            .with_for_update()
        )
    )
    others.sort(
        key=lambda target: (
            target.seats_booked + source.seats_booked < target.min_seats_to_run,
            abs(target.departure_time - source.departure_time),
            target.id,
        )
    )
    for target in others:
        if target.data.get("topup_funding") or any(
            b.price_status == "TOPUP_LOCKED" for b in active_bookings(session, target.id)
        ):
            continue
        if (
            target.seats_booked == 0
            or target.seats_booked + source.seats_booked > 4
            or abs(target.departure_time - source.departure_time) > 3600
        ):
            continue
        source_bookings = active_bookings(session, source.id)
        # Check all passengers together before committing a merge.
        original_ids = [b.scheduled_trip_id for b in source_bookings]
        for b in source_bookings:
            b.scheduled_trip_id = target.id
        session.flush()
        order = optimize_order(session, context, target)
        if order is None:
            for b, old_id in zip(source_bookings, original_ids, strict=True):
                b.scheduled_trip_id = old_id
            session.flush()
            continue
        for b in source_bookings:
            old_seat = source.seat_price_vnd
            reduction = max(0, old_seat - target.seat_price_vnd) * b.seat_count
            b.final_price_vnd -= reduction
            b.current_estimated_price_vnd = b.final_price_vnd
            b.driver_id = target.driver_id
            b.price_status = "MERGED_REDUCED_LOCKED"
            b.data = {**b.data, "merge_free_until": context.clock.now() + 7200}
            escrow_command(
                session,
                context,
                b,
                "MERGE",
                {"driver": target.driver_id, "trip_id": target.id, "final_vnd": b.final_price_vnd},
                f"merge:{source.id}",
            )
        target.seats_booked += source.seats_booked
        source.seats_booked = 0
        source.status = "MERGED"
        source.data = {**source.data, "merged_into_trip_id": target.id}
        source.plan_version += 1
        target.status = "MERGE_PENDING_CONFIRMATION"
        target.plan_version += 1
        target.data = {**target.data, "merge_free_until": context.clock.now() + 7200}
        for row in session.scalars(
            select(Auxiliary).where(Auxiliary.kind == "TOPUP", Auxiliary.target_id == target.id)
        ):
            row.data = {**row.data, "status": "WITHDRAWN"}
        schedule(
            session,
            "INTERCITY_MERGE_END",
            target.id,
            context.clock.now() + 7200,
            f"merge-end:{source.id}:{target.id}",
        )
        audit(session, "POOL_TRIP_MERGED", source.id, context.clock.now(), {"target_id": target.id})
        return True
    return False


def offer_topup(session: Session, context: Context, trip: ScheduledTrip) -> None:
    if trip.seats_booked == 0:
        trip.status = "CANCELLED_LOW_DEMAND"
        return
    trip.status = "TOPUP_OFFERED"
    price = floor_money(trip.data["private_fare_vnd"] / trip.seats_booked)
    deadline = min(context.clock.now() + 6 * 3600, trip.departure_time - 60 * 3600)
    generation = str(context.clock.now())
    for booking in active_bookings(session, trip.id):
        row = Auxiliary(
            kind="TOPUP",
            owner_id=booking.user_id,
            target_id=trip.id,
            created_at=context.clock.now(),
            data={
                "booking_id": booking.id,
                "amount_vnd": max(0, price - trip.seat_price_vnd) * booking.seat_count,
                "status": "PENDING",
                "expires_at": deadline,
                "generation": generation,
            },
        )
        session.add(row)
    schedule(session, "INTERCITY_TOPUP_END", trip.id, deadline, f"topup-end:{trip.id}:{generation}")


def respond_topup(
    session: Session, context: Context, user: User, offer_id: str, decision: str
) -> dict:
    offer = session.get(Auxiliary, offer_id)
    if offer is None or offer.kind != "TOPUP" or offer.owner_id != user.id:
        raise DomainError("NOT_FOUND", status=404)
    trip = locked(session, ScheduledTrip, offer.target_id)
    if (
        trip.status != "TOPUP_OFFERED"
        or offer.data["status"] != "PENDING"
        or context.clock.now() >= offer.data["expires_at"]
    ):
        raise DomainError("TOPUP_OFFER_EXPIRED")
    offer.data = {**offer.data, "status": decision}
    session.flush()
    if decision == "DECLINE":
        trip.status = "UNDER_MIN_DRIVER_DECISION"
    else:
        all_offers = list(
            session.scalars(
                select(Auxiliary).where(Auxiliary.kind == "TOPUP", Auxiliary.target_id == trip.id)
            )
        )
        current = [o for o in all_offers if o.data["generation"] == offer.data["generation"]]
        if current and all(o.data["status"] == "ACCEPT" for o in current):
            trip.data = {**trip.data, "topup_funding": True}
            for row in current:
                booking = session.get(Booking, row.data["booking_id"])
                booking.data = {
                    **booking.data,
                    "topup_accepted": True,
                    "topup_original_price": booking.final_price_vnd,
                    "topup_offer_id": row.id,
                }
                escrow_command(
                    session,
                    context,
                    booking,
                    "TOPUP",
                    {"amount_vnd": row.data["amount_vnd"]},
                    f"topup:{row.id}",
                )
    return {"id": offer.id, **offer.data, "trip_status": trip.status}


def driver_decision(
    session: Session, context: Context, user: User, trip_id: str, decision: str
) -> dict:
    trip = locked(session, ScheduledTrip, trip_id)
    if trip.data.get("topup_funding"):
        raise DomainError("TOPUP_FUNDING_REQUIRES_RECONCILIATION")
    if trip.driver_id != user.id:
        raise DomainError("NOT_FOUND", status=404)
    if (
        trip.status != "UNDER_MIN_DRIVER_DECISION"
        or context.clock.now() >= trip.departure_time - 60 * 3600
    ):
        raise DomainError("DRIVER_DECISION_NOT_AVAILABLE")
    if decision == "RUN":
        trip.status = "CONFIRMED_UNDER_MIN"
    else:
        cancel_low_demand(session, context, trip)
    trip.plan_version += 1
    return trip_view(trip)


def recover_topup(session: Session, context: Context, trip: ScheduledTrip) -> None:
    """Restore original fares only after each original top-up has a known outcome.

    Reverts remain behind their original command in the outbox. An uncertain
    broadcast must be reconciled/retried; it can never be silently skipped.
    """
    if not trip.data.get("topup_funding") or trip.data.get("topup_reverting"):
        return
    trip.data = {**trip.data, "topup_reverting": True}
    trip.status = "UNDER_MIN_DRIVER_DECISION"
    trip.plan_version += 1
    for booking in active_bookings(session, trip.id):
        if booking.data.get("topup_accepted"):
            escrow_command(
                session,
                context,
                booking,
                "REVERT_TOPUP",
                {},
                f"revert-topup:{booking.data['topup_offer_id']}",
            )
    audit(session, "TOPUP_RECOVERY_QUEUED", trip.id, context.clock.now())


def cancel_low_demand(session: Session, context: Context, trip: ScheduledTrip) -> None:
    trip.status = "CANCELLED_LOW_DEMAND"
    trip.plan_version += 1
    for booking in active_bookings(session, trip.id):
        booking.ride_status = "CANCELLED_BY_SYSTEM"
        booking.data = {
            **booking.data,
            "cancellation_reason": "LOW_DEMAND",
            "alternative_service": "CAR_INTERCITY_PRIVATE",
        }
        escrow_command(
            session,
            context,
            booking,
            "CANCEL",
            {"fee_vnd": 0, "driver_vnd": 0, "platform_vnd": 0, "fund_vnd": 0},
        )
    trip.seats_booked = 0
    audit(session, "POOL_TRIP_CANCELLED_LOW_DEMAND", trip.id, context.clock.now())
