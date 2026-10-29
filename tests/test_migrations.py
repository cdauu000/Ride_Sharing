import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect


def test_upgrade_fresh_database_and_compile_postgis(tmp_path: Path) -> None:
    target = tmp_path / "migration.db"
    env = {**os.environ, "RISE_DATABASE_URL": "sqlite:///" + str(target)}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env=env,
        check=True,
        capture_output=True,
    )
    engine = create_engine(env["RISE_DATABASE_URL"])
    tables = set(inspect(engine).get_table_names())
    assert {
        "bookings",
        "scheduled_jobs",
        "fund_ledger",
        "ride_candidates",
        "alembic_version",
    } <= tables
    engine.dispose()
    env["RISE_DATABASE_URL"] = "postgresql+psycopg://compile:compile@localhost/compile"
    sql = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert "CREATE EXTENSION IF NOT EXISTS postgis" in sql
    assert "USING GIST" in sql and "CREATE TRIGGER immutable_ride_candidates" in sql
