"""Strictly observed training data, temporal splits, and immutable manifests."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

SERVICES = (
    "BIKE_URBAN",
    "CAR_URBAN_PRIVATE",
    "CAR_URBAN_POOL",
    "CAR_INTERCITY_PRIVATE",
    "CAR_INTERCITY_POOL",
)
NUMERIC_FEATURES = (
    "is_raining",
    "has_luggage",
    "hour_of_day",
    "day_of_week",
    "direct_distance_km",
    "direct_duration_min",
    "passenger_count",
    "pickup_window_width_min",
    "budget_min",
    "budget_max",
    "lead_time_hours",
    "max_passenger_detour_ratio",
    "max_walk_m",
    "effective_price_vnd",
    "pool_quote_price_vnd",
    "pool_unmatched_price_vnd",
    "fare_matched_est_vnd",
    "planned_pickup_eta_min",
    "schedule_deviation_min",
    "in_vehicle_duration_min",
    "detour_ratio",
    "extra_stops_count",
    "walk_m",
    "driver_rating_bayesian",
    "seats_currently_occupied",
    "p_match_oof_est",
    "p_fulfill_oof_est",
    "p_fill_oof_est",
    "user_hist_trip_count",
    "user_hist_bike_share",
    "user_hist_pool_share",
    "user_hist_private_share",
    "user_hist_cancel_rate",
    "is_existing_plan",
    "active_pool_requests_15m_in_origin_zone",
    "open_pool_plans_same_direction_in_radius",
)
CATEGORICAL_FEATURES = ("service_code", "mode", "booking_type", "candidate_source_type")
LABELS = (
    "selected",
    "driver_accepted",
    "trip_confirmed_at_T72",
    "ride_started",
    "completed",
    "pool_final_matched",
    "unmatched_cause",
    "final_price_vnd",
)
METADATA = (
    "request_id",
    "candidate_id",
    "timestamp_utc",
    "user_id_hash",
    "origin_zone_id",
    "dest_zone_id",
    "split_set",
    "shown_position",
    "shown_reason",
    "exposure_propensity",
    "dataset_version",
    "pricing_version",
    "scenario_version",
    "model_versions_json",
    "booking_id",
    "segment",
    "outcome_at",
    "history_as_of",
)
ALLOWED_EXPORT = frozenset(NUMERIC_FEATURES + CATEGORICAL_FEATURES + LABELS + METADATA)
FORBIDDEN_FRAGMENTS = (
    "theta",
    "utility_true",
    "hidden",
    "true_p",
    "aversion",
    "noise_scale",
    "latent",
    "willingness_to_pay",
    "oracle",
    "wait_threshold",
    "price_gamma",
)


class FeatureFirewallError(ValueError):
    """A hidden variable or invalid point-in-time snapshot reached the boundary."""


def export_observation(observation: Mapping[str, Any], salt: str) -> dict[str, Any]:
    """Copy an observed transaction into an explicit allowlist, never a hidden object.

    Labels are retained separately for supervised targets; feature_vector never reads them.
    Exact coordinates and arbitrary new keys are discarded, not serialized to disk.
    """
    if not salt:
        raise FeatureFirewallError("An identity hashing salt is required")

    def check_nested(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                if any(fragment in str(key).lower() for fragment in FORBIDDEN_FRAGMENTS):
                    raise FeatureFirewallError(f"Forbidden field at export boundary: {key}")
                check_nested(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                check_nested(item)

    check_nested(observation)
    result = {key: observation[key] for key in sorted(ALLOWED_EXPORT) if key in observation}
    if "model_versions_json" in result:
        versions = result["model_versions_json"]
        if not isinstance(versions, Mapping) or any(
            key not in ("ltr", "p_match", "p_fulfill", "p_fill", "temperature")
            or not isinstance(value, str)
            or len(value) > 128
            for key, value in versions.items()
        ):
            raise FeatureFirewallError("Model lineage must contain only named version strings")
    for key in ("request_id", "candidate_id", "timestamp_utc", "service_code"):
        if key not in result:
            raise FeatureFirewallError(f"Missing observation field: {key}")
    timestamp = datetime.fromisoformat(str(result["timestamp_utc"]))
    if timestamp.tzinfo is None:
        raise FeatureFirewallError("Observation timestamps must include a UTC offset")
    if observation.get("history_as_of"):
        history_at = datetime.fromisoformat(str(observation["history_as_of"]))
        if history_at >= timestamp:
            raise FeatureFirewallError("History must predate the request")
    if "user_id" in observation:
        result["user_id_hash"] = hashlib.sha256(
            (salt + ":" + str(observation["user_id"])).encode()
        ).hexdigest()
    for key in NUMERIC_FEATURES:
        value = result.get(key)
        if value is not None and not math.isfinite(float(value)):
            raise FeatureFirewallError(f"Non-finite feature: {key}")
    if result["service_code"] not in SERVICES:
        raise FeatureFirewallError("Unknown service")
    return result


def temporal_split(
    rows: Iterable[Mapping[str, Any]],
    train_fraction: float = 0.65,
    validation_fraction: float = 0.15,
) -> dict[str, list[dict[str, Any]]]:
    """Split whole query groups; identical timestamps always stay on one side.

    A final test partition is required. Calling this never shuffles observations.
    """
    if not (
        0 < train_fraction < 1
        and 0 < validation_fraction < 1
        and train_fraction + validation_fraction < 1
    ):
        raise ValueError("Fractions must leave nonempty train, validation, and test ranges")
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for source in rows:
        row = dict(source)
        groups[str(row["request_id"])].append(row)
    by_time: dict[str, list[str]] = defaultdict(list)
    for query, items in groups.items():
        timestamps = {str(item["timestamp_utc"]) for item in items}
        if len(timestamps) != 1:
            raise ValueError(f"Query {query} has inconsistent quote timestamps")
        by_time[next(iter(timestamps))].append(query)
    times = sorted(by_time, key=lambda stamp: datetime.fromisoformat(stamp))
    if len(times) < 3:
        raise ValueError("At least three distinct request timestamps are required")
    train_end = min(max(1, int(len(times) * train_fraction)), len(times) - 2)
    val_end = min(
        max(train_end + 1, int(len(times) * (train_fraction + validation_fraction))), len(times) - 1
    )
    result: dict[str, list[dict[str, Any]]] = {"TRAIN": [], "VAL": [], "TEST": []}
    for index, timestamp in enumerate(times):
        split = "TRAIN" if index < train_end else "VAL" if index < val_end else "TEST"
        for query in sorted(by_time[timestamp]):
            result[split].extend(dict(item, split_set=split) for item in groups[query])
    return result


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def write_dataset(
    rows: list[dict[str, Any]], target: Path, manifest: Mapping[str, Any]
) -> dict[str, Any]:
    """Write newline JSON plus Parquet when pyarrow is installed, with content hashes.

    Existing different content is refused to preserve the frozen dataset version.
    """
    target.mkdir(parents=True, exist_ok=True)
    payload = b"\n".join(canonical_bytes(row) for row in rows) + b"\n"
    dataset_path = target / "observations.jsonl"
    if dataset_path.exists() and dataset_path.read_bytes() != payload:
        raise FileExistsError("Dataset directory contains a different immutable dataset")
    dataset_path.write_bytes(payload)
    metadata = dict(
        manifest, sha256=hashlib.sha256(payload).hexdigest(), rows=len(rows), format="jsonl"
    )
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        metadata["parquet_status"] = "pyarrow_not_installed"
    else:
        pq.write_table(pa.Table.from_pylist(rows), target / "observations.parquet")
        metadata["parquet_status"] = "written"
    (target / "manifest.json").write_bytes(canonical_bytes(metadata))
    return metadata


def read_dataset(path: Path) -> list[dict[str, Any]]:
    if path.suffix == ".parquet":
        import pyarrow.parquet as pq

        return pq.read_table(path).to_pylist()
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def censor_unavailable_outcomes(
    rows: Iterable[Mapping[str, Any]], cutoff: str
) -> list[dict[str, Any]]:
    """Keep contemporaneous choices, embargo outcomes not yet known at fitting time."""
    boundary = datetime.fromisoformat(cutoff)
    result = []
    for source in rows:
        row = dict(source)
        if row.get("outcome_at") and datetime.fromisoformat(str(row["outcome_at"])) >= boundary:
            for label in LABELS:
                if label != "selected":
                    row.pop(label, None)
        result.append(row)
    return result
