"""Offline hypotheses and closed-loop comparisons with explicit evidence levels."""

from __future__ import annotations

import itertools
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from typing import Any

import numpy as np

from research.domain_engine import DomainSimulationEngine
from research.metrics import (
    compare_rankings,
    h9_segment_test,
    paired_bootstrap,
    probability_metrics,
    ranking_by_query,
    summarize_ranking,
)
from research.models import ModelBundle, feature_matrix, with_match_estimates
from research.simulator import SimulationConfig, Simulator, baseline_scores


def _policy_scorer(
    bundle: ModelBundle, policy: str
) -> Callable[[list[dict[str, Any]]], np.ndarray]:
    if policy == "baseline_match_model":

        def score_match(rows: list[dict[str, Any]]) -> np.ndarray:
            return baseline_scores(with_match_estimates(rows, bundle.match.predict(rows)))

        return score_match
    if policy in ("ltr", "ltr_fulfillment"):

        def score_ltr(rows: list[dict[str, Any]]) -> np.ndarray:
            return bundle.scores(rows, use_fulfillment=policy == "ltr_fulfillment")

        return score_ltr
    return baseline_scores


def _compare_runs(runs: list[dict[str, Any]], left: str, right: str, metric: str) -> dict[str, Any]:
    a = [run["metrics"][metric] for run in runs if run["policy"] == left]
    b = [run["metrics"][metric] for run in runs if run["policy"] == right]
    if len(a) < 2:
        return {"status": "INSUFFICIENT_SEEDS"}
    report = paired_bootstrap(a, b, seed=0)
    lower = any(word in metric for word in ("regret", "cancellation_rate", "unmatched"))
    report["desired_direction"] = "LOWER" if lower else "HIGHER"
    report["evidence_improvement"] = (
        report["ci95"][1] < 0 if lower else report["ci95"][0] > 0
    ) and report["permutation_p_value_two_sided"] < 0.05
    return report


class EmpiricalMatchBaseline:
    """Train-only, Beta-smoothed corridor/hour reference, not a test-set oracle."""

    def __init__(self, rows: Sequence[Mapping[str, Any]]) -> None:
        observed = [
            r
            for r in rows
            if r.get("service_code") == "CAR_URBAN_POOL"
            and r.get("pool_final_matched") in (0, 1)
            and (r.get("pool_final_matched") == 1 or r.get("unmatched_cause") == "NO_COMPATIBLE")
        ]
        self.global_rate = (sum(int(r["pool_final_matched"]) for r in observed) + 1) / (
            len(observed) + 2
        )
        self.counts: dict[tuple[str, str, int], tuple[int, int]] = {}
        for row in observed:
            key = self.key(row)
            success, count = self.counts.get(key, (0, 0))
            self.counts[key] = success + int(row["pool_final_matched"]), count + 1

    @staticmethod
    def key(row: Mapping[str, Any]) -> tuple[str, str, int]:
        return (
            str(row.get("origin_zone_id", "UNKNOWN")),
            str(row.get("dest_zone_id", "UNKNOWN")),
            int(row.get("hour_of_day") or 0) // 3,
        )

    def predict(self, rows: Sequence[Mapping[str, Any]]) -> np.ndarray:
        result = []
        for row in rows:
            success, count = self.counts.get(self.key(row), (0, 0))
            result.append(
                1.0
                if row.get("is_existing_plan")
                else (success + 5 * self.global_rate) / (count + 5)
            )
        return np.asarray(result)


def offline_report(
    bundle: ModelBundle, test: list[dict[str, Any]], train: list[dict[str, Any]]
) -> dict[str, Any]:
    if any(row.get("split_set") not in (None, "TEST") for row in test):
        raise ValueError("Final evaluation consumes TEST rows only")
    train_ids = {str(row["request_id"]) for row in train}
    if train_ids & {str(row["request_id"]) for row in test}:
        raise ValueError("Train and test queries overlap")
    prepared = with_match_estimates(test, bundle.match.predict(test))
    prepared = [
        dict(row, p_fulfill_oof_est=float(p))
        for row, p in zip(prepared, bundle.fulfill.predict(prepared), strict=True)
    ]
    baseline = ranking_by_query(prepared, baseline_scores(prepared))
    rankings = {}
    for name, model in bundle.rankers.items():
        rankings[name] = ranking_by_query(
            prepared, model.predict(feature_matrix(prepared, name.endswith("full")))
        )
    h1 = compare_rankings(baseline, rankings["tree_full"])
    h2 = {
        "raw": compare_rankings(rankings["linear_raw"], rankings["tree_raw"]),
        "full": compare_rankings(rankings["linear_full"], rankings["tree_full"]),
    }
    observed = [
        row
        for row in prepared
        if row.get("service_code") == "CAR_URBAN_POOL"
        and row.get("pool_final_matched") in (0, 1)
        and (row.get("pool_final_matched") == 1 or row.get("unmatched_cause") == "NO_COMPATIBLE")
    ]
    if observed:
        labels = [int(row["pool_final_matched"]) for row in observed]
        estimated = bundle.match.predict(observed)
        empirical = EmpiricalMatchBaseline(train).predict(observed)
        h3: dict[str, Any] = {
            "status": "OFFLINE_ONLY",
            "model": probability_metrics(labels, estimated),
            "spatiotemporal_baseline": probability_metrics(labels, empirical),
            "brier_improvement": paired_bootstrap(
                -np.square(np.asarray(labels) - empirical),
                -np.square(np.asarray(labels) - estimated),
            )
            if len(observed) >= 2
            else {"status": "INSUFFICIENT_PAIRS"},
            "closed_loop_evidence": "REQUIRES_PAIRED_RUNS",
        }
    else:
        h3 = {"status": "INSUFFICIENT_MATCH_LABELS", "supported": None}
    return {
        "evidence_level": "SYNTHETIC_OFFLINE",
        "test_queries": len(baseline),
        "metrics": {
            "baseline": summarize_ranking(baseline),
            **{name: summarize_ranking(values) for name, values in rankings.items()},
        },
        "H1": h1,
        "H2": h2,
        "H3": h3,
        "H9": h9_segment_test(baseline, rankings["tree_full"]),
        "human_evidence": "PENDING_REAL_SURVEY",
        "performance_claim": "NOT_A_PRODUCTION_BENCHMARK",
    }


def closed_loop_report(
    bundle: ModelBundle,
    config: SimulationConfig,
    seeds: Sequence[int],
    *,
    full_scenario_matrix: bool = True,
) -> dict[str, Any]:
    if len(set(seeds)) != len(seeds) or not seeds:
        raise ValueError("Independent unique seeds are required")
    scenarios = (
        list(itertools.product(("LOW", "MEDIUM", "HIGH"), ("LOW", "MEDIUM", "HIGH"), (0.1, 0.3)))
        if full_scenario_matrix
        else [(config.urban_density, config.intercity_density, config.rain_share)]
    )
    scenario_reports = []
    policies = ["baseline", "baseline_match_model", "ltr", "intercity_no_rescue", "batch"]
    if bundle.can_multiply_fulfillment:
        policies.append("ltr_fulfillment")
    for urban, intercity, rain in scenarios:
        runs = []
        for seed in seeds:
            scenario = replace(
                config,
                master_seed=seed,
                urban_density=urban,
                intercity_density=intercity,
                rain_share=rain,
            )
            exogenous = set()
            for policy in policies:
                scorer = _policy_scorer(bundle, policy)
                engine = DomainSimulationEngine(
                    scenario,
                    rescue_intercity=policy != "intercity_no_rescue",
                    batch_matching=policy == "batch",
                )
                result = Simulator(scenario, engine, scorer).run()
                exogenous.add(result.manifest["exogenous_stream_sha256"])
                metrics = dict(result.metrics)
                metrics["completion_per_request"] = (
                    metrics["completed_bookings"] / metrics["requests"]
                )
                metrics["unmatched_pool_selection_rate"] = (
                    metrics["pool_completed"] - metrics["pool_matched"]
                ) / max(1, metrics["pool_completed"])
                metrics["pool_match_rate"] = metrics["pool_matched"] / max(
                    1, metrics["pool_completed"]
                )
                metrics["low_demand_cancellation_rate"] = metrics[
                    "intercity_cancelled_low_demand_with_bookings"
                ] / max(1, metrics["intercity_published_with_bookings"])
                runs.append(
                    {
                        "seed": seed,
                        "policy": policy,
                        "metrics": metrics,
                        "exogenous_sha256": result.manifest["exogenous_stream_sha256"],
                    }
                )
            if len(exogenous) != 1:
                raise RuntimeError("Common Random Numbers stream changed across policies")

        from functools import partial

        compare = partial(_compare_runs, runs)

        scenario_reports.append(
            {
                "scenario": {
                    "urban_density": urban,
                    "intercity_density": intercity,
                    "rain_share": rain,
                },
                "runs": runs,
                "H3": {
                    "fund_difference": compare(
                        "baseline", "baseline_match_model", "fund_balance_vnd"
                    ),
                    "unmatched_rate_difference": compare(
                        "baseline", "baseline_match_model", "unmatched_pool_selection_rate"
                    ),
                },
                "ranking_utility_regret": compare("baseline", "ltr", "expected_utility_regret"),
                "H5": compare("ltr", "ltr_fulfillment", "completion_per_request")
                if "ltr_fulfillment" in policies
                else {"status": "DISABLED_SELECTION_CALIBRATION_GATE"},
                "H6": {
                    "fund_difference": compare("baseline", "batch", "fund_balance_vnd"),
                    "pool_match_rate_difference": compare("baseline", "batch", "pool_match_rate"),
                },
                "H10": {
                    "cancellation_rate_difference": compare(
                        "intercity_no_rescue", "baseline", "low_demand_cancellation_rate"
                    ),
                    "completion_difference": compare(
                        "intercity_no_rescue", "baseline", "completion_per_request"
                    ),
                },
            }
        )
    return {
        "evidence_level": "SYNTHETIC_CLOSED_LOOP",
        "seeds": list(seeds),
        "recommended_seed_count_met": len(seeds) >= 20,
        "minimum_seed_count_met": len(seeds) >= 10,
        "full_scenario_matrix": full_scenario_matrix,
        "scenarios": scenario_reports,
        "main_benchmark_ready": len(seeds) >= 20
        and full_scenario_matrix
        and config.request_count >= 50_000,
        "human_survey_calibrated": False,
        "routing": "fixture_not_osrm_measurement",
    }
