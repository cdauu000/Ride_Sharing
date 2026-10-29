import pytest

from research.metrics import paired_bootstrap, ranking_by_query, summarize_ranking


def test_bootstrap_does_not_manufacture_significance() -> None:
    result = paired_bootstrap([1.0] * 20, [1.0] * 20)
    assert result["ci95"] == [0, 0]
    assert result["permutation_p_value_two_sided"] == 1
    assert not result["evidence_positive"]


def test_query_ranking_and_outside_option_denominators() -> None:
    rows = [
        {"request_id": "a", "candidate_id": "1", "selected": 1},
        {"request_id": "a", "candidate_id": "2", "selected": 0},
        {"request_id": "b", "candidate_id": "3", "selected": 0},
    ]
    results = ranking_by_query(rows, [0, 1, 2])
    assert results["a"]["hr1"] == 0
    assert results["a"]["mrr"] == 0.5
    assert results["b"]["hr1"] is None
    assert summarize_ranking(results)["outside_queries"] == 1


def test_unaligned_pairs_are_rejected() -> None:
    with pytest.raises(ValueError):
        paired_bootstrap([1, 2], [1])
