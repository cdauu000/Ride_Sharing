from typing import Any

from fastapi import APIRouter
from sqlalchemy import select

from app.domain.errors import DomainError
from app.http.dependencies import Ctx, Db
from app.models import (
    Auxiliary,
)
from research.survey import (
    FAIRNESS_TABLES,
    SCENARIOS,
    SURVEY_VERSION,
    SurveyResponse,
)

router = APIRouter()


@router.get("/surveys/scenarios", response_model=dict[str, Any])
def survey_scenarios() -> dict:
    return {
        "survey_version": SURVEY_VERSION,
        "scenarios": SCENARIOS,
        "fairness_tables": FAIRNESS_TABLES,
    }


@router.post("/surveys/responses", response_model=dict[str, Any], status_code=201)
def survey_response(payload: SurveyResponse, session: Db, context: Ctx) -> dict:
    target = str(payload.respondent_id)
    if session.scalar(
        select(Auxiliary).where(Auxiliary.kind == "SURVEY", Auxiliary.target_id == target)
    ):
        raise DomainError("SURVEY_ALREADY_SUBMITTED")
    record = Auxiliary(
        kind="SURVEY",
        target_id=target,
        data=payload.model_dump(mode="json"),
        created_at=context.clock.now(),
    )
    session.add(record)
    session.flush()
    return {"id": record.id, "status": "RECORDED", "anonymous": True}
