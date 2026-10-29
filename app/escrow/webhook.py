"""Timestamp-bound HMAC authentication; caller must deduplicate signed event IDs."""

from __future__ import annotations

import hashlib
import hmac
import time

from .types import EscrowError


def sign_webhook(body: bytes, timestamp: int, secret: str) -> str:
    if len(secret) < 32:
        raise EscrowError("WEBHOOK_SECRET_TOO_SHORT")
    message = str(timestamp).encode() + b"." + body
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def verify_webhook(
    body: bytes,
    timestamp: str,
    signature: str,
    secret: str,
    *,
    now: int | None = None,
    tolerance_s: int = 300,
) -> None:
    try:
        seconds = int(timestamp)
    except (ValueError, TypeError):
        raise EscrowError("INVALID_WEBHOOK_TIMESTAMP") from None
    current = int(time.time()) if now is None else now
    if abs(current - seconds) > tolerance_s:
        raise EscrowError("EXPIRED_WEBHOOK_SIGNATURE")
    expected = sign_webhook(body, seconds, secret)
    candidate = signature.removeprefix("sha256=")
    if not hmac.compare_digest(expected, candidate):
        raise EscrowError("INVALID_WEBHOOK_SIGNATURE")
