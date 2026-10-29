import hashlib
import json
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, baseline
from app.db import Database
from app.domain.trips import ServiceAreas
from app.geocoding import PhotonGeocoder
from app.models import Event, FundAccount, FundEntry, Job, PricingConfig
from app.place_catalog import PlaceCatalog
from app.route_preview import RoadPreview
from app.routing import FixtureRouting, OsrmRouting, RoutingProvider


@dataclass
class Clock:
    offset: float = 0

    def now(self) -> float:
        return time.time() + self.offset


@dataclass
class Context:
    settings: Settings
    db: Database
    routing: RoutingProvider
    areas: ServiceAreas
    clock: Clock = field(default_factory=Clock)
    escrow: Any = None
    jwt_secret: str = ""
    webhook_secret: str = ""
    models: Any = None
    wallets: Any = None
    geocoding: PhotonGeocoder | None = None
    road_preview: RoadPreview | None = None


def create_context(settings: Settings) -> Context:
    settings.assert_safe()
    routing = (
        FixtureRouting()
        if settings.routing_mode == "fixture"
        else OsrmRouting(settings.osrm_car_url, settings.osrm_motorbike_url, settings.redis_url)
    )
    context = Context(
        settings,
        Database(settings.database_url),
        routing,
        ServiceAreas(settings.service_areas_path),
    )
    context.jwt_secret = settings.jwt_secret or secrets.token_urlsafe(48)
    context.webhook_secret = settings.webhook_secret or secrets.token_urlsafe(48)
    context.geocoding = PhotonGeocoder(
        settings.geocoding_search_url,
        settings.redis_url,
        catalog=PlaceCatalog(settings.local_places_path),
    )
    context.road_preview = RoadPreview(settings.route_preview_url, settings.redis_url)
    if settings.escrow_mode == "local":
        from app.escrow import LocalEscrowAdapter

        context.escrow = LocalEscrowAdapter(settings.escrow_journal_path)
    elif settings.escrow_mode == "web3":
        from app.escrow.evm import CustodialWallets, EvmSettings, Web3EscrowAdapter

        Path(settings.escrow_journal_path).parent.mkdir(parents=True, exist_ok=True)
        context.wallets = CustodialWallets(settings.escrow_journal_path, settings.evm_mnemonic_env)
        context.escrow = Web3EscrowAdapter(
            EvmSettings(
                settings.evm_rpc_url,
                settings.evm_chain_id,
                settings.evm_escrow_address,
                Path(settings.evm_abi_path),
                Path(settings.escrow_journal_path),
                private_key_env=settings.evm_private_key_env,
            )
        )
    else:
        raise ValueError("Unknown escrow mode")
    return context


def initialize(session: Session, now: float) -> None:
    cfg = baseline()
    canonical = json.dumps(cfg, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    existing = session.get(PricingConfig, cfg["pricing_version"])
    if existing is not None and existing.digest != digest:
        raise RuntimeError("Frozen pricing version has changed. Create a new pricing_version.")
    if existing is None:
        session.add(PricingConfig(version=cfg["pricing_version"], params=cfg, digest=digest))
    if session.get(FundAccount, 1) is None:
        seed = cfg["booking_and_concurrency"]["initial_guarantee_fund_seed_vnd"]
        session.add(FundAccount(id=1, balance_vnd=seed))
        session.add(
            FundEntry(
                booking_id=None,
                entry_type="INITIAL_SEED",
                operation_id="initial-seed",
                amount_signed_vnd=seed,
                balance_after_vnd=seed,
                created_at=now,
            )
        )
    for kind, interval in (("BATCH_MATCH", 30), ("RECONCILE", 300)):
        if (
            session.scalar(
                select(Job).where(
                    Job.job_type == kind, Job.status.in_(["PENDING", "PROCESSING", "FAILED_RETRY"])
                )
            )
            is None
        ):
            schedule(session, kind, "system", now + interval, f"initial:{kind}:{int(now)}")


def initialize_spatial(context: Context, session: Session) -> None:
    if session.bind.dialect.name != "postgresql":
        return
    from sqlalchemy import text

    source = Path(context.settings.service_areas_path).read_bytes()
    digest = hashlib.sha256(source).hexdigest()
    for feature in json.loads(source)["features"]:
        session.execute(
            text("""INSERT INTO service_areas(kind,geom,source_sha256,validation_status)
            VALUES (:kind,ST_SetSRID(ST_GeomFromGeoJSON(:geometry),4326),:digest,:status)
            ON CONFLICT (kind) DO UPDATE SET geom=EXCLUDED.geom,source_sha256=EXCLUDED.source_sha256,validation_status=EXCLUDED.validation_status"""),
            {
                "kind": feature["properties"]["kind"],
                "geometry": json.dumps(feature["geometry"]),
                "digest": digest,
                "status": context.areas.status,
            },
        )


def schedule(
    session: Session,
    kind: str,
    target: str,
    run_at: float,
    key: str | None = None,
    data: dict | None = None,
) -> None:
    session.add(
        Job(
            job_type=kind,
            target_id=target,
            run_at=run_at,
            idempotency_key=key or f"{kind}:{target}",
            data=data or {},
        )
    )


def audit(session: Session, kind: str, target: str, now: float, data: dict | None = None) -> None:
    session.add(Event(kind=kind, target_id=target, created_at=now, data=data or {}))
