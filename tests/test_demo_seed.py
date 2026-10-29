from pathlib import Path

import pytest
from sqlalchemy import select

from app import cli
from app.config import Settings
from app.context import create_context
from app.models import Driver, User


def test_demo_seed_is_predictable_and_preserves_existing_operator_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    for key, value in {
        "RISE_DATABASE_URL": f"sqlite:///{tmp_path / 'review.db'}",
        "RISE_ESCROW_JOURNAL_PATH": str(tmp_path / "escrow.db"),
        "RISE_ENVIRONMENT": "development",
        "RISE_ESCROW_MODE": "local",
        "RISE_DEMO_PASSWORD": "Testing-only-password-2026!",
    }.items():
        monkeypatch.setenv(key, value)
    cli.init_demo()
    context = create_context(Settings())
    with context.db.transaction() as session:
        flags = {
            user.email: driver.online
            for user, driver in session.execute(
                select(User, Driver).join(Driver, Driver.id == User.id)
            )
        }
        assert flags == {
            "bike@rise.local": True,
            "driver@rise.local": True,
            "driver2@rise.local": False,
            "driver3@rise.local": False,
        }
        driver = session.scalar(
            select(Driver)
            .join(User, User.id == Driver.id)
            .where(User.email == "driver2@rise.local")
        )
        driver.online = True
    cli.init_demo()
    with context.db.transaction() as session:
        assert (
            session.scalar(
                select(Driver)
                .join(User, User.id == Driver.id)
                .where(User.email == "driver2@rise.local")
            ).online
            is True
        )
    context.db.engine.dispose()
