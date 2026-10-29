from datetime import UTC, datetime, timedelta

import numpy as np

from research.models import (
    ConditionalLogit,
    ProbabilityModel,
    expected_calibration_error,
    feature_matrix,
    oof_fulfill_predictions,
    oof_match_predictions,
    temperature_probabilities,
)


def row(index: int, label: int) -> dict[str, object]:
    return {
        "request_id": str(index),
        "candidate_id": str(index),
        "service_code": "CAR_URBAN_POOL",
        "timestamp_utc": (datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=index)).isoformat(),
        "pool_final_matched": label,
        "unmatched_cause": "NO_COMPATIBLE" if not label else "NONE",
        "selected": 1,
        "direct_distance_km": 5.0 + label,
        "effective_price_vnd": 100_000,
    }


def test_label_values_never_become_features() -> None:
    a = row(0, 0)
    b = a | {"completed": 1, "final_price_vnd": 50_000, "pool_final_matched": 1, "selected": 0}
    np.testing.assert_array_equal(feature_matrix([a]), feature_matrix([b]))


def test_five_fold_predictions_exclude_held_out_queries() -> None:
    rows = [row(i, i % 2) for i in range(50)]
    estimates, provenance = oof_match_predictions(rows, folds=5)
    assert len(estimates) == len(rows)
    assert np.isfinite(estimates).all()
    for fold in provenance:
        assert set(fold["train_queries"]).isdisjoint(fold["held_out_queries"])
    assert len(provenance) == 5


def test_fulfillment_features_are_cross_fitted() -> None:
    rows = [
        row(i, i % 2)
        | {
            "driver_accepted": int(i % 3 != 0),
            "ride_started": int(i % 3 != 0 and i % 7 != 0),
            "completed": int(i % 3 != 0 and i % 7 != 0),
        }
        for i in range(50)
    ]
    values, provenance = oof_fulfill_predictions(rows)
    assert np.all((values > 0) & (values < 1))
    for fold in provenance:
        assert set(fold["train_queries"]).isdisjoint(fold["held_out_queries"])


def test_probability_cold_start_and_single_class_are_finite() -> None:
    model = ProbabilityModel().fit([row(i, 0) for i in range(10)])
    values = model.predict([row(11, 0), row(12, 1)])
    assert np.all((values > 0) & (values < 1))


def test_conditional_logit_uses_query_groups() -> None:
    x = np.array([[0.0], [1.0]] * 30)
    labels = np.array([0, 1] * 30)
    model = ConditionalLogit().fit(x, labels, [2] * 30)
    scores = model.predict(x)
    assert scores[1] > scores[0]


def test_softmax_is_stable_and_query_normalized() -> None:
    probabilities = temperature_probabilities(
        np.array([10000.0, 10001.0, -10000.0, -10001.0]), [2, 2], 0.7
    )
    assert abs(probabilities[:2].sum() - 1) < 1e-12
    assert abs(probabilities[2:].sum() - 1) < 1e-12
    assert expected_calibration_error([0, 1], [0, 1]) == 0
