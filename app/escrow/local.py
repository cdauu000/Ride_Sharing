from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .types import EscrowCommand, EscrowError, EscrowReceipt, EscrowRejected, integer_vnd

SERVICES = {
    "BIKE_URBAN",
    "CAR_URBAN_PRIVATE",
    "CAR_URBAN_POOL",
    "CAR_INTERCITY_PRIVATE",
    "CAR_INTERCITY_POOL",
}
ACTIVE = {"DEPOSITED", "LOCKED", "TOPPED_UP"}


class LocalEscrowAdapter:
    """Durable local financial simulation, never represented as a chain transaction.

    Each command and its result commit atomically in a private SQLite journal.
    Retrying an operation ID after process failure cannot pay twice. The caller's
    business database should enqueue commands in an outbox and consume receipts.
    """

    mode = "LOCAL_SIMULATION"

    def __init__(self, path: str | Path, initial_fund_vnd: int = 5_000_000) -> None:
        self.path = str(path)
        integer_vnd(initial_fund_vnd)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS escrow_bookings (id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS escrow_operations (
                    id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, receipt TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS escrow_fund (id INTEGER PRIMARY KEY CHECK(id=1), balance INTEGER NOT NULL CHECK(balance>=0));
            """)
            db.execute("INSERT OR IGNORE INTO escrow_fund VALUES (1, ?)", (initial_fund_vnd,))

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.execute("PRAGMA busy_timeout=30000")
        try:
            yield db
        finally:
            db.close()

    @property
    def fund_balance_vnd(self) -> int:
        with self._connect() as db:
            return int(db.execute("SELECT balance FROM escrow_fund WHERE id=1").fetchone()[0])

    def get(self, booking_id: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute(
                "SELECT data FROM escrow_bookings WHERE id=?", (booking_id,)
            ).fetchone()
            if not row:
                raise EscrowError("ESCROW_NOT_FOUND")
            snapshot: dict[str, Any] = json.loads(row[0])
            snapshot["fund_balance_vnd"] = int(
                db.execute("SELECT balance FROM escrow_fund WHERE id=1").fetchone()[0]
            )
            return snapshot

    def execute(self, command: EscrowCommand) -> EscrowReceipt:
        if not command.operation_id or len(command.operation_id) > 200 or not command.booking_id:
            raise EscrowError("INVALID_OPERATION_ID")
        fingerprint = command.fingerprint()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                prior = db.execute(
                    "SELECT fingerprint,receipt FROM escrow_operations WHERE id=?",
                    (command.operation_id,),
                ).fetchone()
                if prior:
                    if prior[0] != fingerprint:
                        raise EscrowError("ESCROW_OPERATION_PAYLOAD_MISMATCH")
                    db.commit()
                    return EscrowReceipt(**json.loads(prior[1]))
                row = db.execute(
                    "SELECT data FROM escrow_bookings WHERE id=?", (command.booking_id,)
                ).fetchone()
                booking = json.loads(row[0]) if row else None
                fund = int(db.execute("SELECT balance FROM escrow_fund WHERE id=1").fetchone()[0])
                try:
                    booking, fund = self._apply(command, booking, fund)
                except EscrowError as exc:
                    raise EscrowRejected(str(exc)) from exc
                booking["mode"] = self.mode
                db.execute(
                    "INSERT INTO escrow_bookings(id,data) VALUES (?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data",
                    (command.booking_id, json.dumps(booking, sort_keys=True)),
                )
                db.execute("UPDATE escrow_fund SET balance=? WHERE id=1", (fund,))
                snapshot = {**booking, "fund_balance_vnd": fund}
                receipt = EscrowReceipt(
                    command.operation_id, self.mode, None, "CONFIRMED", snapshot
                )
                db.execute(
                    "INSERT INTO escrow_operations VALUES(?,?,?)",
                    (
                        command.operation_id,
                        fingerprint,
                        json.dumps(asdict(receipt), sort_keys=True),
                    ),
                )
                db.commit()
                return receipt
            except Exception:
                db.rollback()
                raise

    def _apply(
        self, command: EscrowCommand, b: dict[str, Any] | None, fund: int
    ) -> tuple[dict[str, Any], int]:
        p = command.params
        action = command.action
        if action in {"DEPOSIT_FIXED", "DEPOSIT_POOL", "DEPOSIT_INTERCITY"}:
            if b is not None:
                raise EscrowError("DUPLICATE_BOOKING")
            fare = integer_vnd(p.get("amount_vnd"), fare=True)
            service = p.get("service_code")
            expected = {
                "DEPOSIT_POOL": {"CAR_URBAN_POOL"},
                "DEPOSIT_INTERCITY": {"CAR_INTERCITY_POOL"},
                "DEPOSIT_FIXED": {"BIKE_URBAN", "CAR_URBAN_PRIVATE", "CAR_INTERCITY_PRIVATE"},
            }
            if (
                service not in expected[action]
                or not p.get("passenger")
                or not p.get("driver")
                or p["passenger"] == p["driver"]
            ):
                raise EscrowError("INVALID_DEPOSIT_PARTIES_OR_SERVICE")
            quote = integer_vnd(p.get("quote_vnd", 0))
            target = integer_vnd(p.get("target_driver_vnd", 0))
            if action == "DEPOSIT_POOL" and (
                quote == 0 or quote % 1000 or quote >= fare or target == 0 or target > fare
            ):
                raise EscrowError("INVALID_POOL_CAP")
            return {
                "booking_id": command.booking_id,
                "passenger": p["passenger"],
                "driver": p["driver"],
                "service_code": service,
                "trip_id": p.get("trip_id", ""),
                "status": "DEPOSITED",
                "cap_vnd": fare,
                "deposited_vnd": fare,
                "balance_vnd": fare,
                "quote_vnd": quote,
                "target_driver_vnd": target,
                "final_vnd": 0 if action == "DEPOSIT_POOL" else fare,
                "refunded_vnd": 0,
                "driver_paid_vnd": 0,
                "platform_paid_vnd": 0,
                "fund_contribution_vnd": 0,
                "guarantee_vnd": 0,
                "price_locked": action != "DEPOSIT_POOL",
                "matched": False,
                "driver_declined": False,
                "started": False,
                "completed": False,
                "topup_mode": False,
                "late_cancellation_protection": False,
                "credited_cancellation_vnd": 0,
            }, fund
        if b is None:
            raise EscrowError("ESCROW_NOT_FOUND")
        if action == "RESOLVE":
            if b["status"] != "DISPUTED":
                raise EscrowError("ESCROW_NOT_DISPUTED")
            refund = integer_vnd(p.get("passenger_vnd"))
            driver = integer_vnd(p.get("driver_vnd"))
            platform = integer_vnd(p.get("platform_vnd"))
            if refund + driver + platform != b["balance_vnd"]:
                raise EscrowError("DISPUTE_ALLOCATION_MISMATCH")
            b.update(
                status="RESOLVED",
                balance_vnd=0,
                refunded_vnd=b["refunded_vnd"] + refund,
                driver_paid_vnd=driver,
                platform_paid_vnd=platform,
            )
            return b, fund
        if b["status"] not in ACTIVE:
            raise EscrowError("ESCROW_NOT_ACTIVE")
        if action == "LOCK":
            final = integer_vnd(p.get("final_vnd"), fare=True)
            matched = p.get("matched", False)
            declined = p.get("driver_declined", False)
            if not isinstance(matched, bool) or not isinstance(declined, bool):
                raise EscrowError("INVALID_LOCK_FLAGS")
            if b["price_locked"] or b["service_code"] != "CAR_URBAN_POOL":
                raise EscrowError("PRICE_ALREADY_LOCKED_OR_NON_POOL")
            if final > b["balance_vnd"] or (matched and (declined or final > b["quote_vnd"])):
                raise EscrowError("PRICE_CAP_EXCEEDED")
            if declined and final != b["quote_vnd"]:
                raise EscrowError("DRIVER_DECLINE_MUST_USE_QUOTE")
            if not matched and not declined and final != b["cap_vnd"]:
                raise EscrowError("UNMATCHED_MUST_USE_CAP")
            b["refunded_vnd"] += b["balance_vnd"] - final
            b.update(
                balance_vnd=final,
                final_vnd=final,
                status="LOCKED",
                price_locked=True,
                matched=matched,
                driver_declined=declined,
            )
        elif action == "TOPUP":
            amount = integer_vnd(p.get("amount_vnd"), fare=True)
            if b["service_code"] != "CAR_INTERCITY_POOL" or b["started"] or b["topup_mode"]:
                raise EscrowError("INVALID_TOPUP_STATE")
            b["topup_original_vnd"] = b["final_vnd"]
            b.update(
                balance_vnd=b["balance_vnd"] + amount,
                final_vnd=b["final_vnd"] + amount,
                deposited_vnd=b["deposited_vnd"] + amount,
                status="TOPPED_UP",
                topup_mode=True,
            )
        elif action == "REVERT_TOPUP":
            if b["service_code"] != "CAR_INTERCITY_POOL" or not b["topup_mode"] or b["started"]:
                raise EscrowError("INVALID_TOPUP_REVERT_STATE")
            original = b["topup_original_vnd"]
            b["refunded_vnd"] += b["balance_vnd"] - original
            b.update(
                balance_vnd=original,
                final_vnd=original,
                status="LOCKED",
                topup_mode=False,
                topup_original_vnd=0,
            )
        elif action == "MERGE":
            final = integer_vnd(p.get("final_vnd"), fare=True)
            if b["service_code"] != "CAR_INTERCITY_POOL" or b["started"] or b["topup_mode"]:
                raise EscrowError("INVALID_MERGE_STATE")
            if final > b["balance_vnd"] or not p.get("driver") or p["driver"] == b["passenger"]:
                raise EscrowError("INVALID_MERGE_PRICE_OR_DRIVER")
            b["refunded_vnd"] += b["balance_vnd"] - final
            b.update(
                balance_vnd=final,
                final_vnd=final,
                status="LOCKED",
                driver=p["driver"],
                trip_id=p.get("trip_id", ""),
            )
        elif action == "START":
            if b["started"]:
                raise EscrowError("RIDE_ALREADY_STARTED")
            b["started"] = True
        elif action == "COMPLETE":
            if not b["started"] or not b["price_locked"] or b["completed"]:
                raise EscrowError("RIDE_NOT_STARTED_OR_PRICE_NOT_LOCKED")
            b["completed"] = True
        elif action == "PROTECT_LATE_CANCEL":
            if (
                not b["matched"]
                or not b["price_locked"]
                or b["service_code"] != "CAR_URBAN_POOL"
                or b["completed"]
            ):
                raise EscrowError("INVALID_LATE_CANCELLATION_STATE")
            credit = integer_vnd(p.get("credited_penalty_vnd", 0))
            if credit < b["credited_cancellation_vnd"]:
                raise EscrowError("CANCELLATION_CREDIT_CANNOT_DECREASE")
            b["late_cancellation_protection"] = True
            b["credited_cancellation_vnd"] = credit
        elif action == "RELEASE":
            if not b["completed"] or not b["price_locked"]:
                raise EscrowError("RELEASE_REQUIRES_COMPLETED_AND_LOCKED")
            fare = b["balance_vnd"]
            contribution = 0
            guarantee = 0
            if b["service_code"] == "CAR_URBAN_POOL":
                driver = fare * 85 // 100
                contribution = fare * 3 // 100 if b["matched"] else 0
                platform = fare - driver - contribution
                eligible = (not b["matched"] and not b["driver_declined"]) or b[
                    "late_cancellation_protection"
                ]
                credited = (
                    b["credited_cancellation_vnd"] if b["late_cancellation_protection"] else 0
                )
                guarantee = max(0, b["target_driver_vnd"] - driver - credited) if eligible else 0
            else:
                rate = 20 if b["service_code"] in {"BIKE_URBAN", "CAR_URBAN_PRIVATE"} else 15
                if b["service_code"] == "CAR_INTERCITY_POOL" and not b["topup_mode"]:
                    rate = 10
                platform = fare * rate // 100
                driver = fare - platform
            if guarantee > fund + contribution:
                raise EscrowError("GUARANTEE_FUND_INSUFFICIENT")
            fund += contribution - guarantee
            b.update(
                status="RELEASED",
                balance_vnd=0,
                driver_paid_vnd=driver + guarantee,
                platform_paid_vnd=platform,
                fund_contribution_vnd=contribution,
                guarantee_vnd=guarantee,
            )
        elif action == "CANCEL":
            fee = integer_vnd(p.get("fee_vnd", 0))
            driver = integer_vnd(p.get("driver_vnd", 0))
            platform = integer_vnd(p.get("platform_vnd", 0))
            to_fund = integer_vnd(p.get("fund_vnd", 0))
            if b["completed"] or fee != driver + platform + to_fund or fee > b["balance_vnd"]:
                raise EscrowError("CANCELLATION_ALLOCATION_MISMATCH")
            b.update(
                status="REFUNDED",
                refunded_vnd=b["refunded_vnd"] + b["balance_vnd"] - fee,
                balance_vnd=0,
                driver_paid_vnd=driver,
                platform_paid_vnd=platform,
                fund_contribution_vnd=to_fund,
            )
            fund += to_fund
        elif action == "DISPUTE":
            b["status"] = "DISPUTED"
        else:
            raise EscrowError("UNKNOWN_ESCROW_ACTION")
        return b, fund
