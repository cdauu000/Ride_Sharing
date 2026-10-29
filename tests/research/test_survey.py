from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from research.survey import (
    SCENARIOS,
    SurveyResponse,
    fairness_analysis,
    respondent_cross_validation,
    survey_quality,
)


def payload() -> dict[str, object]:
    return {
        "respondent_id": str(uuid4()),
        "segment": "STUDENT",
        "consent": True,
        "choices": [
            {"scenario_id": scenario["scenario_id"], "selected_service": "OUTSIDE"}
            for scenario in SCENARIOS
        ],
        "fairness": {"proportional": 3, "shapley": 3, "inconvenience": 5},
    }


def test_survey_is_anonymous_and_validates_offered_choices() -> None:
    response = SurveyResponse.model_validate(payload())
    assert survey_quality([response])["status"] == "NEEDS_HUMAN_DATA"
    invalid = payload()
    invalid["email"] = "identifying@example.com"
    with pytest.raises(ValidationError):
        SurveyResponse.model_validate(invalid)
    invalid = payload()
    invalid["choices"][0]["selected_service"] = "CAR_INTERCITY_POOL"
    with pytest.raises(ValidationError):
        SurveyResponse.model_validate(invalid)


def test_missing_or_duplicate_scenarios_are_rejected() -> None:
    invalid = payload()
    invalid["choices"][1] = invalid["choices"][0]
    with pytest.raises(ValidationError):
        SurveyResponse.model_validate(invalid)


def test_small_sample_cannot_claim_hypothesis_confirmed() -> None:
    responses = [SurveyResponse.model_validate(payload()) for _ in range(6)]
    assert fairness_analysis(responses)["supported"] is None


def test_human_cross_validation_compares_models_without_person_overlap() -> None:
    responses = []
    for index in range(10):
        item = payload()
        item["respondent_id"] = str(UUID(int=index + 1))
        item["segment"] = "STUDENT" if index < 5 else "WORKER"
        item["choices"] = [
            {
                "scenario_id": scenario["scenario_id"],
                "selected_service": scenario["alternatives"][index % len(scenario["alternatives"])][
                    "service_code"
                ],
            }
            for scenario in SCENARIOS
        ]
        responses.append(SurveyResponse.model_validate(item))
    result = respondent_cross_validation(responses)
    assert set(result["models"]) == {
        "baseline",
        "linear_raw",
        "tree_raw",
        "linear_full",
        "tree_full",
    }
    assert result["metrics"]["tree_full"]["queries"] == 80
    assert result["statistical_unit"] == "RESPONDENT"
    held = []
    for fold in result["folds"]:
        assert not set(fold["train_respondents"]) & set(fold["test_respondents"])
        held.extend(fold["test_respondents"])
    assert len(held) == len(set(held)) == 10
    assert result["H1"]["pairs"] == result["H9"]["pairs"] == 10
    assert result["H1"]["supported"] is None and result["H9"]["supported"] is None
