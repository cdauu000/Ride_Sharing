import json
from typing import Any

from fastapi import APIRouter, Request

from app.domain.errors import DomainError
from app.http.dependencies import Ctx

router = APIRouter()


@router.post("/escrow/webhook", response_model=dict[str, Any])
async def escrow_webhook(request: Request, context: Ctx) -> dict:
    from app.escrow.webhook import verify_webhook

    body = await request.body()
    try:
        verify_webhook(
            body,
            request.headers.get("X-Escrow-Timestamp", ""),
            request.headers.get("X-Escrow-Signature", ""),
            context.webhook_secret,
        )
        payload = json.loads(body)
    except (ValueError, TypeError) as exc:
        raise DomainError("INVALID_WEBHOOK_SIGNATURE", status=401) from exc
    # A signed notification is a wake-up hint. Only independently fetched chain receipts alter money.
    return {
        "accepted": True,
        "event_id": str(payload.get("event_id", ""))[:128],
        "verified_from_chain": False,
    }
