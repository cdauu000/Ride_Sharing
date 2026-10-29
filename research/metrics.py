"""Query-clustered, paired evaluation; non-significant findings stay non-significant."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

from research.models import expected_calibration_error


def ranking_by_query(
    rows: Sequence[Mapping[str, Any]], scores: Sequence[float]
) -> dict[str, dict[str, Any]]:
    if len(rows) != len(scores):
        raise ValueError("Rows and scores must align")
    groups: dict[str, list[tuple[Mapping[str, Any], float]]] = defaultdict(list)
    for row, score in zip(rows, scores, strict=True):
        if not math.isfinite(float(score)):
            raise ValueError("Non-finite ranking score")
        groups[str(row["request_id"])].append((row, float(score)))
    result = {}
    for query, alternatives in groups.items():
        alternatives.sort(key=lambda value: (-value[1], str(value[0]["candidate_id"])))
        selected_positions = [
            index + 1 for index, (row, _) in enumerate(alternatives) if row.get("selected") == 1
        ]
        if len(selected_positions) > 1:
            raise ValueError("A query cannot have more than one observed selected candidate")
        position = selected_positions[0] if selected_positions else None
        result[query] = {
            "ndcg5": (1 / math.log2(position + 1) if position <= 5 else 0.0) if position else None,
            "hr1": float(position == 1) if position else None,
            "hr3": float(position <= 3) if position else None,
            "mrr": 1 / position if position else None,
            "outside_option": position is None,
            "segment": alternatives[0][0].get("segment", "UNKNOWN"),
            "is_raining": bool(alternatives[0][0].get("is_raining")),
        }
    return result


def summarize_ranking(per_query: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "queries": len(per_query),
        "outside_queries": sum(bool(row["outside_option"]) for row in per_query.values()),
    }
    for metric in ("ndcg5", "hr1", "hr3", "mrr"):
        values = [float(row[metric]) for row in per_query.values() if row.get(metric) is not None]
        result[metric] = float(np.mean(values)) if values else None
    return result


def paired_bootstrap(
    baseline: Sequence[float],
    proposed: Sequence[float],
    *,
    seed: int = 0,
    resamples: int = 1000,
) -> dict[str, Any]:
    a, b = np.asarray(baseline, dtype=float), np.asarray(proposed, dtype=float)
    if len(a) != len(b) or len(a) < 2 or not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError("At least two finite aligned pairs are required")
    if resamples < 100:
        raise ValueError("At least 100 resamples are required")
    differences = b - a
    generator = np.random.default_rng(seed)
    bootstrapped = np.asarray(
        [differences[generator.integers(0, len(a), len(a))].mean() for _ in range(resamples)]
    )
    low, high = np.quantile(bootstrapped, [0.025, 0.975])
    mean, sd = float(differences.mean()), float(differences.std(ddof=1))
    if np.all(differences == 0):
        p_value = 1.0
    else:
        randomized = np.asarray(
            [
                abs(float((differences * generator.choice([-1, 1], len(a))).mean()))
                for _ in range(resamples)
            ]
        )
        p_value = float((1 + np.sum(randomized >= abs(mean) - 1e-15)) / (resamples + 1))
    return {
        "pairs": len(a),
        "resamples": resamples,
        "seed": seed,
        "baseline_mean": float(a.mean()),
        "proposed_mean": float(b.mean()),
        "difference": mean,
        "difference_std": sd,
        "ci95": [float(low), float(high)],
        "cohens_d_paired": mean / sd if sd > 0 else None,
        "relative_lift": mean / abs(float(a.mean())) if a.mean() != 0 else None,
        "permutation_p_value_two_sided": p_value,
        "evidence_positive": bool(low > 0 and p_value < 0.05),
    }


def compare_rankings(
    baseline: Mapping[str, Mapping[str, Any]],
    proposed: Mapping[str, Mapping[str, Any]],
    seed: int = 0,
) -> dict[str, Any]:
    if set(baseline) != set(proposed):
        raise ValueError("Paired comparison requires the same query IDs")
    result = {}
    for metric in ("ndcg5", "hr1", "hr3", "mrr"):
        queries = sorted(
            q
            for q in baseline
            if baseline[q].get(metric) is not None and proposed[q].get(metric) is not None
        )
        result[metric] = (
            paired_bootstrap(
                [baseline[q][metric] for q in queries],
                [proposed[q][metric] for q in queries],
                seed=seed,
            )
            if len(queries) >= 2
            else {"status": "INSUFFICIENT_SELECTED_QUERIES", "pairs": len(queries)}
        )
    return result


def probability_metrics(labels: Sequence[int], probabilities: Sequence[float]) -> dict[str, Any]:
    y, p = np.asarray(labels), np.asarray(probabilities, dtype=float)
    if len(y) == 0 or len(y) != len(p):
        raise ValueError("Nonempty aligned probability labels required")
    return {
        "observations": len(y),
        "brier_score": float(brier_score_loss(y, p)),
        "log_loss": float(log_loss(y, np.clip(p, 1e-8, 1 - 1e-8), labels=[0, 1])),
        "roc_auc": float(roc_auc_score(y, p)) if len(set(y.tolist())) == 2 else None,
        "ece": expected_calibration_error(y, p),
    }


def h9_segment_test(
    baseline: Mapping[str, Mapping[str, Any]],
    proposed: Mapping[str, Mapping[str, Any]],
    seed: int = 0,
) -> dict[str, Any]:
    """Test the *difference in uplift*, not merely two separate significance tests."""
    generator = np.random.default_rng(seed)
    segments = {}
    effects: dict[str, list[float]] = {"URBAN_MULTI": [], "OTHER": []}
    for query in sorted(set(baseline) & set(proposed)):
        a, b = baseline[query], proposed[query]
        if a.get("hr1") is None or b.get("hr1") is None:
            continue
        segment = "URBAN_MULTI" if a.get("segment") == "URBAN_MULTI" else "OTHER"
        effects[segment].append(float(b["hr1"]) - float(a["hr1"]))
    for segment in ("URBAN_MULTI", "URBAN_GROUP", "INTERCITY"):
        queries = {q for q in baseline if baseline[q].get("segment") == segment}
        segments[segment] = compare_rankings(
            {q: baseline[q] for q in queries}, {q: proposed[q] for q in queries}, seed
        )
    a, b = np.asarray(effects["URBAN_MULTI"]), np.asarray(effects["OTHER"])
    if min(len(a), len(b)) < 2:
        return {
            "hypothesis": "H9",
            "status": "INSUFFICIENT_SEGMENTS",
            "supported": None,
            "segments": segments,
        }
    delta = float(a.mean() - b.mean())
    bootstrap = [
        float(
            generator.choice(a, len(a), replace=True).mean()
            - generator.choice(b, len(b), replace=True).mean()
        )
        for _ in range(1000)
    ]
    low, high = np.quantile(bootstrap, [0.025, 0.975])
    pooled = np.concatenate([a, b])
    randomized = []
    for _ in range(1000):
        shuffled = generator.permutation(pooled)
        randomized.append(abs(float(shuffled[: len(a)].mean() - shuffled[len(a) :].mean())))
    p_value = float((1 + np.sum(np.asarray(randomized) >= abs(delta) - 1e-15)) / 1001)
    return {
        "hypothesis": "H9",
        "status": "ANALYZED",
        "difference_in_hr1_uplift": delta,
        "ci95": [float(low), float(high)],
        "permutation_p_value_two_sided": p_value,
        "supported": bool(low > 0 and p_value < 0.05),
        "segments": segments,
        "weather_strata": {
            str(raining): compare_rankings(
                {q: baseline[q] for q in baseline if baseline[q].get("is_raining") == raining},
                {q: proposed[q] for q in proposed if proposed[q].get("is_raining") == raining},
                seed,
            )
            for raining in (False, True)
        },
    }


def holm_adjust(p_values: Mapping[str, float]) -> dict[str, float]:
    ordered = sorted(p_values.items(), key=lambda pair: pair[1])
    adjusted: dict[str, float] = {}
    previous = 0.0
    for index, (name, value) in enumerate(ordered):
        previous = max(previous, min(1.0, value * (len(ordered) - index)))
        adjusted[name] = previous
    return adjusted


def expected_utility_regret(
    candidate_ids: Sequence[str],
    scores: Sequence[float],
    evaluator_utilities: Mapping[str, float],
    outside_utility: float,
) -> float:
    """Evaluation-only utility reference; never call from feature construction or fitting."""
    if not candidate_ids:
        return 0.0
    if len(candidate_ids) != len(scores) or set(candidate_ids) - evaluator_utilities.keys():
        raise ValueError("Utility reference must cover exactly the evaluated alternatives")
    chosen = candidate_ids[int(np.argmax(scores))]
    optimum = max(outside_utility, *(evaluator_utilities[candidate] for candidate in candidate_ids))
    return float(max(0.0, optimum - evaluator_utilities[chosen]))
