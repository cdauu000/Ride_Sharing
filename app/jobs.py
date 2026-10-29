"""Durable DB outbox/scheduler, per-job leases, retry, and receipt reconciliation."""

import threading
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.context import Context, audit, schedule
from app.domain.errors import DomainError
from app.escrow import EscrowCommand, EscrowError, EscrowRejected
from app.models import (
    Booking,
    FundAccount,
    Job,
    Offer,
    Payout,
    Plan,
    ScheduledTrip,
    SeatHold,
)
from app.services.booking import escrow_command, lock_cascade_drivers, next_offer
from app.services.common import locked
from app.services.fund import post_entry
from app.services.intercity import (
    active_bookings,
    cancel_low_demand,
    close_trip,
    offer_topup,
    optimize_order,
    recover_topup,
)


class DeferredJob(Exception):
    """An earlier outbox command is still in progress; this is not a failed attempt."""


def _command(session: Session, context: Context, job: Job) -> None:
    predecessor = job.data.get("predecessor")
    if predecessor:
        previous = session.scalar(select(Job).where(Job.idempotency_key == predecessor))
        if previous is None or previous.status not in {"COMPLETED", "COMPLETED_NOOP"}:
            raise DeferredJob()
    session.scalar(select(FundAccount).where(FundAccount.id == 1).with_for_update())
    initial = session.get(Booking, job.target_id)
    if initial.ride_plan_id:
        locked(session, Plan, initial.ride_plan_id)
    if initial.scheduled_trip_id:
        locked(session, ScheduledTrip, initial.scheduled_trip_id)
    booking = locked(session, Booking, job.target_id)
    payload = job.data
    params = dict(payload["params"])
    if context.wallets:
        for key in ("passenger", "driver"):
            if key in params:
                params[key] = context.wallets.address(params[key])
    command = EscrowCommand(payload["operation_id"], payload["action"], booking.id, params)
    action = command.action
    # Money-changing operations serialize with ledger appends across workers.
    if action == "RELEASE" and (
        booking.ride_status != "COMPLETED" or not booking.price_status.endswith("LOCKED")
    ):
        raise DomainError("RELEASE_GATE_REJECTED")
    if action == "REVERT_TOPUP" and not context.escrow.get(booking.id).get("topup_mode"):
        # Its predecessor definitively failed, or cancellation already refunded it.
        snapshot = context.escrow.get(booking.id)
        receipt = None
    else:
        receipt = context.escrow.execute(command)
        if receipt.status != "CONFIRMED":
            raise DomainError("ESCROW_RECEIPT_PENDING", status=503)
        snapshot = receipt.snapshot
    booking.escrow_status = snapshot["status"]
    booking.data = {
        **booking.data,
        "escrow": snapshot,
        "escrow_tx_hash": receipt.tx_hash if receipt else booking.data.get("escrow_tx_hash"),
        "escrow_mode": receipt.mode if receipt else context.escrow.mode,
    }
    if action == "TOPUP":
        booking.final_price_vnd = snapshot["final_vnd"]
        booking.current_estimated_price_vnd = booking.final_price_vnd
        booking.price_status = "TOPUP_LOCKED"
        session.flush()
        trip = locked(session, ScheduledTrip, booking.scheduled_trip_id)
        bookings = active_bookings(session, trip.id)
        if (
            not trip.data.get("topup_reverting")
            and trip.status == "TOPUP_OFFERED"
            and bookings
            and all(
                b.price_status == "TOPUP_LOCKED" and b.escrow_status == "TOPPED_UP"
                for b in bookings
            )
        ):
            trip.status = "CONFIRMED_TOPUP"
            trip.data = {**trip.data, "topup_funding": False}
            trip.plan_version += 1
    if action == "REVERT_TOPUP":
        booking.final_price_vnd = snapshot["final_vnd"]
        booking.current_estimated_price_vnd = booking.final_price_vnd
        booking.price_status = "FIXED_LOCKED"
        booking.data = {**booking.data, "topup_reverted": True, "topup_accepted": False}
        session.flush()
        trip = locked(session, ScheduledTrip, booking.scheduled_trip_id)
        bookings = active_bookings(session, trip.id)
        if all(not b.data.get("topup_accepted") for b in bookings):
            trip.data = {**trip.data, "topup_funding": False, "topup_reverting": False}
            trip.plan_version += 1
    if action in {"RELEASE", "CANCEL", "RESOLVE"}:
        contribution = snapshot.get("fund_contribution_vnd", 0)
        guarantee = snapshot.get("guarantee_vnd", 0)
        post_entry(
            session,
            command.operation_id + ":fund",
            booking.id,
            "CANCEL_FEE_INFLOW" if action == "CANCEL" else "CONTRIBUTION",
            contribution,
            context.clock.now(),
        )
        post_entry(
            session,
            command.operation_id + ":guarantee",
            booking.id,
            "GUARANTEE_PAYOUT",
            -guarantee,
            context.clock.now(),
        )
        if session.get(Payout, booking.id) is None:
            gross = booking.cancellation_fee_vnd if action == "CANCEL" else booking.final_price_vnd
            session.add(
                Payout(
                    booking_id=booking.id,
                    driver_id=booking.driver_id,
                    data={
                        "gross_fare_charged_vnd": gross,
                        "driver_base_amount_vnd": snapshot["driver_paid_vnd"] - guarantee,
                        "guarantee_amount_vnd": guarantee,
                        "total_driver_payout_vnd": snapshot["driver_paid_vnd"],
                        "platform_net_amount_vnd": snapshot["platform_paid_vnd"],
                        "fund_contribution_vnd": contribution,
                        "tx_hash": receipt.tx_hash,
                        "mode": receipt.mode,
                    },
                )
            )
    audit(
        session,
        "ESCROW_" + action,
        booking.id,
        context.clock.now(),
        {"tx_hash": receipt.tx_hash if receipt else None, "mode": context.escrow.mode},
    )


def handle(session: Session, context: Context, job: Job) -> None:
    if job.job_type == "ESCROW_COMMAND":
        _command(session, context, job)
    elif job.job_type == "OFFER_TIMEOUT":
        initial = session.get(Offer, job.target_id)
        lock_cascade_drivers(session, session.get(Booking, initial.booking_id))
        plan = locked(session, Plan, initial.plan_id)
        offer = locked(session, Offer, job.target_id)
        if offer.status != "PENDING":
            return
        booking = locked(session, Booking, offer.booking_id)
        if booking.ride_status != "HELD":
            return
        hold = session.scalar(
            select(SeatHold).where(SeatHold.offer_id == offer.id).with_for_update()
        )
        hold.status = "RELEASED"
        offer.status = "EXPIRED"
        plan.status = "PLAN_ABORTED"
        plan.plan_version += 1
        session.flush()
        next_offer(session, context, booking)
    elif job.job_type == "ESCROW_TIMEOUT":
        initial = session.get(Booking, job.target_id)
        if initial.ride_plan_id:
            locked(session, Plan, initial.ride_plan_id)
        if initial.scheduled_trip_id:
            locked(session, ScheduledTrip, initial.scheduled_trip_id)
        booking = locked(session, Booking, job.target_id)
        if booking.ride_status == "CONFIRMED" and booking.escrow_status in {
            "DEPOSIT_PENDING",
            "ESCROW_FAILED",
        }:
            booking.ride_status = "CANCELLED_BY_SYSTEM"
            booking.data = {**booking.data, "cancellation_reason": "ESCROW_TIMEOUT"}
            escrow_command(
                session,
                context,
                booking,
                "CANCEL",
                {"fee_vnd": 0, "driver_vnd": 0, "platform_vnd": 0, "fund_vnd": 0},
            )
            if booking.scheduled_trip_id:
                trip = locked(session, ScheduledTrip, booking.scheduled_trip_id)
                trip.seats_booked -= booking.seat_count
                trip.plan_version += 1
            if booking.ride_plan_id:
                plan = locked(session, Plan, booking.ride_plan_id)
                if not session.scalar(
                    select(Booking).where(
                        Booking.ride_plan_id == plan.id,
                        Booking.id != booking.id,
                        Booking.ride_status.in_(["CONFIRMED", "RIDE_STARTED"]),
                    )
                ):
                    plan.status = "PLAN_ABORTED"
                plan.plan_version += 1
    elif job.job_type.startswith("INTERCITY_"):
        # Serialize merge decisions; rows in the same corridor may otherwise lock each other.
        session.scalar(select(FundAccount).where(FundAccount.id == 1).with_for_update())
        trip = locked(session, ScheduledTrip, job.target_id)
        if job.job_type == "INTERCITY_CLOSE":
            close_trip(session, context, trip)
        elif job.job_type == "INTERCITY_MERGE_END" and trip.status == "MERGE_PENDING_CONFIRMATION":
            if trip.seats_booked >= trip.min_seats_to_run:
                trip.status = "CONFIRMED"
            else:
                offer_topup(session, context, trip)
        elif job.job_type == "INTERCITY_TOPUP_END" and trip.status == "TOPUP_OFFERED":
            if trip.data.get("topup_funding"):
                recover_topup(session, context, trip)
            else:
                trip.status = "UNDER_MIN_DRIVER_DECISION"
        elif job.job_type == "INTERCITY_DRIVER_DEADLINE" and trip.status in {
            "TOPUP_OFFERED",
            "UNDER_MIN_DRIVER_DECISION",
            "MERGE_PENDING_CONFIRMATION",
            "OPEN_FOR_BOOKING",
        }:
            cancel_low_demand(session, context, trip)
        elif job.job_type == "INTERCITY_FIX_ORDER" and trip.status in {
            "CONFIRMED",
            "CONFIRMED_TOPUP",
            "CONFIRMED_UNDER_MIN",
        }:
            order = optimize_order(session, context, trip)
            if order is None:
                # Never depart on a plan that violates committed passenger constraints.
                cancel_low_demand(session, context, trip)
            else:
                trip.data = {
                    **trip.data,
                    **order,
                    "pickup_order_fixed": True,
                    "completed_stop_index": -1,
                    "current": trip.data["origin"],
                    "tracking": {},
                }
                trip.status = "PICKUP_ORDER_FIXED"
                trip.plan_version += 1
    elif job.job_type == "RECONCILE":
        account = session.scalar(select(FundAccount).where(FundAccount.id == 1).with_for_update())
        if account.balance_vnd != context.escrow.fund_balance_vnd:
            raise DomainError("ESCROW_FUND_RECONCILIATION_MISMATCH", status=503)
        schedule(
            session,
            "RECONCILE",
            "system",
            context.clock.now() + 300,
            f"reconcile:{int(context.clock.now() // 300) + 1}",
        )
    elif job.job_type == "BATCH_MATCH":
        from app.services.batch import run_batch

        run_batch(session, context)
        schedule(
            session,
            "BATCH_MATCH",
            "system",
            context.clock.now() + 30,
            f"batch:{int(context.clock.now() // 30) + 1}",
        )
    else:
        raise DomainError("UNKNOWN_JOB_TYPE", status=500)


def tick(context: Context, limit: int = 50) -> dict[str, int]:
    counts = {"completed": 0, "failed": 0, "reaped": 0}
    for _ in range(limit):
        with context.db.transaction() as session:
            stale = list(
                session.scalars(
                    select(Job)
                    .where(Job.status == "PROCESSING", Job.run_at <= context.clock.now() - 60)
                    .with_for_update(skip_locked=True)
                    .limit(20)
                )
            )
            for job in stale:
                job.status = "FAILED_RETRY"
                counts["reaped"] += 1
            job = session.scalar(
                select(Job)
                .where(
                    Job.status.in_(["PENDING", "FAILED_RETRY"]), Job.run_at <= context.clock.now()
                )
                .order_by(Job.run_at, Job.data["sequence"].as_integer(), Job.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if job is None:
                break
            job.status = "PROCESSING"
            job.attempts += 1
            job.run_at = context.clock.now()
            job_id = job.id
        try:
            with context.db.transaction() as session:
                job = locked(session, Job, job_id)
                handle(session, context, job)
                job.status = "COMPLETED"
                job.last_error = None
            counts["completed"] += 1
        except DeferredJob:
            with context.db.transaction() as session:
                job = locked(session, Job, job_id)
                job.status = "PENDING"
                job.attempts -= 1
                job.run_at = context.clock.now() + 0.1
        except Exception as exc:
            with context.db.transaction() as session:
                job = locked(session, Job, job_id)
                if (
                    isinstance(exc, EscrowRejected)
                    and job.job_type == "ESCROW_COMMAND"
                    and job.data.get("action") == "TOPUP"
                ):
                    # Only a proved rejection permits successors to run. Timeouts
                    # and unknown transaction outcomes stay in the retry queue.
                    session.scalar(select(FundAccount).where(FundAccount.id == 1).with_for_update())
                    booking = session.get(Booking, job.target_id)
                    trip = locked(session, ScheduledTrip, booking.scheduled_trip_id)
                    job.status = "COMPLETED_NOOP"
                    job.last_error = str(exc)[:100]
                    if trip.status != "CANCELLED_LOW_DEMAND":
                        recover_topup(session, context, trip)
                    audit(
                        session,
                        "TOPUP_DEFINITIVELY_REJECTED",
                        booking.id,
                        context.clock.now(),
                        {"operation_id": job.idempotency_key, "reason": job.last_error},
                    )
                    counts["failed"] += 1
                    continue
                job.status = "DEAD_LETTER" if job.attempts >= job.max_attempts else "FAILED_RETRY"
                job.last_error = (
                    exc.code
                    if isinstance(exc, DomainError)
                    else str(exc)[:100]
                    if isinstance(exc, EscrowError)
                    else type(exc).__name__
                )
                job.run_at = context.clock.now() + min(300, 2**job.attempts)
            counts["failed"] += 1
    return counts


def worker_loop(context: Context, stop: threading.Event) -> None:
    while not stop.wait(0.5):
        tick(context)


def main() -> None:
    from app.config import Settings
    from app.context import create_context, initialize

    context = create_context(Settings())
    with context.db.transaction() as session:
        initialize(session, context.clock.now())
    try:
        while True:
            tick(context)
            time.sleep(0.5)
    finally:
        context.db.engine.dispose()


if __name__ == "__main__":
    main()
