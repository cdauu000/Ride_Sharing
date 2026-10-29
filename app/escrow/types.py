from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Protocol


class EscrowError(ValueError):
    """A rejected financial command; callers must roll back business mutations."""


class EscrowRejected(EscrowError):
    """Definitive rejection with no financial effect, not an unknown RPC outcome."""


@dataclass(frozen=True)
class EscrowCommand:
    operation_id: str
    action: str
    booking_id: str
    params: dict[str, Any] = field(default_factory=dict)

    def fingerprint(self) -> str:
        payload = json.dumps(
            {"action": self.action, "booking_id": self.booking_id, "params": self.params},
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        return hashlib.sha256(payload.encode()).hexdigest()


@dataclass(frozen=True)
class EscrowReceipt:
    operation_id: str
    mode: str
    tx_hash: str | None
    status: str
    snapshot: dict[str, Any]
    block_number: int | None = None


class EscrowAdapter(Protocol):
    mode: str

    def execute(self, command: EscrowCommand) -> EscrowReceipt: ...

    def get(self, booking_id: str) -> dict[str, Any]: ...

    @property
    def fund_balance_vnd(self) -> int: ...


def integer_vnd(value: Any, *, positive: bool = False, fare: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EscrowError("INVALID_INTEGER_VND")
    if positive and value == 0:
        raise EscrowError("AMOUNT_MUST_BE_POSITIVE")
    if fare and (value == 0 or value % 1000):
        raise EscrowError("FARE_MUST_BE_POSITIVE_MULTIPLE_OF_1000")
    return value
