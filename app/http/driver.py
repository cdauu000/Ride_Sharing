from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter
from sqlalchemy import select

from app.context import audit
from app.domain.errors import DomainError
from app.domain.locations import location_view
from app.domain.trips import pickup_window
from app.domain.types import Point
from app.http.dependencies import Actor, Ctx, Db, Key, driver_view
from app.models import (
    Booking,
    Driver,
    Offer,
    Payout,
    Plan,
    ScheduledTrip,
    TripRequest,
)
from app.schemas import (
    Arrival,
    Coordinate,
    DriverSettings,
    Reason,
)
from app.security import require_role
from app.services import booking as booking_service
from app.services import intercity, ride
from app.services.common import booking_view, idempotent, locked, owned_booking
from app.services.driver_views import offer_view

router = APIRouter()


@router.post("/rides/{target_id}/arrived", response_model=dict[str, Any])
def arrived(
    target_id: str, payload: Arrival, session: Db, context: Ctx, user: Actor, key: Key = None
) -> dict:
    require_role(user, "DRIVER")

    def action() -> dict:
        row = owned_booking(session, user, payload.booking_id, True)
        if (
            row.driver_id != user.id
            or target_id not in (row.ride_plan_id, row.scheduled_trip_id)
            or row.ride_status != "CONFIRMED"
        ):
            raise DomainError("BOOKING_NOT_AWAITING_PICKUP")
        driver = session.get(Driver, user.id)
        intent = session.get(TripRequest, row.request_id)
        from app.routing import haversine

        if (
            driver.location_at is None
            or context.clock.now() - driver.location_at > 120
            or haversine(Point(driver.lat, driver.lon), Point(**intent.data["pickup"])) > 0.2
        ):
            raise DomainError("DRIVER_NOT_AT_PICKUP")
        row.data = {
            **row.data,
            "driver_arrived_at": row.data.get("driver_arrived_at", context.clock.now()),
            "no_show_eligible_at": max(
                row.data.get("driver_arrived_at", context.clock.now()),
                pickup_window(intent.data, row.service_code, intent.created_at)[0],
            )
            + 300,
        }
        return {
            "booking_id": row.id,
            "arrived_at": row.data["driver_arrived_at"],
            "no_show_eligible_at": row.data["no_show_eligible_at"],
        }

    return idempotent(
        session,
        context,
        user,
        key,
        f"POST /rides/{target_id}/arrived",
        payload.model_dump(),
        action,
    )


@router.post("/bookings/{booking_id}/no-show", response_model=dict[str, Any])
def no_show(booking_id: str, session: Db, context: Ctx, user: Actor, key: Key = None) -> dict:
    require_role(user, "DRIVER")

    def action() -> dict:
        row = owned_booking(session, user, booking_id, True)
        arrival = row.data.get("driver_arrived_at")
        if (
            row.driver_id != user.id
            or row.ride_status != "CONFIRMED"
            or arrival is None
            or context.clock.now() < row.data.get("no_show_eligible_at", arrival + 300)
        ):
            raise DomainError("NO_SHOW_WAIT_NOT_MET")
        return ride.cancel_booking(session, context, user, booking_id, no_show=True)

    return idempotent(
        session, context, user, key, f"POST /bookings/{booking_id}/no-show", {}, action
    )


@router.put("/driver/settings", response_model=dict[str, Any])
def update_settings(
    payload: DriverSettings, session: Db, context: Ctx, user: Actor, key: Key = None
) -> dict:
    require_role(user, "DRIVER")

    def action() -> dict:
        driver = locked(session, Driver, user.id)
        if (payload.pool_enabled or payload.accepts_intercity) and (
            driver.kyc_status != "VERIFIED" or driver.vehicle_type != "CAR4"
        ):
            raise DomainError("KYC_REQUIRED", status=403)
        for name, value in payload.model_dump().items():
            setattr(driver, name, value)
        return driver_view(driver)

    return idempotent(
        session, context, user, key, "PUT /driver/settings", payload.model_dump(), action
    )


@router.get("/driver/settings", response_model=dict[str, Any])
def get_settings(session: Db, user: Actor) -> dict:
    require_role(user, "DRIVER")
    return driver_view(session.get(Driver, user.id))


@router.put("/driver/location", response_model=dict[str, Any])
def location(payload: Coordinate, session: Db, context: Ctx, user: Actor, key: Key = None) -> dict:
    require_role(user, "DRIVER")

    def action() -> dict:
        driver = locked(session, Driver, user.id)
        driver.lat, driver.lon, driver.location_at = payload.lat, payload.lon, context.clock.now()
        # GPS progress is applied only to plans already started; no coordinates in audit logs.
        for plan in session.scalars(
            select(Plan)
            .where(
                Plan.driver_id == user.id,
                Plan.status.in_(["PLAN_OPEN_SEARCHING", "PLAN_CLOSED_TO_NEW"]),
            )
            .with_for_update()
        ):
            if not plan.data.get("started"):
                continue
            from copy import deepcopy

            data = deepcopy(plan.data)
            old = Point(**data["current"])
            leg = context.routing.route(
                "motorbike" if driver.vehicle_type == "BIKE" else "car",
                old,
                Point(payload.lat, payload.lon),
            )
            if leg.km > 5:
                raise DomainError("GPS_JUMP_REQUIRES_REVIEW", status=422)
            data["current"] = payload.model_dump()
            data["elapsed_km"] = data.get("elapsed_km", 0) + leg.km
            data["elapsed_minutes"] = data.get("elapsed_minutes", 0) + leg.minutes
            for tracking in data.get("tracking", {}).values():
                if tracking.get("onboard"):
                    tracking["traveled_km"] = tracking.get("traveled_km", 0) + leg.km
            plan.data = data
            plan.plan_version += 1
            if plan.service_code == "CAR_URBAN_POOL":
                ride.check_lock_points(session, context, plan)
        return {"ok": True, "updated_at": driver.location_at}

    return idempotent(
        session, context, user, key, "PUT /driver/location", payload.model_dump(), action
    )


@router.get("/offers", response_model=list[dict[str, Any]])
def offers(session: Db, context: Ctx, user: Actor) -> list[dict]:
    require_role(user, "DRIVER")
    return [
        offer_view(session, context, o)
        for o in session.scalars(
            select(Offer)
            .where(
                Offer.driver_id == user.id,
                Offer.status == "PENDING",
                Offer.expires_at > context.clock.now(),
            )
            .order_by(Offer.expires_at)
        )
    ]


@router.post("/offers/{offer_id}/accept", response_model=dict[str, Any])
def accept_offer(offer_id: str, session: Db, context: Ctx, user: Actor, key: Key = None) -> dict:
    require_role(user, "DRIVER")
    return idempotent(
        session,
        context,
        user,
        key,
        f"POST /offers/{offer_id}/accept",
        {},
        lambda: booking_service.respond_offer(session, context, user, offer_id, True),
    )


@router.post("/offers/{offer_id}/reject", response_model=dict[str, Any])
def reject_offer(offer_id: str, session: Db, context: Ctx, user: Actor, key: Key = None) -> dict:
    require_role(user, "DRIVER")
    return idempotent(
        session,
        context,
        user,
        key,
        f"POST /offers/{offer_id}/reject",
        {},
        lambda: booking_service.respond_offer(session, context, user, offer_id, False),
    )


@router.get("/driver/rides", response_model=list[dict[str, Any]])
def driver_rides(session: Db, context: Ctx, user: Actor) -> list[dict]:
    require_role(user, "DRIVER")
    result = []
    targets = list(
        session.scalars(
            select(Plan).where(
                Plan.driver_id == user.id, Plan.status.not_in(["PLAN_ABORTED", "PLAN_COMPLETED"])
            )
        )
    )
    targets += list(
        session.scalars(
            select(ScheduledTrip).where(
                ScheduledTrip.driver_id == user.id,
                ScheduledTrip.status.in_(list(intercity.RUNNING_TRIP_STATES)),
            )
        )
    )
    for plan in targets:
        is_urban = isinstance(plan, Plan)
        members = list(
            session.scalars(
                select(Booking).where(
                    (Booking.ride_plan_id if is_urban else Booking.scheduled_trip_id) == plan.id
                )
            )
        )
        by_request = {b.request_id: b.id for b in members}
        requests = {b.request_id: session.get(TripRequest, b.request_id) for b in members}
        stops = [
            {
                "id": str(i),
                "booking_id": by_request.get(s["rider_id"]),
                "kind": s["kind"],
                "point": location_view(
                    s["point"],
                    requests[s["rider_id"]].data.get(
                        "pickup_label" if s["kind"] == "PICKUP" else "dropoff_label"
                    ),
                ),
                "completed": i <= plan.data.get("completed_stop_index", -1),
            }
            for i, s in enumerate(plan.data.get("stops", []))
        ]
        result.append(
            {
                "id": plan.id,
                "service_code": plan.service_code if is_urban else "CAR_INTERCITY_POOL",
                "status": plan.status,
                "plan_version": plan.plan_version,
                "stops": stops,
                "bookings": [
                    {
                        **booking_view(session, b),
                        "no_show_eligible_at": b.data.get("no_show_eligible_at"),
                    }
                    for b in members
                ],
                "started": plan.data.get("started", False),
                "departure_time": datetime.fromtimestamp(plan.departure_time, UTC).isoformat()
                if not is_urban
                else None,
                "can_start": (
                    not plan.data.get("started")
                    and plan.status in {"PLAN_OPEN_SEARCHING", "PLAN_CLOSED_TO_NEW"}
                    if is_urban
                    else plan.status == "PICKUP_ORDER_FIXED"
                    and context.clock.now() >= plan.departure_time
                )
                and any(b.ride_status == "CONFIRMED" for b in members)
                and all(
                    b.escrow_status in {"DEPOSITED", "LOCKED", "TOPPED_UP"}
                    for b in members
                    if b.ride_status == "CONFIRMED"
                ),
            }
        )
    return result


@router.post("/rides/{target_id}/start", response_model=dict[str, Any])
def start_ride(target_id: str, session: Db, context: Ctx, user: Actor, key: Key = None) -> dict:
    require_role(user, "DRIVER")
    return idempotent(
        session,
        context,
        user,
        key,
        f"POST /rides/{target_id}/start",
        {},
        lambda: ride.start(session, context, user, target_id),
    )


@router.post("/rides/{target_id}/stops/{stop_id}/complete", response_model=dict[str, Any])
def stop_complete(
    target_id: str, stop_id: str, session: Db, context: Ctx, user: Actor, key: Key = None
) -> dict:
    require_role(user, "DRIVER")
    return idempotent(
        session,
        context,
        user,
        key,
        f"POST /rides/{target_id}/stops/{stop_id}/complete",
        {},
        lambda: ride.complete_stop(session, context, user, target_id, stop_id),
    )


@router.post("/rides/{target_id}/complete", response_model=dict[str, Any])
def finish_ride(target_id: str, session: Db, context: Ctx, user: Actor, key: Key = None) -> dict:
    require_role(user, "DRIVER")
    return idempotent(
        session,
        context,
        user,
        key,
        f"POST /rides/{target_id}/complete",
        {},
        lambda: ride.complete(session, context, user, target_id),
    )


@router.post("/rides/{target_id}/abort", response_model=dict[str, Any])
def abort_ride(
    target_id: str, payload: Reason, session: Db, context: Ctx, user: Actor, key: Key = None
) -> dict:
    require_role(user, "DRIVER")

    def action() -> dict:
        target = session.get(Plan, target_id) or session.get(ScheduledTrip, target_id)
        if target is None or target.driver_id != user.id:
            raise DomainError("NOT_FOUND", status=404)
        members = list(
            session.scalars(
                select(Booking).where(
                    (
                        Booking.ride_plan_id
                        if isinstance(target, Plan)
                        else Booking.scheduled_trip_id
                    )
                    == target.id,
                    Booking.ride_status.in_(["HELD", "CONFIRMED", "RIDE_STARTED"]),
                )
            )
        )
        for b in members:
            ride.cancel_booking(session, context, user, b.id, driver_fault=True)
        target.status = "PLAN_ABORTED" if isinstance(target, Plan) else "CANCELLED_BY_DRIVER"
        audit(
            session,
            "DRIVER_ABORT",
            target.id,
            context.clock.now(),
            {"reason_code": payload.reason_code},
        )
        return {"id": target.id, "status": target.status}

    return idempotent(
        session, context, user, key, f"POST /rides/{target_id}/abort", payload.model_dump(), action
    )


@router.post("/rides/{plan_id}/coriders/{booking_id}/decline", response_model=dict[str, Any])
def decline(
    plan_id: str,
    booking_id: str,
    payload: Reason,
    session: Db,
    context: Ctx,
    user: Actor,
    key: Key = None,
) -> dict:
    require_role(user, "DRIVER")
    return idempotent(
        session,
        context,
        user,
        key,
        f"POST /rides/{plan_id}/coriders/{booking_id}/decline",
        payload.model_dump(),
        lambda: ride.decline_corider(
            session, context, user, plan_id, booking_id, payload.reason_code
        ),
    )


@router.get("/driver/earnings", response_model=dict[str, Any])
def earnings(session: Db, user: Actor) -> dict:
    require_role(user, "DRIVER")
    entries = [
        {"booking_id": p.booking_id, **p.data}
        for p in session.scalars(select(Payout).where(Payout.driver_id == user.id))
    ]
    return {
        "total_driver_payout_vnd": sum(p["total_driver_payout_vnd"] for p in entries),
        "guarantee_total_vnd": sum(p["guarantee_amount_vnd"] for p in entries),
        "payouts": entries,
    }
