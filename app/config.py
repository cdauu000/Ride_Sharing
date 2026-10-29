from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="RISE_", extra="ignore")

    database_url: str = "sqlite:///./rise.db"
    environment: str = "development"
    routing_mode: str = "fixture"
    escrow_mode: str = "local"
    osrm_car_url: str = "http://localhost:5000"
    osrm_motorbike_url: str = "http://localhost:5001"
    geocoding_search_url: str = "https://photon.komoot.io/api/"
    local_places_path: str = str(ROOT / "config" / "local_places.json")
    route_preview_url: str = "https://routing.openstreetmap.de/routed-car"
    redis_url: str | None = None
    jwt_secret: str = ""
    webhook_secret: str = ""
    secure_cookies: bool = False
    allowed_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    service_areas_path: str = str(ROOT / "config" / "service_areas.geojson")
    model_artifact_path: str | None = None
    auto_create_schema: bool = True
    run_worker: bool = False
    escrow_journal_path: str = "data/escrow.db"
    evm_rpc_url: str = "http://127.0.0.1:8545"
    evm_chain_id: int = 31337
    evm_escrow_address: str = ""
    evm_abi_path: str = "contracts/abi/RideEscrow.json"
    evm_private_key_env: str = "ESCROW_RELAYER_PRIVATE_KEY"
    evm_mnemonic_env: str = "ESCROW_HD_MNEMONIC"

    def assert_safe(self) -> None:
        if self.environment != "development":
            if len(self.jwt_secret) < 32 or len(self.webhook_secret) < 32:
                raise ValueError("Non-development environments require strong configured secrets")
            if self.routing_mode != "osrm" or self.escrow_mode != "web3":
                raise ValueError("Fixture routing / local escrow only allowed in development")
            if not self.database_url.startswith("postgresql") or self.auto_create_schema:
                raise ValueError("Use PostgreSQL and Alembic migrations outside development")


@lru_cache
def baseline() -> dict[str, Any]:
    with (ROOT / "config" / "mvp_config_baseline_v1.yaml").open(encoding="utf-8") as stream:
        return yaml.safe_load(stream)
