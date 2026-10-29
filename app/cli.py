"""Operator commands; bootstrap is restricted to an explicitly local demo."""

import argparse
import os
import secrets

from dotenv import load_dotenv
from sqlalchemy import select

from app.config import ROOT, Settings
from app.context import create_context, initialize
from app.db import Base
from app.models import Driver, User
from app.schemas import Register
from app.security import register


def init_demo() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        password = secrets.token_urlsafe(18)
        env_path.write_text(
            "\n".join(
                [
                    "RISE_ENVIRONMENT=development",
                    "RISE_DATABASE_URL=sqlite:///./rise.db",
                    "RISE_ROUTING_MODE=fixture",
                    "RISE_ESCROW_MODE=local",
                    "RISE_RUN_WORKER=true",
                    f"RISE_JWT_SECRET={secrets.token_urlsafe(48)}",
                    f"RISE_WEBHOOK_SECRET={secrets.token_urlsafe(48)}",
                    f"RISE_DEMO_PASSWORD={password}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
    load_dotenv(env_path)
    settings = Settings()
    if settings.environment != "development" or settings.escrow_mode != "local":
        raise RuntimeError("Demo seed requires development + local escrow")
    password = os.getenv("RISE_DEMO_PASSWORD")
    if not password or len(password) < 12:
        raise RuntimeError("Set RISE_DEMO_PASSWORD (12+ characters) in .env")
    context = create_context(settings)
    Base.metadata.create_all(context.db.engine)
    with context.db.transaction() as session:
        initialize(session, context.clock.now())
        specs = [
            ("passenger", "Hành khách An", "PASSENGER", "CAR4"),
            ("passenger2", "Hành khách Bình", "PASSENGER", "CAR4"),
            ("bike", "Tài xế Minh", "DRIVER", "BIKE"),
            ("driver", "Tài xế Nam", "DRIVER", "CAR4"),
            ("driver2", "Tài xế Hòa", "DRIVER", "CAR4"),
            ("driver3", "Tài xế Linh", "DRIVER", "CAR4"),
            ("admin", "Quản trị viên", "PASSENGER", "CAR4"),
        ]
        for slug, name, role, vehicle in specs:
            email = slug + "@rise.local"
            user = session.scalar(select(User).where(User.email == email))
            if user is not None:
                continue
            user = register(
                session,
                Register(
                    email=email, name=name, password=password, role=role, vehicle_type=vehicle
                ),
                context.clock.now(),
            )
            user.gender = "MALE"
            if slug == "admin":
                user.role = "ADMIN"
            if role == "DRIVER":
                session.flush()
                driver = session.get(Driver, user.id)
                # One car driver plus one bike makes the first manual test
                # deterministic. Operators can enable the other drivers in UI.
                driver.online = slug in {"bike", "driver"}
                driver.kyc_status = "VERIFIED"
                driver.pool_enabled = vehicle == "CAR4"
                driver.accepts_intercity = vehicle == "CAR4"
                driver.lat, driver.lon = 20.961, 105.747
                driver.location_at = context.clock.now()
    context.db.engine.dispose()
    print(
        "Local demo initialized. Accounts: passenger, passenger2, bike, driver, driver2, driver3, admin @rise.local."
    )
    print(
        "Password is RISE_DEMO_PASSWORD in .env. Routing is illustrative; escrow is a local financial simulation."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Rise Sharing operator commands")
    parser.add_argument("command", choices=["init-demo", "check-config"])
    args = parser.parse_args()
    if args.command == "init-demo":
        init_demo()
    else:
        settings = Settings()
        settings.assert_safe()
        print("Configuration syntax and environment guards passed.")


if __name__ == "__main__":
    main()
