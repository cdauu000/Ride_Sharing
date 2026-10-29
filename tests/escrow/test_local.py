from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from app.escrow import EscrowCommand, EscrowError, LocalEscrowAdapter
from app.escrow.webhook import sign_webhook, verify_webhook


def command(
    action: str, params: dict | None = None, *, booking: str = "a", operation: str | None = None
) -> EscrowCommand:
    return EscrowCommand(operation or f"{booking}:{action}", action, booking, params or {})


def pool(adapter: LocalEscrowAdapter, booking: str = "a") -> None:
    adapter.execute(
        command(
            "DEPOSIT_POOL",
            {
                "passenger": "passenger",
                "driver": "driver",
                "amount_vnd": 174000,
                "service_code": "CAR_URBAN_POOL",
                "quote_vnd": 155000,
                "target_driver_vnd": 155200,
            },
            booking=booking,
        )
    )


def finish(adapter: LocalEscrowAdapter, booking: str = "a") -> dict:
    adapter.execute(command("START", booking=booking))
    adapter.execute(command("COMPLETE", booking=booking))
    return adapter.execute(command("RELEASE", booking=booking)).snapshot


def test_unmatched_exact_guarantee_and_durable_restart(tmp_path: Path) -> None:
    path = tmp_path / "escrow.sqlite"
    adapter = LocalEscrowAdapter(path)
    pool(adapter)
    adapter.execute(command("LOCK", {"final_vnd": 174000}))
    result = finish(adapter)
    assert result["driver_paid_vnd"] == 155200
    assert result["guarantee_vnd"] == 7300
    assert result["platform_paid_vnd"] == 26100
    assert result["fund_balance_vnd"] == 4992700
    assert result["mode"] == "LOCAL_SIMULATION"
    assert LocalEscrowAdapter(path).get("a") == result


def test_matched_exact_money_and_refund(tmp_path: Path) -> None:
    adapter = LocalEscrowAdapter(tmp_path / "escrow.sqlite")
    pool(adapter)
    adapter.execute(command("LOCK", {"final_vnd": 143000, "matched": True}))
    result = finish(adapter)
    assert result["driver_paid_vnd"] == 121550
    assert result["platform_paid_vnd"] == 17160
    assert result["fund_contribution_vnd"] == 4290
    assert result["refunded_vnd"] == 31000
    assert (
        result["driver_paid_vnd"]
        + result["platform_paid_vnd"]
        + result["fund_contribution_vnd"]
        + result["refunded_vnd"]
        == 174000
    )


def test_driver_decline_cuts_guarantee(tmp_path: Path) -> None:
    adapter = LocalEscrowAdapter(tmp_path / "escrow.sqlite")
    pool(adapter)
    adapter.execute(command("LOCK", {"final_vnd": 155000, "driver_declined": True}))
    result = finish(adapter)
    assert result["driver_paid_vnd"] == 131750
    assert result["guarantee_vnd"] == 0
    assert result["refunded_vnd"] == 19000


def test_command_idempotency_under_parallel_retry(tmp_path: Path) -> None:
    adapter = LocalEscrowAdapter(tmp_path / "escrow.sqlite")
    deposit = command(
        "DEPOSIT_FIXED",
        {"passenger": "p", "driver": "d", "amount_vnd": 81000, "service_code": "BIKE_URBAN"},
    )
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(lambda _: adapter.execute(deposit), range(5)))
    assert all(result == results[0] for result in results)
    assert all(result.tx_hash is None for result in results)
    assert finish(adapter)["driver_paid_vnd"] == 64800
    with pytest.raises(EscrowError, match="PAYLOAD_MISMATCH"):
        adapter.execute(EscrowCommand(deposit.operation_id, "RELEASE", "a"))


def test_fund_insufficiency_rolls_back_everything(tmp_path: Path) -> None:
    adapter = LocalEscrowAdapter(tmp_path / "escrow.sqlite", 0)
    pool(adapter)
    adapter.execute(command("LOCK", {"final_vnd": 174000}))
    adapter.execute(command("START"))
    adapter.execute(command("COMPLETE"))
    with pytest.raises(EscrowError, match="FUND_INSUFFICIENT"):
        adapter.execute(command("RELEASE"))
    result = adapter.get("a")
    assert result["balance_vnd"] == 174000
    assert result["driver_paid_vnd"] == 0
    assert adapter.fund_balance_vnd == 0


def test_release_requires_start_completion_and_lock(tmp_path: Path) -> None:
    adapter = LocalEscrowAdapter(tmp_path / "escrow.sqlite")
    pool(adapter)
    with pytest.raises(EscrowError):
        adapter.execute(command("COMPLETE"))
    with pytest.raises(EscrowError):
        adapter.execute(command("RELEASE"))
    adapter.execute(command("START"))
    with pytest.raises(EscrowError):
        adapter.execute(command("COMPLETE"))


def test_late_cancellation_protection_keeps_price(tmp_path: Path) -> None:
    adapter = LocalEscrowAdapter(tmp_path / "escrow.sqlite")
    pool(adapter)
    adapter.execute(command("LOCK", {"final_vnd": 143000, "matched": True}))
    adapter.execute(command("PROTECT_LATE_CANCEL", {"credited_penalty_vnd": 15500}))
    result = finish(adapter)
    assert result["final_vnd"] == 143000
    assert result["driver_paid_vnd"] + 15500 == 155200
    assert result["guarantee_vnd"] == 18150


def test_topup_uses_private_intercity_commission(tmp_path: Path) -> None:
    adapter = LocalEscrowAdapter(tmp_path / "escrow.sqlite")
    adapter.execute(
        command(
            "DEPOSIT_INTERCITY",
            {
                "passenger": "p",
                "driver": "d",
                "amount_vnd": 200000,
                "service_code": "CAR_INTERCITY_POOL",
            },
        )
    )
    adapter.execute(command("TOPUP", {"amount_vnd": 118000}))
    result = finish(adapter)
    assert result["final_vnd"] == 318000
    assert result["driver_paid_vnd"] == 270300
    assert result["platform_paid_vnd"] == 47700


def test_topup_compensation_restores_original_fare_and_commission(tmp_path: Path) -> None:
    adapter = LocalEscrowAdapter(tmp_path / "escrow.sqlite")
    adapter.execute(
        command(
            "DEPOSIT_INTERCITY",
            {
                "passenger": "p",
                "driver": "d",
                "amount_vnd": 200000,
                "service_code": "CAR_INTERCITY_POOL",
            },
        )
    )
    adapter.execute(command("TOPUP", {"amount_vnd": 118000}))
    adapter.execute(command("REVERT_TOPUP"))
    result = finish(adapter)
    assert result["final_vnd"] == 200000
    assert result["driver_paid_vnd"] == 180000
    assert result["refunded_vnd"] == 118000
    assert result["topup_mode"] is False


def test_merge_cannot_increase_price(tmp_path: Path) -> None:
    adapter = LocalEscrowAdapter(tmp_path / "escrow.sqlite")
    adapter.execute(
        command(
            "DEPOSIT_INTERCITY",
            {
                "passenger": "p",
                "driver": "d",
                "amount_vnd": 220000,
                "service_code": "CAR_INTERCITY_POOL",
            },
        )
    )
    with pytest.raises(EscrowError):
        adapter.execute(command("MERGE", {"final_vnd": 230000, "driver": "d2"}))
    result = adapter.execute(command("MERGE", {"final_vnd": 200000, "driver": "d2"})).snapshot
    assert result["driver"] == "d2"
    assert result["refunded_vnd"] == 20000


def test_cancel_exact_allocations_and_fund(tmp_path: Path) -> None:
    adapter = LocalEscrowAdapter(tmp_path / "escrow.sqlite")
    pool(adapter)
    result = adapter.execute(
        command("CANCEL", {"fee_vnd": 31000, "driver_vnd": 15500, "fund_vnd": 15500})
    ).snapshot
    assert result["refunded_vnd"] == 143000
    assert result["fund_balance_vnd"] == 5015500
    with pytest.raises(EscrowError):
        adapter.execute(command("START"))


def test_dispute_freezes_and_resolves_exactly(tmp_path: Path) -> None:
    adapter = LocalEscrowAdapter(tmp_path / "escrow.sqlite")
    pool(adapter)
    adapter.execute(command("DISPUTE"))
    with pytest.raises(EscrowError):
        adapter.execute(command("CANCEL"))
    result = adapter.execute(
        command("RESOLVE", {"passenger_vnd": 100000, "driver_vnd": 70000, "platform_vnd": 4000})
    ).snapshot
    assert result["status"] == "RESOLVED"
    assert result["balance_vnd"] == 0


@pytest.mark.parametrize("amount", [True, -1, 0, 0.5, 1001])
def test_invalid_amounts_rejected(tmp_path: Path, amount: object) -> None:
    adapter = LocalEscrowAdapter(tmp_path / "escrow.sqlite")
    with pytest.raises(EscrowError):
        adapter.execute(
            command(
                "DEPOSIT_FIXED",
                {
                    "passenger": "p",
                    "driver": "d",
                    "amount_vnd": amount,
                    "service_code": "BIKE_URBAN",
                },
            )
        )


def test_hmac_rejects_tampering_and_expiry() -> None:
    secret = "s" * 40
    signature = sign_webhook(b'{"event":"deposit"}', 1000, secret)
    verify_webhook(b'{"event":"deposit"}', "1000", signature, secret, now=1050)
    with pytest.raises(EscrowError, match="SIGNATURE"):
        verify_webhook(b"tampered", "1000", signature, secret, now=1050)
    with pytest.raises(EscrowError, match="EXPIRED"):
        verify_webhook(b'{"event":"deposit"}', "1000", signature, secret, now=1500)
