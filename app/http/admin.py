from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request
from pydantic import Field
from sqlalchemy import func, select

from app.context import audit
from app.domain.errors import DomainError
from app.http.dependencies import Actor, Ctx, Db, Key, driver_view
from app.jobs import tick
from app.models import (
    Auxiliary,
    Booking,
    Driver,
    FundAccount,
    FundEntry,
    Job,
    Payout,
    ScheduledTrip,
    User,
)
from app.schemas import (
    DisputeAllocation,
    InputModel,
    KycReview,
)
from app.security import authenticate, require_role, user_view
from app.services import booking as booking_service
from app.services import intercity
from app.services.common import idempotent, locked, owned_booking
from research.survey import (
    SurveyResponse,
    survey_quality,
)

router = APIRouter()


@router.get("/admin/users", response_model=list[dict[str, Any]])
def admin_users(session: Db, user: Actor) -> list[dict]:
    require_role(user, "ADMIN")
    result = []
    for account in session.scalars(select(User).order_by(User.created_at).limit(200)):
        driver = session.get(Driver, account.id)
        result.append(
            {
                **user_view(account),
                **(
                    {
                        "driver": driver_view(driver),
                        "kyc_status": driver.kyc_status,
                        "vehicle_type": driver.vehicle_type,
                    }
                    if driver
                    else {}
                ),
            }
        )
    return result


@router.post("/admin/drivers/{driver_id}/kyc-review", response_model=dict[str, Any])
def kyc(
    driver_id: str, payload: KycReview, session: Db, context: Ctx, user: Actor, key: Key = None
) -> dict:
    require_role(user, "ADMIN")

    def action() -> dict:
        driver = locked(session, Driver, driver_id)
        driver.kyc_status = payload.status
        session.get(User, driver_id).gender = payload.verified_gender
        if payload.status != "VERIFIED":
            driver.pool_enabled = False
            driver.accepts_intercity = False
        audit(session, "KYC_REVIEW", driver.id, context.clock.now(), {"status": payload.status})
        return driver_view(driver)

    return idempotent(
        session,
        context,
        user,
        key,
        f"POST /admin/drivers/{driver_id}/kyc-review",
        payload.model_dump(),
        action,
    )


@router.get("/admin/fund", response_model=dict[str, Any])
def fund(session: Db, user: Actor) -> dict:
    require_role(user, "ADMIN")
    entries = list(
        session.scalars(
            select(FundEntry).order_by(FundEntry.created_at.desc(), FundEntry.id).limit(200)
        )
    )
    completed = list(
        session.scalars(
            select(Booking).where(
                Booking.service_code == "CAR_URBAN_POOL", Booking.ride_status == "COMPLETED"
            )
        )
    )
    matched = [b for b in completed if b.price_status == "MATCHED_LOCKED"]
    unmatched = [b for b in completed if b.price_status == "UNMATCHED_LOCKED"]
    contributions = [
        session.get(Payout, b.id).data["fund_contribution_vnd"]
        for b in matched
        if session.get(Payout, b.id)
    ]
    guarantees = [
        session.get(Payout, b.id).data["guarantee_amount_vnd"]
        for b in unmatched
        if session.get(Payout, b.id)
    ]
    income = sum(contributions) / len(contributions) if contributions else None
    expense = sum(guarantees) / len(guarantees) if guarantees else None
    m = len(matched) / len({b.ride_plan_id for b in matched}) if matched else 2
    star = (
        expense / (expense + income)
        if expense is not None and income is not None and expense + income > 0
        else None
    )
    return {
        "balance_vnd": session.get(FundAccount, 1).balance_vnd,
        "ledger": [
            {
                name: getattr(e, name)
                for name in (
                    "id",
                    "booking_id",
                    "entry_type",
                    "amount_signed_vnd",
                    "balance_after_vnd",
                    "created_at",
                )
            }
            for e in entries
        ],
        "p_actual_booking": len(matched) / len(completed) if completed else None,
        "p_star_booking": star,
        "p_star_ride": expense / (expense + m * income) if star is not None else None,
    }


@router.get("/admin/metrics", response_model=dict[str, Any])
def metrics(session: Db, user: Actor) -> dict:
    require_role(user, "ADMIN")
    totals = {
        status: count
        for status, count in session.execute(
            select(Booking.ride_status, func.count()).group_by(Booking.ride_status)
        )
    }
    return {
        "bookings_by_status": totals,
        "total_bookings": sum(totals.values()),
        "active_drivers": session.scalar(
            select(func.count()).select_from(Driver).where(Driver.online.is_(True))
        ),
        "jobs_by_status": {
            status: count
            for status, count in session.execute(
                select(Job.status, func.count()).group_by(Job.status)
            )
        },
        "services": {
            s: count
            for s, count in session.execute(
                select(Booking.service_code, func.count()).group_by(Booking.service_code)
            )
        },
    }


@router.get("/admin/jobs", response_model=list[dict[str, Any]])
def jobs(session: Db, user: Actor) -> list[dict]:
    require_role(user, "ADMIN")
    return [
        {
            name: getattr(j, name)
            for name in (
                "id",
                "job_type",
                "target_id",
                "run_at",
                "status",
                "attempts",
                "max_attempts",
                "last_error",
            )
        }
        for j in session.scalars(select(Job).order_by(Job.run_at.desc()).limit(200))
    ]


@router.post("/admin/jobs/{job_id}/retry", response_model=dict[str, Any])
def retry_job(job_id: str, session: Db, context: Ctx, user: Actor, key: Key = None) -> dict:
    require_role(user, "ADMIN")

    def action() -> dict:
        job = locked(session, Job, job_id)
        if job.status not in {"DEAD_LETTER", "FAILED_RETRY"}:
            raise DomainError("JOB_NOT_RETRYABLE")
        job.status = "PENDING"
        job.attempts = 0
        job.run_at = context.clock.now()
        # Preserve the original operation, payload and predecessor. The adapter
        # journal replays the same receipt rather than issuing a second payment.
        audit(
            session,
            "JOB_RETRY_REQUESTED",
            job.id,
            context.clock.now(),
            {"operator_id": user.id, "operation_id": job.idempotency_key},
        )
        return {"id": job.id, "status": job.status, "operation_id": job.idempotency_key}

    return idempotent(session, context, user, key, f"POST /admin/jobs/{job_id}/retry", {}, action)


@router.post("/admin/jobs/run", response_model=dict[str, int])
def run_jobs(context: Ctx, request: Request) -> dict:
    # Authenticate separately, then close the DB transaction before worker transactions start.
    with context.db.transaction() as session:
        user = authenticate(session, context, request.cookies.get("rise_access"))
        require_role(user, "ADMIN")
    return tick(context)


class ClockAdvance(InputModel):
    advance_seconds: float = Field(gt=0, le=7 * 86400)


@router.post("/admin/demo-clock", response_model=dict[str, Any])
def advance_clock(payload: ClockAdvance, context: Ctx, session: Db, user: Actor) -> dict:
    require_role(user, "ADMIN")
    if context.settings.environment != "development" or context.settings.escrow_mode != "local":
        raise DomainError("LOCAL_DEMO_ONLY", status=403)
    context.clock.offset += payload.advance_seconds
    return {"server_time": datetime.fromtimestamp(context.clock.now(), UTC).isoformat()}


@router.get("/admin/pool-trips", response_model=list[dict[str, Any]])
def admin_trips(session: Db, user: Actor) -> list[dict]:
    require_role(user, "ADMIN")
    return [
        intercity.trip_view(t)
        for t in session.scalars(
            select(ScheduledTrip).order_by(ScheduledTrip.departure_time.desc()).limit(200)
        )
    ]


@router.get("/admin/models", response_model=dict[str, Any])
def model_status(context: Ctx, user: Actor) -> dict:
    require_role(user, "ADMIN")
    if context.models is None:
        return {
            "active": False,
            "ranking": "BASELINE",
            "reason": "NO_VALIDATED_ARTIFACT_CONFIGURED",
        }
    manifest = {
        key: value
        for key, value in context.models.manifest.items()
        if key not in {"oof_folds", "fulfillment_oof_folds", "code_sha256"}
    }
    return {
        "active": True,
        "ranking": "LGBMRanker",
        "can_multiply_fulfillment": context.models.can_multiply_fulfillment,
        "manifest": manifest,
        "models": [
            {
                "id": context.models.version,
                "name": "LambdaMART / LightGBM",
                "version": context.models.version,
                "status": "Nghiên cứu mô phỏng",
                "metrics": {"ece": manifest.get("match_validation_ece")},
            }
        ],
    }


@router.get("/admin/batch-runs", response_model=list[dict[str, Any]])
def batch_runs(session: Db, user: Actor) -> list[dict]:
    require_role(user, "ADMIN")
    return [
        {"id": r.id, **r.data}
        for r in session.scalars(
            select(Auxiliary)
            .where(Auxiliary.kind == "BATCH_RUN")
            .order_by(Auxiliary.created_at.desc())
            .limit(100)
        )
    ]


@router.get("/admin/surveys", response_model=dict[str, Any])
def surveys(session: Db, user: Actor) -> dict:
    require_role(user, "ADMIN")
    return survey_quality(
        [
            SurveyResponse.model_validate(r.data)
            for r in session.scalars(select(Auxiliary).where(Auxiliary.kind == "SURVEY"))
        ]
    )


@router.get("/admin/safety-incidents", response_model=list[dict[str, Any]])
def safety_incidents(session: Db, user: Actor) -> list[dict]:
    require_role(user, "ADMIN")
    return [
        {"id": row.id, "booking_id": row.target_id, "created_at": row.created_at, **row.data}
        for row in session.scalars(
            select(Auxiliary)
            .where(Auxiliary.kind == "SOS")
            .order_by(Auxiliary.created_at.desc())
            .limit(100)
        )
    ]


@router.post("/admin/disputes/{booking_id}/resolve", response_model=dict[str, Any])
def resolve(
    booking_id: str,
    payload: DisputeAllocation,
    session: Db,
    context: Ctx,
    user: Actor,
    key: Key = None,
) -> dict:
    require_role(user, "ADMIN")

    def action() -> dict:
        row = owned_booking(session, user, booking_id, True)
        if row.escrow_status != "DISPUTED":
            raise DomainError("ESCROW_NOT_DISPUTED")
        balance = row.data.get("escrow", {}).get("balance_vnd", row.final_price_vnd)
        if sum(payload.model_dump().values()) != balance:
            raise DomainError("DISPUTE_ALLOCATION_MISMATCH", status=422)
        booking_service.escrow_command(session, context, row, "RESOLVE", payload.model_dump())
        return {"id": row.id, "resolution": "QUEUED"}

    return idempotent(
        session,
        context,
        user,
        key,
        f"POST /admin/disputes/{booking_id}/resolve",
        payload.model_dump(),
        action,
    )
