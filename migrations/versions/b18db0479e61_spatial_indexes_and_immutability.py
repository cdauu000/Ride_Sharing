"""PostGIS generated geometry, spatial indexes, immutable financial snapshots.

Revision ID: b18db0479e61
Revises: ad6336cd5a28
"""

from alembic import op

revision = "b18db0479e61"
down_revision = "ad6336cd5a28"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute(
        "ALTER TABLE driver_profiles ADD COLUMN location_geom geometry(Point,4326) GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(lon,lat),4326)) STORED"
    )
    op.execute(
        "CREATE INDEX idx_driver_locations_geom ON driver_profiles USING GIST (location_geom)"
    )
    op.execute(
        "CREATE INDEX idx_driver_locations_geography ON driver_profiles USING GIST ((location_geom::geography))"
    )
    op.execute("""CREATE TABLE service_areas (
        kind text PRIMARY KEY, geom geometry(Geometry,4326) NOT NULL,
        source_sha256 text NOT NULL, validation_status text NOT NULL)""")
    op.execute("CREATE INDEX idx_service_areas_geom ON service_areas USING GIST (geom)")
    op.execute(
        "CREATE INDEX idx_scheduled_jobs_due ON scheduled_jobs (run_at) WHERE status IN ('PENDING','FAILED_RETRY')"
    )
    op.execute(
        "CREATE INDEX idx_scheduled_trips_search ON scheduled_trips (corridor_id,departure_time) WHERE status='OPEN_FOR_BOOKING'"
    )
    op.execute("""CREATE FUNCTION rise_reject_immutable_change() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'Immutable record: create a new version or compensating ledger entry'; END $$""")
    for table in ("pricing_configs", "ride_candidates", "fund_ledger"):
        op.execute(
            f"CREATE TRIGGER immutable_{table} BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION rise_reject_immutable_change()"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in ("pricing_configs", "ride_candidates", "fund_ledger"):
        op.execute(f"DROP TRIGGER immutable_{table} ON {table}")
    op.execute("DROP FUNCTION rise_reject_immutable_change()")
    op.execute("DROP INDEX idx_scheduled_trips_search")
    op.execute("DROP INDEX idx_scheduled_jobs_due")
    op.execute("DROP TABLE service_areas")
    op.execute("DROP INDEX idx_driver_locations_geography")
    op.execute("DROP INDEX idx_driver_locations_geom")
    op.execute("ALTER TABLE driver_profiles DROP COLUMN location_geom")
