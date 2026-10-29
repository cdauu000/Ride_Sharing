from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.context import create_context
from app.main import create_app
from app.models import Driver
from app.schemas import Register
from app.security import register


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(
        database_url="sqlite:///" + str(tmp_path / "test.db"),
        escrow_journal_path=str(tmp_path / "escrow.db"),
        run_worker=False,
    )
    context = create_context(settings)
    with TestClient(create_app(context=context)) as test:
        yield test


@pytest.fixture
def accounts(client: TestClient) -> dict[str, dict[str, Any]]:
    context = client.app.state.context
    result = {}
    with context.db.transaction() as session:
        for name, role, vehicle in (
            ("passenger", "PASSENGER", "CAR4"),
            ("other", "PASSENGER", "CAR4"),
            ("driver", "DRIVER", "CAR4"),
            ("bike", "DRIVER", "BIKE"),
            ("admin", "PASSENGER", "CAR4"),
        ):
            user = register(
                session,
                Register(
                    email=name + "@test.example",
                    password="Test-password-2026!",
                    name=name,
                    role=role,
                    vehicle_type=vehicle,
                ),
                context.clock.now(),
            )
            if name == "admin":
                user.role = "ADMIN"
            if role == "DRIVER":
                session.flush()
                driver = session.get(Driver, user.id)
                driver.online = True
                driver.kyc_status = "VERIFIED"
                driver.pool_enabled = vehicle == "CAR4"
                driver.accepts_intercity = vehicle == "CAR4"
                driver.lat, driver.lon = 20.961, 105.747
            result[name] = {"id": user.id, "email": user.email, "password": "Test-password-2026!"}
    return result


def login_as(client: TestClient, account: dict) -> None:
    response = client.post(
        "/api/auth/login", json={"email": account["email"], "password": account["password"]}
    )
    assert response.status_code == 200, response.text


def mutate(
    client: TestClient, path: str, payload: dict | None = None, key: str | None = None
) -> Any:
    return client.post(path, json=payload or {}, headers={"Idempotency-Key": key or str(uuid4())})


def intent(**overrides: Any) -> dict:
    return {
        "pickup": {"lat": 20.961, "lon": 105.747},
        "dropoff": {"lat": 21.013, "lon": 105.824},
        "budget_min": 50000,
        "budget_max": 1000000,
        **overrides,
    }
