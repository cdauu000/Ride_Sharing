import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.context import Context
from app.domain.errors import DomainError
from app.models import AuthSession, Driver, User
from app.schemas import Register

hasher = PasswordHasher()
DUMMY_HASH = hasher.hash(secrets.token_hex(24))


def user_view(user: User) -> dict[str, str]:
    return {"id": user.id, "email": user.email, "name": user.name, "role": user.role}


def register(session: Session, payload: Register, now: float) -> User:
    email = payload.email.strip().casefold()
    if session.scalar(select(User).where(User.email == email)):
        raise DomainError("EMAIL_EXISTS", status=409)
    user = User(
        email=email,
        name=payload.name.strip(),
        password_hash=hasher.hash(payload.password),
        role=payload.role,
        created_at=now,
    )
    session.add(user)
    session.flush()
    if user.role == "DRIVER":
        session.add(
            Driver(
                id=user.id,
                vehicle_type=payload.vehicle_type,
                license_plate="MOCK-" + user.id[:8],
                capacity=1 if payload.vehicle_type == "BIKE" else 4,
            )
        )
    return user


def login(session: Session, email: str, password: str) -> User:
    user = session.scalar(select(User).where(User.email == email.strip().casefold()))
    try:
        hasher.verify(user.password_hash if user else DUMMY_HASH, password)
    except VerificationError as exc:
        raise DomainError("INVALID_CREDENTIALS", "Email hoặc mật khẩu không đúng.", 401) from exc
    if user is None:
        raise DomainError("INVALID_CREDENTIALS", status=401)
    return user


def issue_tokens(session: Session, context: Context, user: User) -> tuple[str, str]:
    raw = secrets.token_urlsafe(48)
    record = AuthSession(
        user_id=user.id,
        refresh_hash=hashlib.sha256(raw.encode()).hexdigest(),
        expires_at=context.clock.now() + 30 * 86400,
    )
    session.add(record)
    session.flush()
    token = jwt.encode(
        {
            "sub": user.id,
            "sid": record.id,
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=15),
            "iss": "rise-sharing",
            "aud": "rise-web",
        },
        context.jwt_secret,
        algorithm="HS256",
    )
    return token, raw


def authenticate(session: Session, context: Context, token: str | None) -> User:
    if not token:
        raise DomainError("UNAUTHENTICATED", status=401)
    try:
        claims: dict[str, Any] = jwt.decode(
            token,
            context.jwt_secret,
            algorithms=["HS256"],
            issuer="rise-sharing",
            audience="rise-web",
            options={"require": ["exp", "sub", "sid"]},
        )
        record = session.get(AuthSession, claims["sid"])
        user = session.get(User, claims["sub"])
        if (
            record is None
            or record.revoked
            or record.expires_at <= context.clock.now()
            or user is None
            or record.user_id != user.id
        ):
            raise DomainError("UNAUTHENTICATED", status=401)
        return user
    except jwt.PyJWTError as exc:
        raise DomainError("UNAUTHENTICATED", status=401) from exc


def require_role(user: User, *roles: str) -> None:
    if user.role not in roles:
        raise DomainError("FORBIDDEN", status=403)
