"""Custodial EVM adapter with a durable signed-transaction journal.

The application must submit commands from an ACID outbox. A signed transaction
is persisted before broadcast, so an ambiguous RPC timeout is retried with the
same nonce rather than issuing a second monetary operation. No secrets are stored
in this journal. Deployments and HD wallet funding are explicit operator steps.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .types import EscrowCommand, EscrowError, EscrowReceipt, EscrowRejected

SERVICE_CODES = (
    "BIKE_URBAN",
    "CAR_URBAN_PRIVATE",
    "CAR_URBAN_POOL",
    "CAR_INTERCITY_PRIVATE",
    "CAR_INTERCITY_POOL",
)
STATES = (
    "NONE",
    "DEPOSITED",
    "LOCKED",
    "TOPPED_UP",
    "RELEASED",
    "REFUNDED",
    "DISPUTED",
    "RESOLVED",
)
BOOKING_FIELDS = (
    "passenger",
    "driver",
    "trip_id",
    "service",
    "state",
    "cap_vnd",
    "balance_vnd",
    "quote_vnd",
    "target_driver_vnd",
    "final_vnd",
    "refunded_vnd",
    "driver_paid_vnd",
    "platform_paid_vnd",
    "fund_contribution_vnd",
    "guarantee_vnd",
    "completed_at",
    "price_locked",
    "matched",
    "driver_declined",
    "started",
    "completed",
    "topup_mode",
    "late_cancellation_protection",
    "credited_cancellation_vnd",
    "topup_original_vnd",
)


@dataclass(frozen=True)
class EvmSettings:
    rpc_url: str
    chain_id: int
    escrow_address: str
    abi_path: Path
    journal_path: Path
    private_key_env: str = "ESCROW_RELAYER_PRIVATE_KEY"
    confirmations: int = 1
    receipt_timeout_s: float = 2.0
    replace_after_s: float = 120.0
    max_attempts: int = 5


class CustodialWallets:
    """Stable user-to-HD-index mapping, with mnemonic read only from the environment."""

    def __init__(self, journal_path: str | Path, mnemonic_env: str = "ESCROW_HD_MNEMONIC") -> None:
        self.path = str(journal_path)
        self.mnemonic_env = mnemonic_env
        Path(journal_path).parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS hd_wallets (user_id TEXT PRIMARY KEY, derivation_index INTEGER UNIQUE NOT NULL)"
            )

    def account(self, user_id: str) -> Any:
        from eth_account import Account

        mnemonic = os.getenv(self.mnemonic_env)
        if not mnemonic:
            raise EscrowError("ESCROW_HD_MNEMONIC_NOT_CONFIGURED")
        with closing(sqlite3.connect(self.path, timeout=30)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT derivation_index FROM hd_wallets WHERE user_id=?", (user_id,)
            ).fetchone()
            if row:
                index = int(row[0])
            else:
                index = int(
                    db.execute(
                        "SELECT COALESCE(MAX(derivation_index),-1)+1 FROM hd_wallets"
                    ).fetchone()[0]
                )
                if index >= 2**31:
                    raise EscrowError("HD_WALLET_INDEX_EXHAUSTED")
                db.execute("INSERT INTO hd_wallets VALUES (?,?)", (user_id, index))
        Account.enable_unaudited_hdwallet_features()
        return Account.from_mnemonic(mnemonic, account_path=f"m/44'/60'/0'/0/{index}")

    def address(self, user_id: str) -> str:
        return str(self.account(user_id).address)


class Web3EscrowAdapter:
    def __init__(self, settings: EvmSettings) -> None:
        from eth_account import Account
        from web3 import Web3

        if (
            settings.confirmations < 1
            or settings.chain_id <= 0
            or not settings.rpc_url.startswith(("http://", "https://"))
        ):
            raise EscrowError("INVALID_EVM_SETTINGS")
        key = os.getenv(settings.private_key_env)
        if not key:
            raise EscrowError("ESCROW_RELAYER_KEY_NOT_CONFIGURED")
        self.settings = settings
        self.web3 = Web3(Web3.HTTPProvider(settings.rpc_url, request_kwargs={"timeout": 15}))
        if self.web3.eth.chain_id != settings.chain_id:
            raise EscrowError("EVM_CHAIN_ID_MISMATCH")
        self.account = Account.from_key(key)
        address = Web3.to_checksum_address(settings.escrow_address)
        if not self.web3.eth.get_code(address):
            raise EscrowError("ESCROW_CONTRACT_NOT_DEPLOYED")
        self.contract = self.web3.eth.contract(
            address=address, abi=json.loads(settings.abi_path.read_text(encoding="utf8"))
        )
        self.mode = "LOCAL_EVM" if settings.chain_id == 31337 else "EVM_TESTNET"
        settings.journal_path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS evm_operations (
                    operation_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, nonce INTEGER NOT NULL,
                    raw_tx TEXT NOT NULL, tx_hash TEXT NOT NULL, submitted_at REAL NOT NULL,
                    attempts INTEGER NOT NULL, status TEXT NOT NULL, fee_json TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS evm_nonces (
                    signer TEXT PRIMARY KEY, next_nonce INTEGER NOT NULL);
            """)

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.settings.journal_path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _id(value: str) -> bytes:
        # Stable namespaced UTF-8 IDs, same mapping must be used by event consumers.
        return hashlib.sha256(("ride-sharing:v9:" + value).encode()).digest()

    @property
    def fund_balance_vnd(self) -> int:
        return int(self.contract.functions.guaranteeFundBalance().call())

    def get(self, booking_id: str) -> dict[str, Any]:
        values = self.contract.functions.getBooking(self._id(booking_id)).call()
        b = dict(zip(BOOKING_FIELDS, values, strict=True))
        if int(b["state"]) == 0:
            raise EscrowError("ESCROW_NOT_FOUND")
        b["status"] = STATES[int(b.pop("state"))]
        b["service_code"] = SERVICE_CODES[int(b.pop("service"))]
        b["trip_id"] = "0x" + bytes(b["trip_id"]).hex()
        b.update(booking_id=booking_id, mode=self.mode, fund_balance_vnd=self.fund_balance_vnd)
        return b

    def _function(self, c: EscrowCommand) -> Any:
        from web3 import Web3

        p = c.params
        booking = self._id(c.booking_id)
        functions = self.contract.functions
        trip = self._id(str(p.get("trip_id", "")))
        checksum = Web3.to_checksum_address
        if c.action == "DEPOSIT_FIXED":
            service = SERVICE_CODES.index(p["service_code"])
            return functions.createAndDepositFixed(
                booking,
                trip,
                checksum(p["passenger"]),
                checksum(p["driver"]),
                service,
                p["amount_vnd"],
            )
        if c.action == "DEPOSIT_POOL":
            return functions.createAndDepositPoolCap(
                booking,
                trip,
                checksum(p["passenger"]),
                checksum(p["driver"]),
                p["amount_vnd"],
                p["quote_vnd"],
                p["target_driver_vnd"],
            )
        if c.action == "DEPOSIT_INTERCITY":
            return functions.createAndDepositIntercityPool(
                booking, trip, checksum(p["passenger"]), checksum(p["driver"]), p["amount_vnd"]
            )
        if c.action == "LOCK":
            return functions.lockFinalPriceAndRefundDiff(
                booking, p["final_vnd"], p.get("matched", False), p.get("driver_declined", False)
            )
        if c.action == "TOPUP":
            return functions.topUpEscrow(booking, p["amount_vnd"])
        if c.action == "REVERT_TOPUP":
            return functions.revertTopUpEscrow(booking)
        if c.action == "MERGE":
            return functions.reassignIntercityBooking(
                booking, trip, checksum(p["driver"]), p["final_vnd"]
            )
        if c.action == "PROTECT_LATE_CANCEL":
            return functions.protectLateCancellation(booking, p.get("credited_penalty_vnd", 0))
        if c.action == "START":
            return functions.markRideStarted(booking)
        if c.action == "COMPLETE":
            return functions.markRideCompleted(booking)
        if c.action == "RELEASE":
            return functions.releasePayment(booking)
        if c.action == "CANCEL":
            return functions.cancelAndRefund(
                booking,
                p.get("fee_vnd", 0),
                p.get("fund_vnd", 0),
                p.get("driver_vnd", 0),
                p.get("platform_vnd", 0),
            )
        if c.action == "DISPUTE":
            return functions.raiseDispute(booking)
        if c.action == "RESOLVE":
            return functions.resolveDispute(
                booking, p["passenger_vnd"], p["driver_vnd"], p["platform_vnd"]
            )
        raise EscrowError("UNKNOWN_ESCROW_ACTION")

    def _signed(
        self, function: Any, nonce: int, fees: dict[str, int] | None = None
    ) -> tuple[str, str, dict[str, int]]:
        if fees is None:
            block = self.web3.eth.get_block("latest")
            if "baseFeePerGas" in block:
                priority = int(self.web3.eth.max_priority_fee)
                fees = {
                    "maxPriorityFeePerGas": priority,
                    "maxFeePerGas": int(block["baseFeePerGas"]) * 2 + priority,
                }
            else:
                fees = {"gasPrice": int(self.web3.eth.gas_price)}
        transaction = function.build_transaction(
            {
                "from": self.account.address,
                "nonce": nonce,
                "chainId": self.settings.chain_id,
                **fees,
            }
        )
        transaction["gas"] = int(transaction["gas"] * 12 // 10)
        signed = self.account.sign_transaction(transaction)
        return signed.raw_transaction.hex(), signed.hash.hex(), fees

    def execute(self, command: EscrowCommand) -> EscrowReceipt:
        from web3.exceptions import TimeExhausted, TransactionNotFound, Web3RPCError

        if not command.operation_id or len(command.operation_id) > 200:
            raise EscrowError("INVALID_OPERATION_ID")
        fingerprint = command.fingerprint()
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM evm_operations WHERE operation_id=?", (command.operation_id,)
            ).fetchone()
            if row and row["fingerprint"] != fingerprint:
                raise EscrowError("ESCROW_OPERATION_PAYLOAD_MISMATCH")
            if row and row["status"] == "FAILED":
                raise EscrowRejected("EVM_TRANSACTION_REVERTED")
            if row is None:
                persisted = db.execute(
                    "SELECT next_nonce FROM evm_nonces WHERE signer=?", (self.account.address,)
                ).fetchone()
                nonce = max(
                    int(self.web3.eth.get_transaction_count(self.account.address, "pending")),
                    int(persisted[0]) if persisted else 0,
                )
                raw, tx_hash, fees = self._signed(self._function(command), nonce)
                db.execute(
                    "INSERT INTO evm_operations VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        command.operation_id,
                        fingerprint,
                        nonce,
                        raw,
                        tx_hash,
                        time.time(),
                        1,
                        "SUBMITTED",
                        json.dumps(fees),
                    ),
                )
                db.execute(
                    "INSERT INTO evm_nonces VALUES(?,?) ON CONFLICT(signer) DO UPDATE SET next_nonce=excluded.next_nonce",
                    (self.account.address, nonce + 1),
                )
                db.commit()
                row = db.execute(
                    "SELECT * FROM evm_operations WHERE operation_id=?", (command.operation_id,)
                ).fetchone()
            elif (
                row["status"] == "SUBMITTED"
                and time.time() - float(row["submitted_at"]) > self.settings.replace_after_s
            ):
                # Only replace an unmined transaction. A transaction already mined
                # but awaiting finality must retain its original receipt/hash.
                try:
                    self.web3.eth.get_transaction_receipt(row["tx_hash"])
                except TransactionNotFound:
                    if int(row["attempts"]) >= self.settings.max_attempts:
                        raise EscrowError("EVM_RETRY_LIMIT_REACHED") from None
                    fees = {
                        key: int(value) * 115 // 100 + 1
                        for key, value in json.loads(row["fee_json"]).items()
                    }
                    raw, tx_hash, fees = self._signed(
                        self._function(command), int(row["nonce"]), fees
                    )
                    db.execute(
                        "UPDATE evm_operations SET raw_tx=?,tx_hash=?,submitted_at=?,attempts=attempts+1,fee_json=? WHERE operation_id=?",
                        (raw, tx_hash, time.time(), json.dumps(fees), command.operation_id),
                    )
                    db.commit()
                    row = db.execute(
                        "SELECT * FROM evm_operations WHERE operation_id=?", (command.operation_id,)
                    ).fetchone()
            db.commit()
        assert row is not None
        tx_hash = str(row["tx_hash"])
        if not tx_hash.startswith("0x"):
            tx_hash = "0x" + tx_hash
        try:
            chain_receipt = self.web3.eth.get_transaction_receipt(tx_hash)
        except TransactionNotFound:
            chain_receipt = None
        if chain_receipt is None:
            try:
                self.web3.eth.send_raw_transaction(
                    bytes.fromhex(str(row["raw_tx"]).removeprefix("0x"))
                )
            except (ValueError, Web3RPCError) as exc:
                message = str(exc).lower()
                if not any(
                    value in message
                    for value in ("already known", "known transaction", "nonce too low")
                ):
                    raise EscrowError("EVM_BROADCAST_FAILED") from exc
        try:
            receipt = chain_receipt or self.web3.eth.wait_for_transaction_receipt(
                tx_hash, timeout=self.settings.receipt_timeout_s, poll_latency=0.1
            )
        except (TimeExhausted, TransactionNotFound):
            return EscrowReceipt(command.operation_id, self.mode, tx_hash, "SUBMITTED", {})
        canonical = self.web3.eth.get_block(receipt["blockNumber"])
        if (
            canonical["hash"] != receipt["blockHash"]
            or self.web3.eth.block_number - int(receipt["blockNumber"]) + 1
            < self.settings.confirmations
        ):
            return EscrowReceipt(
                command.operation_id,
                self.mode,
                tx_hash,
                "SUBMITTED",
                {},
                int(receipt["blockNumber"]),
            )
        if int(receipt["status"]) != 1:
            with self._db() as db:
                db.execute(
                    "UPDATE evm_operations SET status='FAILED' WHERE operation_id=?",
                    (command.operation_id,),
                )
            raise EscrowRejected("EVM_TRANSACTION_REVERTED")
        with self._db() as db:
            db.execute(
                "UPDATE evm_operations SET status='CONFIRMED' WHERE operation_id=?",
                (command.operation_id,),
            )
        return EscrowReceipt(
            command.operation_id,
            self.mode,
            tx_hash,
            "CONFIRMED",
            self.get(command.booking_id),
            int(receipt["blockNumber"]),
        )
