"""Offline models and online inference with explicit feature/label separation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from lightgbm import LGBMClassifier, LGBMRanker
from scipy.optimize import minimize, minimize_scalar
from scipy.special import logsumexp
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from research.data import NUMERIC_FEATURES, SERVICES, canonical_bytes

Row = Mapping[str, Any]
MATCH_FEATURES = (
    "hour_of_day",
    "day_of_week",
    "is_raining",
    "direct_distance_km",
    "passenger_count",
    "max_passenger_detour_ratio",
    "pickup_window_width_min",
    "lead_time_hours",
    "active_pool_requests_15m_in_origin_zone",
    "open_pool_plans_same_direction_in_radius",
)


def feature_matrix(rows: Sequence[Row], interactions: bool = False) -> np.ndarray:
    """Construct only frozen point-in-time features; labels can never enter here."""
    vectors: list[list[float]] = []
    for row in rows:
        service = str(row.get("service_code", ""))
        vector = [float(row.get(key) or 0) for key in NUMERIC_FEATURES]
        vector.extend(float(service == value) for value in SERVICES)
        vector.extend(
            [
                float(row.get("mode") == "INTERCITY"),
                float(row.get("booking_type") == "SCHEDULED"),
                float(row.get("candidate_source_type") == "EXISTING_POOL_PLAN"),
            ]
        )
        if interactions:
            bike, pool = float(service == "BIKE_URBAN"), float("POOL" in service)
            distance = float(row.get("direct_distance_km") or 0)
            width = max(1, float(row.get("pickup_window_width_min") or 0))
            budget_min = float(row.get("budget_min") or 0)
            budget_span = max(1, float(row.get("budget_max") or 0) - budget_min)
            vector.extend(
                [
                    bike * float(row.get("is_raining") or 0),
                    bike * distance,
                    pool * float(row.get("detour_ratio") or 0) / width,
                    (float(row.get("effective_price_vnd") or 0) - budget_min) / budget_span,
                ]
            )
        vectors.append(vector)
    return np.asarray(vectors, dtype=float)


def match_matrix(rows: Sequence[Row]) -> np.ndarray:
    return np.asarray(
        [[float(row.get(key) or 0) for key in MATCH_FEATURES] for row in rows], dtype=float
    )


def grouped(rows: Sequence[Row]) -> tuple[list[dict[str, Any]], list[int]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(str(row["request_id"]), []).append(dict(row))
    ordered = sorted(
        groups.values(),
        key=lambda items: (str(items[0]["timestamp_utc"]), str(items[0]["request_id"])),
    )
    return [item for items in ordered for item in items], [len(items) for items in ordered]


def expected_calibration_error(
    labels: Sequence[float], probabilities: Sequence[float], bins: int = 10
) -> float:
    y, p = np.asarray(labels, dtype=float), np.asarray(probabilities, dtype=float)
    if len(y) == 0 or len(y) != len(p):
        raise ValueError("Nonempty aligned labels and probabilities are required")
    if not np.isfinite(p).all() or np.any((p < 0) | (p > 1)):
        raise ValueError("Invalid probabilities")
    indexes = np.minimum((p * bins).astype(int), bins - 1)
    return float(
        sum(
            np.mean(indexes == b) * abs(y[indexes == b].mean() - p[indexes == b].mean())
            for b in range(bins)
            if np.any(indexes == b)
        )
    )


def _pool_observations(rows: Sequence[Row]) -> list[Row]:
    return [
        r
        for r in rows
        if r.get("service_code") == "CAR_URBAN_POOL"
        and r.get("pool_final_matched") in (0, 1)
        and (r.get("pool_final_matched") == 1 or r.get("unmatched_cause") == "NO_COMPATIBLE")
    ]


def calibration_partitions(rows: Sequence[Row]) -> tuple[list[Row], list[Row]]:
    """Fit calibration on an earlier validation block, measure ECE on a later block."""
    times = {str(row["request_id"]): str(row["timestamp_utc"]) for row in rows}
    queries = sorted(times, key=lambda query: (times[query], query))
    cut = len(queries) // 2
    first = set(queries[:cut])
    return (
        [row for row in rows if str(row["request_id"]) in first],
        [row for row in rows if str(row["request_id"]) not in first],
    )


@dataclass
class ProbabilityModel:
    """P(match) fitted only to resolved Pool bookings; Beta prior handles cold start."""

    estimator: Any = None
    calibrator: Any = None
    prior: float = 0.5
    calibration_ece: float | None = None
    calibration_status: str = "NOT_FITTED"
    training_queries: tuple[str, ...] = ()

    def fit(self, rows: Sequence[Row], validation: Sequence[Row] = ()) -> ProbabilityModel:
        observed = _pool_observations(rows)
        labels = np.asarray([int(r["pool_final_matched"]) for r in observed])
        self.training_queries = tuple(sorted({str(r["request_id"]) for r in observed}))
        self.prior = float((labels.sum() + 1) / (len(labels) + 2))
        if len(observed) >= 10 and len(set(labels)) == 2:
            self.estimator = LGBMClassifier(
                n_estimators=70,
                num_leaves=12,
                min_child_samples=8,
                random_state=0,
                n_jobs=1,
                verbosity=-1,
                deterministic=True,
                force_col_wise=True,
            )
            self.estimator.fit(match_matrix(observed), labels)
        calibration, gate = calibration_partitions(validation)
        valid = _pool_observations(calibration)
        gate = _pool_observations(gate)
        if len(valid) >= 10 and len({int(r["pool_final_matched"]) for r in valid}) == 2:
            raw = self._raw(valid)
            self.calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.001, y_max=0.999)
            self.calibrator.fit(raw, [int(r["pool_final_matched"]) for r in valid])
            if len(gate) >= 10 and len({int(r["pool_final_matched"]) for r in gate}) == 2:
                self.calibration_ece = expected_calibration_error(
                    [int(r["pool_final_matched"]) for r in gate], self.predict(gate)
                )
                self.calibration_status = "VALIDATION_FITTED"
            else:
                self.calibration_status = "INSUFFICIENT_VALIDATION_GATE_LABELS"
        else:
            self.calibration_status = "INSUFFICIENT_VALIDATION_LABELS"
        return self

    def _raw(self, rows: Sequence[Row]) -> np.ndarray:
        if not rows:
            return np.empty(0)
        if self.estimator is None:
            return np.full(len(rows), self.prior)
        return self.estimator.predict_proba(match_matrix(rows))[:, 1]

    def predict(self, rows: Sequence[Row]) -> np.ndarray:
        probabilities = self._raw(rows)
        if self.calibrator is not None and len(probabilities):
            probabilities = self.calibrator.predict(probabilities)
        # Existing co-riding plan is structurally matched at quote time, not an ML guess.
        return np.asarray(
            [
                1.0 if row.get("is_existing_plan") else float(p)
                for row, p in zip(rows, probabilities, strict=True)
            ]
        )


def oof_match_predictions(
    rows: Sequence[Row], folds: int = 5
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    """Cross-fit five contiguous query-time blocks, strictly inside the training set.

    Models never fit held-out query labels. Each fold reserves its own calibration
    tail; validation/test rows are rejected to prevent accidental cross-split fitting.
    """
    if folds < 2:
        raise ValueError("At least two OOF folds are required")
    if any(r.get("split_set") not in (None, "TRAIN") for r in rows):
        raise ValueError("OOF fitting may only consume TRAIN rows")
    query_times = {str(row["request_id"]): str(row["timestamp_utc"]) for row in rows}
    queries = sorted(query_times, key=lambda query: (query_times[query], query))
    if len(queries) < folds:
        raise ValueError("Need at least one distinct query per OOF fold")
    blocks = np.array_split(np.asarray(queries, dtype=object), folds)
    predictions = np.empty(len(rows))
    provenance: list[dict[str, Any]] = []
    for index, block in enumerate(blocks):
        held_out = set(block.tolist())
        available = [q for q in queries if q not in held_out]
        cut = max(1, int(len(available) * 0.8))
        fit_ids, calibration_ids = set(available[:cut]), set(available[cut:])
        model = ProbabilityModel().fit(
            [r for r in rows if str(r["request_id"]) in fit_ids],
            [r for r in rows if str(r["request_id"]) in calibration_ids],
        )
        held_indexes = [i for i, r in enumerate(rows) if str(r["request_id"]) in held_out]
        predictions[held_indexes] = model.predict([rows[i] for i in held_indexes])
        provenance.append(
            {
                "fold": index,
                "train_queries": sorted(fit_ids | calibration_ids),
                "held_out_queries": sorted(held_out),
                "calibration_status": model.calibration_status,
            }
        )
    return predictions, provenance


@dataclass
class ConditionalLogit:
    """Conditional multinomial logit with a fixed-zero outside-option utility."""

    l2: float = 1.0
    scaler: Any = field(default_factory=StandardScaler)
    coefficients: np.ndarray | None = None
    converged: bool = False

    def fit(self, x: np.ndarray, labels: np.ndarray, groups: Sequence[int]) -> ConditionalLogit:
        if (
            not groups
            or any(size < 1 for size in groups)
            or sum(groups) != len(x)
            or len(x) != len(labels)
        ):
            raise ValueError("Query group sizes do not match observations")
        transformed = self.scaler.fit_transform(x)
        offsets = np.cumsum([0] + list(groups))

        def objective(coefficients: np.ndarray) -> tuple[float, np.ndarray]:
            scores = transformed @ coefficients
            group_max = np.maximum(0, np.maximum.reduceat(scores, offsets[:-1]))
            stable_scores = np.exp(scores - np.repeat(group_max, groups))
            denominator = group_max + np.log(
                np.exp(-group_max) + np.add.reduceat(stable_scores, offsets[:-1])
            )
            probabilities = np.exp(scores - np.repeat(denominator, groups))
            value = (
                float(denominator.sum() - labels @ scores)
                + self.l2 * float(coefficients @ coefficients) / 2
            )
            gradient = transformed.T @ (probabilities - labels) + self.l2 * coefficients
            return value / len(groups), gradient / len(groups)

        result = minimize(
            objective,
            np.zeros(transformed.shape[1]),
            method="L-BFGS-B",
            jac=True,
            options={"maxiter": 250, "ftol": 1e-9},
        )
        self.coefficients = result.x
        self.converged = bool(result.success)
        return self

    def predict(self, x: np.ndarray) -> np.ndarray:
        if self.coefficients is None:
            raise ValueError("Conditional logit has not been fitted")
        return self.scaler.transform(x) @ self.coefficients


def temperature_probabilities(
    scores: np.ndarray, groups: Sequence[int], temperature: float
) -> np.ndarray:
    if temperature <= 0 or sum(groups) != len(scores):
        raise ValueError("Positive temperature and aligned groups required")
    result = np.empty_like(scores, dtype=float)
    offset = 0
    for size in groups:
        values = scores[offset : offset + size] / temperature
        result[offset : offset + size] = np.exp(values - logsumexp(values))
        offset += size
    return result


def fit_temperature(
    scores: np.ndarray, labels: np.ndarray, groups: Sequence[int]
) -> tuple[float, float]:
    # Only selected groups have a categorical label for the candidate-only softmax.
    indexes: list[int] = []
    kept_groups: list[int] = []
    offset = 0
    for size in groups:
        if labels[offset : offset + size].sum() == 1:
            indexes.extend(range(offset, offset + size))
            kept_groups.append(size)
        offset += size
    if not kept_groups:
        raise ValueError("Temperature fitting requires selected validation queries")
    s, y = scores[indexes], labels[indexes]

    def nll(log_temperature: float) -> float:
        p = temperature_probabilities(s, kept_groups, float(np.exp(log_temperature)))
        return float(-np.sum(y * np.log(np.clip(p, 1e-12, 1))) / len(kept_groups))

    result = minimize_scalar(nll, bounds=(-4.0, 4.0), method="bounded")
    temperature = float(np.exp(result.x))
    ece = expected_calibration_error(y, temperature_probabilities(s, kept_groups, temperature))
    return temperature, ece


@dataclass
class FulfillModel:
    """Three non-censored sequential gates with conditional training populations."""

    stages: list[Any] = field(default_factory=list)
    priors: list[float] = field(default_factory=list)
    calibrators: list[Any] = field(default_factory=list)
    validation_ece: list[float | None] = field(default_factory=list)

    def fit(self, rows: Sequence[Row], validation: Sequence[Row] = ()) -> FulfillModel:
        self.stages, self.priors, self.calibrators, self.validation_ece = [], [], [], []

        def subset_for(source: Sequence[Row], stage: int) -> tuple[list[Row], np.ndarray]:
            subset, labels = [], []
            for row in source:
                intercity = row.get("service_code") == "CAR_INTERCITY_POOL"
                first_gate = "trip_confirmed_at_T72" if intercity else "driver_accepted"
                label = first_gate if stage == 0 else "ride_started" if stage == 1 else "completed"
                condition = None if stage == 0 else first_gate if stage == 1 else "ride_started"
                if row.get(label) in (0, 1) and (condition is None or row.get(condition) == 1):
                    subset.append(row)
                    labels.append(int(row[label]))
            return subset, np.asarray(labels)

        calibration, gate_rows = calibration_partitions(validation)
        for stage in range(3):
            subset, labels = subset_for(rows, stage)
            self.priors.append(float((labels.sum() + 1) / (len(labels) + 2)))
            estimator = None
            if len(subset) >= 10 and len(set(labels)) == 2:
                from sklearn.pipeline import make_pipeline

                estimator = make_pipeline(
                    StandardScaler(), LogisticRegression(max_iter=300, random_state=0)
                )
                estimator.fit(feature_matrix(subset), labels)
            self.stages.append(estimator)
            valid, targets = subset_for(calibration, stage)
            gate, gate_labels = subset_for(gate_rows, stage)
            calibrator, ece = None, None
            if len(valid) >= 10 and len(set(targets)) == 2:
                raw = (
                    np.full(len(valid), self.priors[-1])
                    if estimator is None
                    else estimator.predict_proba(feature_matrix(valid))[:, 1]
                )
                calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.001, y_max=0.999).fit(
                    raw, targets
                )
                if len(gate) >= 10 and len(set(gate_labels)) == 2:
                    gate_raw = (
                        np.full(len(gate), self.priors[-1])
                        if estimator is None
                        else estimator.predict_proba(feature_matrix(gate))[:, 1]
                    )
                    ece = expected_calibration_error(gate_labels, calibrator.predict(gate_raw))
            self.calibrators.append(calibrator)
            self.validation_ece.append(ece)
        return self

    def predict(self, rows: Sequence[Row]) -> np.ndarray:
        probabilities = np.ones(len(rows))
        for index, (estimator, prior) in enumerate(zip(self.stages, self.priors, strict=True)):
            gate = (
                np.full(len(rows), prior)
                if estimator is None
                else estimator.predict_proba(feature_matrix(rows))[:, 1]
            )
            if self.calibrators[index] is not None:
                gate = self.calibrators[index].predict(gate)
            probabilities *= gate
        return probabilities


def oof_fulfill_predictions(
    rows: Sequence[Row], folds: int = 5
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    """Cross-fit conditional completion probabilities; held-out labels never fit a stage."""
    times = {str(row["request_id"]): str(row["timestamp_utc"]) for row in rows}
    queries = sorted(times, key=lambda key: (times[key], key))
    if len(queries) < folds or folds < 2:
        raise ValueError("Need at least one distinct query per OOF fold")
    predictions = np.empty(len(rows))
    provenance = []
    for index, block in enumerate(np.array_split(np.asarray(queries, dtype=object), folds)):
        held = set(block.tolist())
        available = [key for key in queries if key not in held]
        cutoff = max(1, int(len(available) * 0.8))
        fit_ids, cal_ids = set(available[:cutoff]), set(available[cutoff:])
        model = FulfillModel().fit(
            [row for row in rows if str(row["request_id"]) in fit_ids],
            [row for row in rows if str(row["request_id"]) in cal_ids],
        )
        indexes = [i for i, row in enumerate(rows) if str(row["request_id"]) in held]
        predictions[indexes] = model.predict([rows[i] for i in indexes])
        provenance.append(
            {
                "fold": index,
                "train_queries": sorted(fit_ids | cal_ids),
                "held_out_queries": sorted(held),
            }
        )
    return predictions, provenance


@dataclass
class ModelBundle:
    match: ProbabilityModel
    rankers: dict[str, Any]
    fulfill: FulfillModel
    temperature: float | None = None
    selection_ece: float | None = None
    version: str = "unversioned"
    manifest: dict[str, Any] = field(default_factory=dict)

    @property
    def can_multiply_fulfillment(self) -> bool:
        return (
            self.temperature is not None
            and self.selection_ece is not None
            and self.selection_ece <= 0.05
            and self.match.calibration_ece is not None
            and self.match.calibration_ece <= 0.05
            and len(self.fulfill.validation_ece) == 3
            and all(value is not None and value <= 0.05 for value in self.fulfill.validation_ece)
        )

    def scores(self, rows: Sequence[Row], use_fulfillment: bool = False) -> np.ndarray:
        ordered, sizes = grouped(rows)
        prepared = with_match_estimates(ordered, self.match.predict(ordered))
        probabilities = self.fulfill.predict(prepared)
        prepared = [
            dict(row, p_fulfill_oof_est=float(p))
            for row, p in zip(prepared, probabilities, strict=True)
        ]
        raw = self.rankers["tree_full"].predict(feature_matrix(prepared, interactions=True))
        if use_fulfillment and self.can_multiply_fulfillment:
            raw = temperature_probabilities(raw, sizes, float(self.temperature)) * probabilities
        by_candidate = {
            str(row["candidate_id"]): float(score) for row, score in zip(ordered, raw, strict=True)
        }
        return np.asarray([by_candidate[str(row["candidate_id"])] for row in rows])


def with_match_estimates(rows: Sequence[Row], estimates: Sequence[float]) -> list[dict[str, Any]]:
    result = []
    for row, estimate in zip(rows, estimates, strict=True):
        item = dict(row, p_match_oof_est=float(estimate))
        if row.get("service_code") == "CAR_URBAN_POOL":
            item["effective_price_vnd"] = float(estimate) * float(
                row.get("fare_matched_est_vnd") or 0
            ) + (1 - float(estimate)) * float(row.get("pool_unmatched_price_vnd") or 0)
        result.append(item)
    return result


def train_bundle(train: Sequence[Row], validation: Sequence[Row], version: str) -> ModelBundle:
    if any(r.get("split_set") not in (None, "TRAIN") for r in train) or any(
        r.get("split_set") not in (None, "VAL") for r in validation
    ):
        raise ValueError("Training and calibration split labels must be respected")
    if {str(r["request_id"]) for r in train} & {str(r["request_id"]) for r in validation}:
        raise ValueError("A query appears in both training and validation")
    train_ordered, train_groups = grouped(train)
    validation_ordered, validation_groups = grouped(validation)
    estimates, provenance = oof_match_predictions(train_ordered)
    train_prepared = with_match_estimates(train_ordered, estimates)
    match = ProbabilityModel().fit(train_ordered, validation_ordered)
    validation_prepared = with_match_estimates(
        validation_ordered, match.predict(validation_ordered)
    )
    fulfillment = FulfillModel().fit(train_prepared, validation_prepared)
    fulfill_oof, fulfill_provenance = oof_fulfill_predictions(train_prepared)
    train_prepared = [
        dict(row, p_fulfill_oof_est=float(p))
        for row, p in zip(train_prepared, fulfill_oof, strict=True)
    ]
    validation_prepared = [
        dict(row, p_fulfill_oof_est=float(p))
        for row, p in zip(
            validation_prepared, fulfillment.predict(validation_prepared), strict=True
        )
    ]
    labels = np.asarray([int(r.get("selected") or 0) for r in train_prepared])
    rankers: dict[str, Any] = {}
    for interactions, suffix in ((False, "raw"), (True, "full")):
        x = feature_matrix(train_prepared, interactions)
        rankers[f"linear_{suffix}"] = ConditionalLogit().fit(x, labels, train_groups)
        tree = LGBMRanker(
            objective="lambdarank",
            n_estimators=80,
            num_leaves=15,
            min_child_samples=10,
            learning_rate=0.06,
            random_state=0,
            n_jobs=1,
            verbosity=-1,
            deterministic=True,
            force_col_wise=True,
        )
        tree.fit(x, labels, group=train_groups)
        rankers[f"tree_{suffix}"] = tree
    temperature, ece = None, None
    if validation_prepared:
        calibration, gate = calibration_partitions(validation_prepared)
        calibration, calibration_groups = grouped(calibration)
        gate, gate_groups = grouped(gate)
        scores = rankers["tree_full"].predict(feature_matrix(calibration, True))
        try:
            temperature, _ = fit_temperature(
                scores,
                np.asarray([int(r.get("selected") or 0) for r in calibration]),
                calibration_groups,
            )
            gate_scores = rankers["tree_full"].predict(feature_matrix(gate, True))
            probabilities = temperature_probabilities(gate_scores, gate_groups, temperature)
            labels = np.asarray([int(r.get("selected") or 0) for r in gate])
            indexes = []
            offset = 0
            for size in gate_groups:
                if labels[offset : offset + size].sum() == 1:
                    indexes.extend(range(offset, offset + size))
                offset += size
            ece = (
                expected_calibration_error(labels[indexes], probabilities[indexes])
                if indexes
                else None
            )
        except ValueError:
            pass
    bundle = ModelBundle(
        match,
        rankers,
        fulfillment,
        temperature,
        ece,
        version,
    )
    bundle.manifest = {
        "version": version,
        "oof_folds": provenance,
        "fulfillment_oof_folds": fulfill_provenance,
        "features": list(NUMERIC_FEATURES),
        "train_queries": len(train_groups),
        "validation_queries": len(validation_groups),
        "match_calibration_status": match.calibration_status,
        "match_validation_ece": match.calibration_ece,
        "selection_validation_ece": ece,
        "temperature": temperature,
        "fulfill_stage_validation_ece": bundle.fulfill.validation_ece,
        "fulfillment_multiplication_enabled": bundle.can_multiply_fulfillment,
        "test_used_for_fitting": False,
        "calibration_ece_measured_on": "LATER_VALIDATION_QUERIES_SEPARATE_FROM_CALIBRATION_FIT",
        "scientific_verdict": "NOT_EVALUATED",
    }
    return bundle


def save_bundle(bundle: ModelBundle, target: Path) -> dict[str, Any]:
    target.mkdir(parents=True, exist_ok=True)
    model_path = target / "bundle.joblib"
    if model_path.exists():
        raise FileExistsError("Model versions are immutable; choose a new directory")
    joblib.dump(bundle, model_path)
    manifest = dict(
        bundle.manifest, artifact_sha256=hashlib.sha256(model_path.read_bytes()).hexdigest()
    )
    (target / "manifest.json").write_bytes(canonical_bytes(manifest))
    return manifest


def load_bundle(target: Path) -> ModelBundle:
    """Load only operator-controlled artifacts after checking their stored hash.

    joblib is executable serialization; never point this at an uploaded/untrusted path.
    """
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    path = target / "bundle.joblib"
    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest["artifact_sha256"]:
        raise ValueError("Model artifact hash mismatch")
    bundle = joblib.load(path)
    if not isinstance(bundle, ModelBundle):
        raise ValueError("Invalid model bundle")
    return bundle
