"""Read-only financial reconciliation for an isolated local acceptance run."""

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any


def collect(database: Path, journal: Path) -> dict[str, Any]:
    with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN")
        payouts = []
        for row in db.execute(
            "SELECT b.id,b.service_code,b.ride_status,b.price_status,p.data FROM bookings b JOIN driver_payouts p ON p.booking_id=b.id ORDER BY b.id"
        ):
            payout = {**dict(row), "data": json.loads(row["data"])}
            values = payout["data"]
            payout["balanced"] = values["gross_fare_charged_vnd"] + values[
                "guarantee_amount_vnd"
            ] == (
                values["total_driver_payout_vnd"]
                + values["platform_net_amount_vnd"]
                + values["fund_contribution_vnd"]
            )
            payouts.append(payout)
        balance = db.execute("SELECT balance_vnd FROM fund_account WHERE id=1").fetchone()[0]
        ledger = db.execute(
            "SELECT COALESCE(SUM(amount_signed_vnd),0) FROM fund_ledger"
        ).fetchone()[0]
        job_states = {
            row[0]: row[1]
            for row in db.execute("SELECT status,COUNT(*) FROM scheduled_jobs GROUP BY status")
        }
        booking_states = {
            row[0]: row[1]
            for row in db.execute("SELECT ride_status,COUNT(*) FROM bookings GROUP BY ride_status")
        }
    with sqlite3.connect(journal.resolve().as_uri() + "?mode=ro", uri=True) as escrow:
        journal_balance = escrow.execute("SELECT balance FROM escrow_fund WHERE id=1").fetchone()[0]
    fields = [
        "gross_fare_charged_vnd",
        "guarantee_amount_vnd",
        "total_driver_payout_vnd",
        "platform_net_amount_vnd",
        "fund_contribution_vnd",
    ]
    totals = {field: sum(row["data"][field] for row in payouts) for field in fields}
    return {
        "mode": "LOCAL_SIMULATION",
        "balance_db_vnd": balance,
        "balance_journal_vnd": journal_balance,
        "ledger_sum_vnd": ledger,
        "fund_balanced": balance == journal_balance == ledger,
        "all_payouts_balanced": all(row["balanced"] for row in payouts),
        "job_states": job_states,
        "booking_states": booking_states,
        "totals": totals,
        "payouts": payouts,
        "database_sha256": hashlib.sha256(database.read_bytes()).hexdigest(),
        "journal_sha256": hashlib.sha256(journal.read_bytes()).hexdigest(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    args = parser.parse_args()
    output = args.run / "financial-evidence.json"
    if output.exists():
        raise SystemExit("Evidence is immutable; use a new run directory or output version.")
    evidence = collect(args.run / "rise.db", args.run / "escrow.db")
    output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    assert evidence["fund_balanced"] and evidence["all_payouts_balanced"], "Financial mismatch"
    assert not any(
        evidence["job_states"].get(state, 0) for state in ("FAILED_RETRY", "DEAD_LETTER")
    ), "Unresolved jobs"
    print("Read-only reconciliation passed. Evidence saved without session or wallet secrets.")


if __name__ == "__main__":
    main()
