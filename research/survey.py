"""Anonymous stated-preference instrument and respondent-grouped evaluation."""

from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import UUID

import numpy as np
from lightgbm import LGBMRanker
from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator
from scipy.stats import friedmanchisquare, wilcoxon
from sklearn.model_selection import GroupKFold

from research.models import ConditionalLogit, feature_matrix, grouped

SURVEY_VERSION = "sp_survey_v1"
ServiceChoice = Literal[
    "BIKE_URBAN",
    "CAR_URBAN_PRIVATE",
    "CAR_URBAN_POOL",
    "CAR_INTERCITY_PRIVATE",
    "CAR_INTERCITY_POOL",
    "OUTSIDE",
]
Rating = Annotated[StrictInt, Field(ge=1, le=5)]


def _urban(index: int, km: int, raining: bool, urgent: bool) -> dict[str, Any]:
    long = km == 14
    return {
        "scenario_id": f"urban_{index}",
        "mode": "URBAN",
        "distance_km": km,
        "is_raining": raining,
        "urgent": urgent,
        "lead_time_hours": 0,
        "passenger_count": 1,
        "has_luggage": False,
        "description": f"Đi {km} km, {'trời mưa' if raining else 'khô ráo'}, {'cần đến đúng giờ' if urgent else 'không vội'}.",
        "alternatives": [
            {
                "service_code": "BIKE_URBAN",
                "price_vnd": 81_000 if long else 42_000,
                "pickup_min": 5,
                "duration_min": 35 if long else 22,
            },
            {
                "service_code": "CAR_URBAN_POOL",
                "price_vnd": 143_000 if long else 72_000,
                "quote_vnd": 155_000 if long else 77_000,
                "cap_vnd": 174_000 if long else 87_000,
                "pickup_min": 8,
                "duration_min": 52 if long else 28,
                "match_likelihood": "Cao",
                "detour_ratio": 0.25,
                "walk_m": 0,
            },
            {
                "service_code": "CAR_URBAN_PRIVATE",
                "price_vnd": 194_000 if long else 97_000,
                "pickup_min": 7,
                "duration_min": 40 if long else 22,
            },
        ],
    }


SCENARIOS = [
    _urban(1, 6, False, False),
    _urban(2, 6, True, False),
    _urban(3, 6, True, True),
    _urban(4, 14, False, True),
    _urban(5, 14, True, False),
    _urban(6, 14, True, True),
    {
        "scenario_id": "intercity_1",
        "mode": "INTERCITY",
        "distance_km": 65,
        "is_raining": False,
        "urgent": False,
        "lead_time_hours": 120,
        "passenger_count": 1,
        "has_luggage": False,
        "description": "Hà Đông → Hưng Yên, 65 km, đặt trước 5 ngày; chuyến ghép có thể hủy do thiếu ghế trước 3 ngày và được hoàn tiền.",
        "alternatives": [
            {
                "service_code": "CAR_INTERCITY_POOL",
                "price_vnd": 200_000,
                "pickup_min": 0,
                "duration_min": 100,
                "match_likelihood": "Cao",
            },
            {
                "service_code": "CAR_INTERCITY_PRIVATE",
                "price_vnd": 637_000,
                "pickup_min": 0,
                "duration_min": 90,
            },
        ],
    },
    {
        "scenario_id": "intercity_2",
        "mode": "INTERCITY",
        "distance_km": 65,
        "is_raining": True,
        "urgent": True,
        "lead_time_hours": 72,
        "passenger_count": 1,
        "has_luggage": False,
        "description": "Hà Đông → Hưng Yên, 65 km, đặt trước 3 ngày, trời mưa; chuyến ghép có thể hủy do thiếu ghế và được hoàn tiền.",
        "alternatives": [
            {
                "service_code": "CAR_INTERCITY_POOL",
                "price_vnd": 220_000,
                "pickup_min": 0,
                "duration_min": 110,
                "match_likelihood": "Thấp",
            },
            {
                "service_code": "CAR_INTERCITY_PRIVATE",
                "price_vnd": 637_000,
                "pickup_min": 0,
                "duration_min": 90,
            },
        ],
    },
]
SCENARIO_BY_ID = {item["scenario_id"]: item for item in SCENARIOS}
FAIRNESS_TABLES = {
    "proportional": {"passenger_a_vnd": 147_428, "passenger_b_vnd": 101_072},
    "shapley": {"passenger_a_vnd": 154_750, "passenger_b_vnd": 93_750},
    "inconvenience": {"passenger_a_vnd": 143_304, "passenger_b_vnd": 105_196},
}


class SurveyChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario_id: str = Field(min_length=1, max_length=32)
    selected_service: ServiceChoice


class FairnessRatings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    proportional: Rating
    shapley: Rating
    inconvenience: Rating


class SurveyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    respondent_id: UUID
    segment: Literal["STUDENT", "WORKER"]
    choices: list[SurveyChoice] = Field(min_length=8, max_length=8)
    fairness: FairnessRatings
    consent: Literal[True]
    survey_version: Literal["sp_survey_v1"] = SURVEY_VERSION

    @model_validator(mode="after")
    def validate_instrument(self) -> SurveyResponse:
        identifiers = [choice.scenario_id for choice in self.choices]
        if set(identifiers) != set(SCENARIO_BY_ID) or len(set(identifiers)) != 8:
            raise ValueError("Answer each of the eight published scenarios exactly once")
        for choice in self.choices:
            allowed = {
                a["service_code"] for a in SCENARIO_BY_ID[choice.scenario_id]["alternatives"]
            } | {"OUTSIDE"}
            if choice.selected_service not in allowed:
                raise ValueError("Selected service was not offered in this scenario")
        return self


def fairness_order(respondent_id: UUID) -> list[str]:
    """Counterbalance anonymous A/B/C presentation without collecting identities."""
    import itertools

    orders = list(itertools.permutations(FAIRNESS_TABLES))
    return list(orders[respondent_id.int % len(orders)])


def survey_quality(responses: list[SurveyResponse]) -> dict[str, Any]:
    identities = [str(response.respondent_id) for response in responses]
    if len(identities) != len(set(identities)):
        raise ValueError("Respondent IDs must be unique")
    total = len(responses)
    students = sum(response.segment == "STUDENT" for response in responses)
    share = students / total if total else 0.0
    return {
        "valid_respondents": total,
        "student_count": students,
        "worker_count": total - students,
        "student_share": share,
        "quota_met": total >= 100 and 0.4 <= share <= 0.6,
        "real_survey_ready": total >= 100 and 0.4 <= share <= 0.6,
        "status": "READY_FOR_ANALYSIS"
        if total >= 100 and 0.4 <= share <= 0.6
        else "NEEDS_HUMAN_DATA",
    }


def survey_rows(responses: list[SurveyResponse]) -> list[dict[str, Any]]:
    """Return offered alternatives with observed choices; never infer actual ride outcomes."""
    rows = []
    for response in responses:
        for answer in response.choices:
            scenario = SCENARIO_BY_ID[answer.scenario_id]
            for alternative in scenario["alternatives"]:
                code = alternative["service_code"]
                pool = "POOL" in code
                rows.append(
                    {
                        "request_id": f"{response.respondent_id}:{answer.scenario_id}",
                        "respondent_id": str(response.respondent_id),
                        "candidate_id": f"{response.respondent_id}:{answer.scenario_id}:{code}",
                        "timestamp_utc": "2026-01-01T00:00:00+00:00",  # instrument context; no fabricated observation date
                        "service_code": code,
                        "mode": scenario["mode"],
                        "segment": "URBAN_MULTI" if scenario["mode"] == "URBAN" else "INTERCITY",
                        "booking_type": "SCHEDULED" if scenario["lead_time_hours"] else "NOW",
                        "is_raining": int(scenario["is_raining"]),
                        "has_luggage": 0,
                        "direct_distance_km": scenario["distance_km"],
                        "direct_duration_min": 40
                        if scenario["distance_km"] == 14
                        else 22
                        if scenario["mode"] == "URBAN"
                        else 90,
                        "passenger_count": 1,
                        "pickup_window_width_min": 10 if scenario["urgent"] else 30,
                        "budget_min": 80_000 if scenario["mode"] == "URBAN" else 200_000,
                        "budget_max": 220_000 if scenario["mode"] == "URBAN" else 700_000,
                        "lead_time_hours": scenario["lead_time_hours"],
                        "effective_price_vnd": alternative["price_vnd"],
                        "fare_matched_est_vnd": alternative["price_vnd"] if pool else 0,
                        "pool_quote_price_vnd": alternative.get("quote_vnd", 0),
                        "pool_unmatched_price_vnd": alternative.get("cap_vnd", 0),
                        "planned_pickup_eta_min": alternative["pickup_min"],
                        "in_vehicle_duration_min": alternative["duration_min"],
                        "detour_ratio": alternative.get("detour_ratio", 0),
                        "walk_m": alternative.get("walk_m", 0),
                        "driver_rating_bayesian": 4.7,
                        "selected": int(answer.selected_service == code),
                    }
                )
    return rows


def fairness_analysis(responses: list[SurveyResponse]) -> dict[str, Any]:
    quality = survey_quality(responses)
    if len(responses) < 5:
        return {
            "quality": quality,
            "status": "INSUFFICIENT_DATA",
            "hypothesis": "H4",
            "supported": None,
        }
    methods = list(FAIRNESS_TABLES)
    arrays = [
        np.asarray([getattr(response.fairness, method) for response in responses])
        for method in methods
    ]
    comparisons = []
    for i, left in enumerate(methods):
        for j in range(i + 1, len(methods)):
            differences = arrays[i] - arrays[j]
            p_value = (
                1.0
                if not np.any(differences)
                else float(wilcoxon(arrays[i], arrays[j], alternative="two-sided").pvalue)
            )
            comparisons.append(
                {
                    "left": left,
                    "right": methods[j],
                    "mean_difference": float(differences.mean()),
                    "p_value": p_value,
                    "bonferroni_p_value": min(1.0, p_value * 3),
                }
            )
    friedman_p = (
        1.0
        if all(np.array_equal(arrays[0], arr) for arr in arrays[1:])
        else float(friedmanchisquare(*arrays).pvalue)
    )
    preference = float(arrays[2].mean()) > max(float(arrays[0].mean()), float(arrays[1].mean()))
    proposed_comparisons = [
        comparison for comparison in comparisons if comparison["right"] == "inconvenience"
    ]
    return {
        "hypothesis": "H4",
        "quality": quality,
        "status": "ANALYZED" if quality["real_survey_ready"] else "EXPLORATORY_INSUFFICIENT_QUOTA",
        "mean_ratings": {
            method: float(arr.mean()) for method, arr in zip(methods, arrays, strict=True)
        },
        "median_ratings": {
            method: float(np.median(arr)) for method, arr in zip(methods, arrays, strict=True)
        },
        "friedman_p_value": friedman_p,
        "comparisons": comparisons,
        "supported": bool(
            preference and all(c["bonferroni_p_value"] < 0.05 for c in proposed_comparisons)
        )
        if quality["real_survey_ready"]
        else None,
    }


def respondent_cross_validation(responses: list[SurveyResponse]) -> dict[str, Any]:
    """Five-fold grouping uses every human query once without respondent overlap."""
    from research.evaluation import baseline_scores
    from research.metrics import paired_bootstrap, ranking_by_query, summarize_ranking

    quality = survey_quality(responses)
    rows = survey_rows(responses)
    if len(responses) < 5:
        raise ValueError("At least five independent respondents are required")
    identities = np.asarray([str(row["respondent_id"]) for row in rows])
    folds = []
    results: dict[str, dict] = {
        name: {} for name in ("baseline", "linear_raw", "tree_raw", "linear_full", "tree_full")
    }
    for fold, (fit_indexes, held_indexes) in enumerate(
        GroupKFold(n_splits=5).split(rows, groups=identities)
    ):
        training, sizes = grouped([rows[index] for index in fit_indexes])
        held, held_sizes = grouped([rows[index] for index in held_indexes])
        labels = np.asarray([int(row["selected"]) for row in training])
        rankings = {"baseline": ranking_by_query(held, baseline_scores(held))}
        for interactions, suffix in ((False, "raw"), (True, "full")):
            x = feature_matrix(training, interactions)
            test_x = feature_matrix(held, interactions)
            linear = ConditionalLogit().fit(x, labels, sizes)
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
            tree.fit(x, labels, group=sizes)
            rankings[f"linear_{suffix}"] = ranking_by_query(held, linear.predict(test_x))
            rankings[f"tree_{suffix}"] = ranking_by_query(held, tree.predict(test_x))
        for name, metrics in rankings.items():
            if results[name].keys() & metrics.keys():
                raise ValueError("A human query appeared in more than one held-out fold")
            results[name].update(metrics)
        folds.append(
            {
                "fold": fold,
                "train_respondents": sorted(set(identities[fit_indexes])),
                "test_respondents": sorted(set(identities[held_indexes])),
                "test_queries": len(held_sizes),
                "metrics": {name: summarize_ranking(value) for name, value in rankings.items()},
            }
        )
    # Inference resamples independent people, not their eight correlated answers.
    respondent_queries: dict[str, dict[str, str]] = {}
    for row in rows:
        respondent_queries.setdefault(str(row["respondent_id"]), {})[str(row["request_id"])] = str(
            row["segment"]
        )

    def compare_people(left: str, right: str, urban_difference: bool = False) -> dict[str, Any]:
        a, b = [], []
        for queries in respondent_queries.values():
            valid = [
                q
                for q in queries
                if results[left][q]["hr1"] is not None and results[right][q]["hr1"] is not None
            ]
            if urban_difference:
                urban = [q for q in valid if queries[q] == "URBAN_MULTI"]
                other = [q for q in valid if queries[q] != "URBAN_MULTI"]
                if not urban or not other:
                    continue
                a.append(0.0)
                b.append(
                    float(
                        np.mean([results[right][q]["hr1"] - results[left][q]["hr1"] for q in urban])
                        - np.mean(
                            [results[right][q]["hr1"] - results[left][q]["hr1"] for q in other]
                        )
                    )
                )
            elif valid:
                a.append(float(np.mean([results[left][q]["hr1"] for q in valid])))
                b.append(float(np.mean([results[right][q]["hr1"] for q in valid])))
        if len(a) < 2:
            return {"status": "INSUFFICIENT_RESPONDENTS_WITH_OBSERVED_CHOICES", "supported": None}
        report = paired_bootstrap(a, b)
        report.update(
            unit="RESPONDENT",
            supported=report["evidence_positive"] if quality["real_survey_ready"] else None,
        )
        return report

    return {
        "status": "EXPLORATORY" if not quality["real_survey_ready"] else "ANALYZED",
        "folds": folds,
        "models": list(results),
        "metrics": {name: summarize_ranking(value) for name, value in results.items()},
        "H1": compare_people("baseline", "tree_full"),
        "H2": {
            suffix: compare_people(f"linear_{suffix}", f"tree_{suffix}")
            for suffix in ("raw", "full")
        },
        "H9": compare_people("baseline", "tree_full", urban_difference=True),
        "statistical_unit": "RESPONDENT",
        "full_data_used_once_for_test": True,
    }
