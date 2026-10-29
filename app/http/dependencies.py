from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.context import Context
from app.models import (
    Driver,
    User,
)
from app.schemas import (
    DriverSettings,
)
from app.security import authenticate


def context_dependency(request: Request) -> Context:
    return request.app.state.context


def session_dependency(request: Request):
    with request.app.state.context.db.transaction() as session:
        yield session


Ctx = Annotated[Context, Depends(context_dependency)]


Db = Annotated[Session, Depends(session_dependency)]


def actor_dependency(request: Request, context: Ctx, session: Db) -> User:
    return authenticate(session, context, request.cookies.get("rise_access"))


Actor = Annotated[User, Depends(actor_dependency)]


Key = Annotated[str | None, Header(alias="Idempotency-Key")]


def driver_view(driver: Driver) -> dict:
    return {
        name: getattr(driver, name)
        for name in (
            *DriverSettings.model_fields,
            "id",
            "vehicle_type",
            "capacity",
            "kyc_status",
            "license_plate",
        )
    }
