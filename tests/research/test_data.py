from datetime import UTC, datetime, timedelta

import pytest

from research.data import FeatureFirewallError, export_observation, temporal_split


def observation(index: int) -> dict[str, object]:
    return {
        "request_id": f"r{index}",
        "candidate_id": f"c{index}",
        "timestamp_utc": (datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=index)).isoformat(),
        "user_id": "person",
        "service_code": "CAR_URBAN_POOL",
        "direct_distance_km": 14.0,
        "selected": 1,
    }


def test_exporter_rejects_hidden_and_future_features() -> None:
    for forbidden in ("theta_price", "utility_true", "rain_aversion_bike", "true_p_match"):
        row = observation(0) | {forbidden: 0.8}
        with pytest.raises(FeatureFirewallError):
            export_observation(row, "test-salt")
    with pytest.raises(FeatureFirewallError):
        export_observation(
            observation(0) | {"model_versions_json": {"hidden_utility": 0.8}}, "salt"
        )


def test_exporter_hides_identity_and_coordinates() -> None:
    row = export_observation(observation(0) | {"lat": 20.12345, "lon": 105.12345}, "salt")
    assert "user_id" not in row and "lat" not in row and "lon" not in row
    assert len(str(row["user_id_hash"])) == 64
    assert row["direct_distance_km"] == 14


def test_query_groups_remain_intact_and_time_ordered() -> None:
    rows = [export_observation(observation(i), "salt") for i in range(20)]
    rows += [rows[0] | {"candidate_id": "alternative"}]
    splits = temporal_split(rows)
    groups = [{str(r["request_id"]) for r in splits[split]} for split in ("TRAIN", "VAL", "TEST")]
    assert all(groups[i].isdisjoint(groups[j]) for i in range(3) for j in range(i + 1, 3))
    assert len(splits["TRAIN"]) == 14
    assert max(r["timestamp_utc"] for r in splits["TRAIN"]) < min(
        r["timestamp_utc"] for r in splits["VAL"]
    )


def test_same_timestamp_cannot_cross_temporal_boundaries() -> None:
    rows = [export_observation(observation(i), "salt") for i in range(10)]
    rows[6]["timestamp_utc"] = rows[5]["timestamp_utc"]
    splits = temporal_split(rows)
    for a, b in (("TRAIN", "VAL"), ("VAL", "TEST")):
        assert max(r["timestamp_utc"] for r in splits[a]) < min(
            r["timestamp_utc"] for r in splits[b]
        )
