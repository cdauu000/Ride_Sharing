from dataclasses import replace
from fractions import Fraction
from itertools import combinations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.context import Context, audit
from app.domain.batch_matcher import Bundle, solve_bundles
from app.domain.pooling import insert
from app.domain.pricing import plan_fare
from app.models import Auxiliary, Booking, Driver, Offer, Plan, SeatHold, TripRequest, uid
from app.services.booking import confirm
from app.services.pooling import apply_result, plan_from_row, rider_from_request, serialize_result


def run_batch(session: Session, context: Context) -> dict:
    """Only not-yet-accepted pool offers may move cars; deposited bookings stay put."""
    waiting = list(
        session.scalars(
            select(Booking)
            .where(
                Booking.service_code == "CAR_URBAN_POOL",
                Booking.ride_status == "HELD",
                Booking.escrow_status == "NONE",
            )
            .order_by(Booking.created_at)
            .limit(500)
        )
    )
    plans = list(
        session.scalars(
            select(Plan)
            .where(Plan.service_code == "CAR_URBAN_POOL", Plan.status == "PLAN_OPEN_SEARCHING")
            .order_by(Plan.id)
            .limit(20)
        )
    )
    # Lock every involved aggregate in a stable order before constructing snapshots.
    driver_ids = sorted(
        {p.driver_id for p in plans} | {b.driver_id for b in waiting if b.driver_id}
    )
    if driver_ids:
        session.scalars(
            select(Driver)
            .where(Driver.id.in_(driver_ids))
            .order_by(Driver.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).all()
    ids = sorted({p.id for p in plans} | {b.ride_plan_id for b in waiting if b.ride_plan_id})
    if ids:
        session.scalars(
            select(Plan)
            .where(Plan.id.in_(ids))
            .order_by(Plan.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).all()
    # An offer may have been accepted while this transaction waited for drivers.
    # Re-read under aggregate locks before using the initial candidate snapshot.
    waiting_ids = [b.id for b in waiting]
    waiting = (
        list(
            session.scalars(
                select(Booking)
                .where(
                    Booking.id.in_(waiting_ids),
                    Booking.ride_status == "HELD",
                    Booking.escrow_status == "NONE",
                )
                .order_by(Booking.created_at, Booking.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )
        if waiting_ids
        else []
    )
    plans = [p for p in plans if p.status == "PLAN_OPEN_SEARCHING"]
    snapshots = {p.id: plan_from_row(session, context, p) for p in plans}
    points = [
        point
        for plan in snapshots.values()
        for point in [plan.current, *[s.point for s in plan.stops]]
    ]
    backlog = len(waiting)
    admitted = max(0, (200 - len(set(points))) // 2)
    waiting = waiting[:admitted]
    requests = {b.request_id: session.get(TripRequest, b.request_id) for b in waiting}
    riders = {key: rider_from_request(request) for key, request in requests.items()}
    points.extend(point for rider in riders.values() for point in (rider.pickup, rider.dropoff))
    bundles = []
    if points:
        matrix = context.routing.matrix("car", points)
        for row in plans:
            driver = session.get(Driver, row.driver_id)
            if (
                not driver.online
                or not driver.active
                or not driver.pool_enabled
                or driver.kyc_status != "VERIFIED"
            ):
                continue
            plan = snapshots[row.id]
            singles = {}
            old_cost = plan_fare(
                row.data.get("total_km", max(r.direct_km for r in plan.riders)),
                row.data.get("total_minutes", max(r.direct_minutes for r in plan.riders)),
                len(plan.stops),
            )
            for key, rider in riders.items():
                result = insert(plan, rider, matrix)
                if result:
                    singles[key] = result
                    gain = int(
                        rider.private_fare
                        - (
                            plan_fare(result.total_km, result.total_minutes, len(result.plan.stops))
                            - old_cost
                        )
                    )
                    bundles.append(Bundle(uid(), row.id, (key,), gain, serialize_result(result)))
            for first, second in combinations(sorted(singles), 2):
                result = singles[first]
                updated = replace(
                    result.plan,
                    riders=tuple(
                        replace(r, old_exact=Fraction(result.fares[r.id]["exact"]))
                        if not r.frozen
                        else r
                        for r in result.plan.riders
                    ),
                )
                combined = insert(updated, riders[second], matrix)
                if combined:
                    gain = int(
                        riders[first].private_fare
                        + riders[second].private_fare
                        - (
                            plan_fare(
                                combined.total_km, combined.total_minutes, len(combined.plan.stops)
                            )
                            - old_cost
                        )
                    )
                    bundles.append(
                        Bundle(uid(), row.id, (first, second), gain, serialize_result(combined))
                    )
    solution = solve_bundles(bundles, set(requests))
    assigned = 0
    for bundle in solution.selected:
        target = session.get(Plan, bundle.vehicle_id)
        selected = [b for b in waiting if b.request_id in bundle.request_ids]
        if any(b.ride_status != "HELD" or b.escrow_status != "NONE" for b in selected):
            continue
        for booking in selected:
            original = session.get(Plan, booking.ride_plan_id)
            offers = list(
                session.scalars(
                    select(Offer)
                    .where(Offer.booking_id == booking.id, Offer.status == "PENDING")
                    .with_for_update()
                )
            )
            for offer in offers:
                offer.status = "REASSIGNED_BY_BATCH"
                hold = session.scalar(select(SeatHold).where(SeatHold.offer_id == offer.id))
                hold.status = "RELEASED"
            if original:
                original.status = "PLAN_ABORTED"
                original.plan_version += 1
            booking.ride_plan_id, booking.driver_id = target.id, target.driver_id
            confirm(session, context, booking)
            assigned += 1
        session.flush()
        apply_result(session, target, bundle.payload)
        target.plan_version += 1
        audit(
            session,
            "BATCH_MATCH_RUN_COMPLETED",
            target.id,
            context.clock.now(),
            {"assigned": len(selected)},
        )
    report = {
        "backlog_requests": backlog,
        "requests": len(waiting),
        "bundles": len(bundles),
        "assigned": assigned,
        "solver_status": solution.solver_status,
        "fallback": solution.fallback,
        "eligibility": "HELD_NOT_YET_ACCEPTED_POOL_OFFERS",
    }
    session.add(Auxiliary(kind="BATCH_RUN", data=report, created_at=context.clock.now()))
    return report
