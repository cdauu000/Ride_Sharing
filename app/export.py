"""Export observable snapshots without raw coordinates or hidden simulator state."""

import argparse
import json
import os
from pathlib import Path

from sqlalchemy import select

from app.config import Settings
from app.context import create_context
from app.models import Auxiliary, Booking, Candidate
from research.data import export_observation, write_dataset


def export_training(output: Path, salt: str) -> dict:
    context = create_context(Settings())
    rows = []
    with context.db.transaction() as session:
        bookings = {
            b.request_id: b for b in session.scalars(select(Booking).order_by(Booking.created_at))
        }
        for candidate in session.scalars(
            select(Candidate).order_by(Candidate.run_id, Candidate.id)
        ):
            feature = candidate.data.get("features")
            if not feature:
                continue
            booking = bookings.get(candidate.request_id)
            # A repeated menu exposure is its own query group; never mix two displayed runs.
            observed = {
                **feature,
                "request_id": candidate.run_id,
                "shown_position": candidate.data.get("shown_position"),
                "shown_reason": candidate.data.get("shown_reason"),
                "exposure_propensity": candidate.data.get("exposure_propensity", 1),
                "selected": int(bool(booking and booking.data.get("candidate_id") == candidate.id)),
            }
            if observed["selected"]:
                terminal = booking.ride_status in {
                    "COMPLETED",
                    "EXPIRED",
                    "NO_SHOW",
                    "CANCELLED_BY_PASSENGER",
                    "CANCELLED_BY_DRIVER",
                    "CANCELLED_BY_SYSTEM",
                }
                observed.update(
                    booking_id=booking.id,
                    driver_accepted=1
                    if booking.confirmed_at is not None
                    else 0
                    if terminal
                    else None,
                    ride_started=1
                    if booking.data.get("actual_pickup_at") is not None
                    else 0
                    if terminal
                    else None,
                    completed=int(booking.ride_status == "COMPLETED") if terminal else None,
                    unmatched_cause=booking.unmatched_cause,
                    final_price_vnd=booking.final_price_vnd,
                    pool_final_matched=1
                    if booking.price_status == "MATCHED_LOCKED"
                    else 0
                    if booking.price_status == "UNMATCHED_LOCKED"
                    and booking.unmatched_cause == "NO_COMPATIBLE"
                    else None,
                )
                end = booking.data.get("completed_at", booking.data.get("ended_at"))
                if end is not None:
                    from datetime import UTC, datetime

                    observed["outcome_at"] = datetime.fromtimestamp(end, UTC).isoformat()
            rows.append(export_observation(observed, salt))
    versions = {row.get("pricing_version") for row in rows}
    if len(versions) > 1:
        raise ValueError("Export each pricing version separately before training")
    return write_dataset(
        rows,
        output,
        {
            "source": "OBSERVED_API_TRANSACTIONS",
            "evidence_level": "LOCAL_DEMO_OR_RECORDED_TRAFFIC",
            "pricing_versions": sorted(versions),
            "query_group": "recommendation_run_id",
            "raw_coordinates_exported": False,
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=["training", "surveys"])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.kind == "training":
        salt = os.getenv("RISE_EXPORT_SALT")
        if not salt:
            raise SystemExit("RISE_EXPORT_SALT is required; keep it outside the dataset")
        manifest = export_training(args.output, salt)
        print(json.dumps({"rows": manifest.get("rows"), "sha256": manifest.get("sha256")}))
    else:
        if args.output.exists():
            raise FileExistsError(args.output)
        context = create_context(Settings())
        with context.db.transaction() as session:
            records = [
                r.data for r in session.scalars(select(Auxiliary).where(Auxiliary.kind == "SURVEY"))
            ]
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
        print(f"Exported {len(records)} anonymous survey responses")


if __name__ == "__main__":
    main()
