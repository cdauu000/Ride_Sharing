import hashlib

from fastapi import APIRouter, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.context import Context
from app.domain.errors import DomainError
from app.http.dependencies import Actor, Ctx, Db
from app.models import (
    AuthSession,
    User,
)
from app.schemas import (
    Login,
    Register,
    UserView,
)
from app.security import issue_tokens, login, register, user_view

router = APIRouter()


def cookies(response: Response, session: Session, context: Context, user: User) -> None:
    access, refresh = issue_tokens(session, context, user)
    response.set_cookie(
        "rise_access",
        access,
        max_age=900,
        httponly=True,
        secure=context.settings.secure_cookies,
        samesite="strict",
        path="/",
    )
    response.set_cookie(
        "rise_refresh",
        refresh,
        max_age=30 * 86400,
        httponly=True,
        secure=context.settings.secure_cookies,
        samesite="strict",
        path="/api/auth",
    )


@router.post("/auth/register", response_model=UserView, status_code=201)
def register_user(payload: Register, response: Response, session: Db, context: Ctx) -> dict:
    user = register(session, payload, context.clock.now())
    cookies(response, session, context, user)
    return user_view(user)


@router.post("/auth/login", response_model=UserView)
def login_user(payload: Login, response: Response, session: Db, context: Ctx) -> dict:
    user = login(session, payload.email, payload.password)
    cookies(response, session, context, user)
    return user_view(user)


@router.post("/auth/refresh", response_model=UserView)
def refresh_user(request: Request, response: Response, session: Db, context: Ctx) -> dict:
    raw = request.cookies.get("rise_refresh", "")
    record = session.scalar(
        select(AuthSession)
        .where(AuthSession.refresh_hash == hashlib.sha256(raw.encode()).hexdigest())
        .with_for_update()
    )
    if not record or record.revoked or record.expires_at <= context.clock.now():
        raise DomainError("UNAUTHENTICATED", status=401)
    record.revoked = True
    user = session.get(User, record.user_id)
    cookies(response, session, context, user)
    return user_view(user)


@router.get("/auth/me", response_model=UserView)
def me(user: Actor) -> dict:
    return user_view(user)


@router.post("/auth/logout", response_model=dict[str, bool])
def logout(user: Actor, session: Db, response: Response) -> dict:
    for row in session.scalars(select(AuthSession).where(AuthSession.user_id == user.id)):
        row.revoked = True
    response.delete_cookie("rise_access", path="/")
    response.delete_cookie("rise_refresh", path="/api/auth")
    return {"ok": True}
