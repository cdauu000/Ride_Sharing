from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter
from sqlalchemy import select

from app.domain.errors import DomainError
from app.http.dependencies import Actor, Ctx, Db, Key
from app.models import (
    Auxiliary,
    ScheduledTrip,
)
from app.schemas import (
    Decision,
    PublishTrip,
    SelectCandidate,
    TopupResponse,
)
from app.security import require_role
from app.services import booking as booking_service
from app.services import intercity
from app.services.common import idempotent

router = APIRouter()


@router.post("/driver/pool-trips", response_model=dict[str, Any], status_code=201)
def publish_trip(
    payload: PublishTrip, session: Db, context: Ctx, user: Actor, key: Key = None
) -> dict:
    require_role(user, "DRIVER")
    return idempotent(
        session,
        context,
        user,
        key,
        "POST /driver/pool-trips",
        payload.model_dump(mode="json"),
        lambda: intercity.trip_view(intercity.publish(session, context, user, payload)),
    )


@router.get("/driver/pool-trips", response_model=list[dict[str, Any]])
def own_trips(session: Db, user: Actor) -> list[dict]:
    require_role(user, "DRIVER")
    return [
        intercity.trip_view(t)
        for t in session.scalars(
            select(ScheduledTrip)
            .where(ScheduledTrip.driver_id == user.id)
            .order_by(ScheduledTrip.departure_time.desc())
            .limit(100)
        )
    ]


@router.get("/intercity/pool-trips", response_model=list[dict[str, Any]])
def search_trips(
    session: Db, context: Ctx, corridor: str | None = None, date: str | None = None, seats: int = 1
) -> list[dict]:
    if not 1 <= seats <= 4:
        raise DomainError("INVALID_SEAT_COUNT", status=422)
    query = select(ScheduledTrip).where(
        ScheduledTrip.status == "OPEN_FOR_BOOKING",
        ScheduledTrip.seats_total - ScheduledTrip.seats_booked >= seats,
        ScheduledTrip.departure_time >= context.clock.now() + 72 * 3600,
    )
    if corridor:
        query = query.where(ScheduledTrip.corridor_id == corridor)
    trips = list(session.scalars(query.order_by(ScheduledTrip.departure_time).limit(100)))
    return [
        intercity.trip_view(t)
        for t in trips
        if not date
        or datetime.fromtimestamp(t.departure_time, timezone(timedelta(hours=7))).date().isoformat()
        == date
    ]


@router.post("/intercity/pool-trips/{trip_id}/book", response_model=dict[str, Any])
def book_trip(
    trip_id: str, payload: SelectCandidate, session: Db, context: Ctx, user: Actor, key: Key = None
) -> dict:
    from app.models import Candidate

    candidate = session.get(Candidate, payload.candidate_id)
    if (
        candidate is None
        or candidate.target_id != trip_id
        or candidate.source_type != "SCHEDULED_INTERCITY_TRIP"
    ):
        raise DomainError("NOT_FOUND", status=404)
    return idempotent(
        session,
        context,
        user,
        key,
        f"POST /intercity/pool-trips/{trip_id}/book",
        payload.model_dump(),
        lambda: booking_service.choose(session, context, user, candidate.run_id, candidate.id),
    )


@router.get("/intercity/topup-offers", response_model=list[dict[str, Any]])
def topups(session: Db, user: Actor) -> list[dict]:
    return [
        {"id": row.id, "trip_id": row.target_id, **row.data}
        for row in session.scalars(
            select(Auxiliary).where(Auxiliary.kind == "TOPUP", Auxiliary.owner_id == user.id)
        )
    ]


@router.post("/intercity/topup-offers/{offer_id}/respond", response_model=dict[str, Any])
def respond_topup(
    offer_id: str, payload: TopupResponse, session: Db, context: Ctx, user: Actor, key: Key = None
) -> dict:
    return idempotent(
        session,
        context,
        user,
        key,
        f"POST /intercity/topup-offers/{offer_id}/respond",
        payload.model_dump(),
        lambda: intercity.respond_topup(session, context, user, offer_id, payload.decision),
    )


@router.post("/driver/pool-trips/{trip_id}/under-min-decision", response_model=dict[str, Any])
def under_min(
    trip_id: str, payload: Decision, session: Db, context: Ctx, user: Actor, key: Key = None
) -> dict:
    require_role(user, "DRIVER")
    return idempotent(
        session,
        context,
        user,
        key,
        f"POST /driver/pool-trips/{trip_id}/under-min-decision",
        payload.model_dump(),
        lambda: intercity.driver_decision(session, context, user, trip_id, payload.decision),
    )
