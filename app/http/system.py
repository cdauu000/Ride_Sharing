from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter

from app.config import baseline
from app.http.dependencies import Ctx

router = APIRouter()


@router.get("/health", response_model=dict[str, str])
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/system", response_model=dict[str, Any])
def system(context: Ctx) -> dict[str, Any]:
    return {
        "app_version": "0.1.0",
        "routing_mode": context.settings.routing_mode,
        "escrow_mode": context.settings.escrow_mode,
        "database": context.db.engine.dialect.name,
        "pricing_version": baseline()["pricing_version"],
        "service_areas_status": context.areas.status,
        "readiness": "DEVELOPMENT_VALIDATION"
        if context.settings.environment == "development"
        else "CONFIGURED",
        "model_configured": context.models is not None,
        "scope": "MUST_AND_SHOULD",
        "server_time": datetime.fromtimestamp(context.clock.now(), UTC).isoformat(),
    }
