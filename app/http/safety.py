import hashlib
import secrets
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.domain.errors import DomainError
from app.http.dependencies import Actor, Ctx, Db, Key
from app.models import (
    Auxiliary,
    Booking,
    Driver,
)
from app.schemas import (
    Rating,
)
from app.security import authenticate
from app.services import booking as booking_service
from app.services.common import booking_view, idempotent, owned_booking

router = APIRouter()


@router.post("/bookings/{booking_id}/sos", response_model=dict[str, Any])
def sos(booking_id: str, session: Db, context: Ctx, user: Actor, key: Key = None) -> dict:
    def action() -> dict:
        owned_booking(session, user, booking_id)
        record = Auxiliary(
            kind="SOS",
            owner_id=user.id,
            target_id=booking_id,
            data={"status": "OPEN", "simulated": True},
            created_at=context.clock.now(),
        )
        session.add(record)
        session.flush()
        return {
            "id": record.id,
            "status": "OPEN",
            "simulated": True,
            "message": "Đã ghi nhận cảnh báo mô phỏng; không liên hệ dịch vụ khẩn cấp.",
        }

    return idempotent(session, context, user, key, f"POST /bookings/{booking_id}/sos", {}, action)


@router.post("/bookings/{booking_id}/share-link", response_model=dict[str, Any])
def share(booking_id: str, session: Db, context: Ctx, user: Actor, key: Key = None) -> dict:
    def action() -> dict:
        owned_booking(session, user, booking_id)
        raw = secrets.token_urlsafe(32)
        session.add(
            Auxiliary(
                kind="SHARE",
                owner_id=user.id,
                target_id=booking_id,
                data={
                    "hash": hashlib.sha256(raw.encode()).hexdigest(),
                    "expires_at": context.clock.now() + 3600,
                },
                created_at=context.clock.now(),
            )
        )
        return {"url": f"/share/{raw}", "token": raw, "expires_at": context.clock.now() + 3600}

    return idempotent(
        session, context, user, key, f"POST /bookings/{booking_id}/share-link", {}, action
    )


@router.get("/shared/{token}", response_model=dict[str, Any])
def shared(token: str, session: Db, context: Ctx) -> dict:
    if len(token) > 128:
        raise DomainError("NOT_FOUND", status=404)
    digest = hashlib.sha256(token.encode()).hexdigest()
    record = next(
        (
            r
            for r in session.scalars(select(Auxiliary).where(Auxiliary.kind == "SHARE"))
            if secrets.compare_digest(r.data["hash"], digest)
            and r.data["expires_at"] > context.clock.now()
        ),
        None,
    )
    if record is None:
        raise DomainError("NOT_FOUND", status=404)
    booking = session.get(Booking, record.target_id)
    driver = session.get(Driver, booking.driver_id) if booking.driver_id else None
    position = (
        {"lat": driver.lat, "lon": driver.lon}
        if driver and booking.ride_status == "RIDE_STARTED"
        else None
    )
    return {
        "booking_id": booking.id,
        "service_code": booking.service_code,
        "ride_status": booking.ride_status,
        "driver_position": position,
        "expires_at": record.data["expires_at"],
    }


@router.post("/bookings/{booking_id}/rating", response_model=dict[str, Any])
def rating(
    booking_id: str, payload: Rating, session: Db, context: Ctx, user: Actor, key: Key = None
) -> dict:
    def action() -> dict:
        booking = owned_booking(session, user, booking_id, True)
        if booking.ride_status != "COMPLETED":
            raise DomainError("RATING_REQUIRES_COMPLETION")
        if session.scalar(
            select(Auxiliary).where(
                Auxiliary.kind == "RATING",
                Auxiliary.owner_id == user.id,
                Auxiliary.target_id == booking_id,
            )
        ):
            raise DomainError("ALREADY_RATED")
        row = Auxiliary(
            kind="RATING",
            owner_id=user.id,
            target_id=booking_id,
            data=payload.model_dump(),
            created_at=context.clock.now(),
        )
        session.add(row)
        session.flush()
        return {"id": row.id, **row.data}

    return idempotent(
        session,
        context,
        user,
        key,
        f"POST /bookings/{booking_id}/rating",
        payload.model_dump(),
        action,
    )


@router.post("/bookings/{booking_id}/dispute", response_model=dict[str, Any])
def dispute(booking_id: str, session: Db, context: Ctx, user: Actor, key: Key = None) -> dict:
    def action() -> dict:
        row = owned_booking(session, user, booking_id, True)
        if row.escrow_status not in {
            "DEPOSITED",
            "LOCKED",
            "TOPPED_UP",
        } or not row.price_status.endswith("LOCKED"):
            raise DomainError("ESCROW_NOT_DISPUTABLE")
        row.escrow_status = "DISPUTED"
        booking_service.escrow_command(session, context, row, "DISPUTE", {})
        return booking_view(session, row)

    return idempotent(
        session, context, user, key, f"POST /bookings/{booking_id}/dispute", {}, action
    )


@router.websocket("/bookings/{booking_id}/events")
async def booking_events(websocket: WebSocket, booking_id: str) -> None:
    import asyncio

    context = websocket.app.state.context
    origin = websocket.headers.get("origin")
    if origin and origin not in context.settings.allowed_origins:
        await websocket.close(code=1008)
        return
    try:
        with context.db.transaction() as session:
            user = authenticate(session, context, websocket.cookies.get("rise_access"))
            owned_booking(session, user, booking_id)
        await websocket.accept()
        while True:
            with context.db.transaction() as session:
                fresh_user = authenticate(session, context, websocket.cookies.get("rise_access"))
                row = owned_booking(session, fresh_user, booking_id)
                data = booking_view(session, row)
            await websocket.send_json(data)
            await asyncio.sleep(2)
    except DomainError:
        await websocket.close(code=1008)
    except WebSocketDisconnect:
        return
