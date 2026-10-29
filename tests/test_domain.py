from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.config import Settings
from app.domain.batch_matcher import Bundle, solve_bundles
from app.domain.errors import DomainError
from app.domain.pooling import PoolPlan, Rider, Stop, evaluate, insert
from app.domain.trips import ServiceAreas, allowed_services
from app.domain.types import Point
from app.routing import DONG_DA, LA_PHU, NGUYEN_TRAI, PHENIKAA, FixtureRouting
from app.schemas import TripIntent


def test_area_buffer_boundary_and_unsupported_route() -> None:
    areas = ServiceAreas(Settings().service_areas_path)
    assert areas.classify(PHENIKAA, Point(20.89, 105.75), 5) == "URBAN"
    assert areas.classify(PHENIKAA, Point(20.646, 106.051), 65) == "INTERCITY"
    with pytest.raises(DomainError, match="UNSUPPORTED_INTER_PROVINCE_ROUTE"):
        areas.classify(Point(20.646, 106.051), Point(20.65, 106.055), 3)
    with pytest.raises(DomainError, match="OUT_OF_SERVICE_AREA"):
        areas.classify(PHENIKAA, Point(10.7, 106.7), 1500)


def test_exact_lead_time_and_preferences() -> None:
    now = datetime(2026, 10, 28, tzinfo=UTC)
    payload = {
        "pickup": {"lat": 20.961, "lon": 105.747},
        "dropoff": {"lat": 20.646, "lon": 106.051},
        "booking_type": "SCHEDULED",
        "preferred_departure": now + timedelta(hours=72),
        "earliest_departure": now + timedelta(hours=71),
        "latest_departure": now + timedelta(hours=73),
    }
    intent = TripIntent(**payload)
    assert "CAR_INTERCITY_POOL" in allowed_services(intent, "INTERCITY", now.timestamp())[0]
    assert "CAR_INTERCITY_POOL" not in allowed_services(intent, "INTERCITY", now.timestamp() + 1)[0]
    for passengers in (2, 4):
        intent = TripIntent(
            pickup=payload["pickup"], dropoff=payload["dropoff"], passenger_count=passengers
        )
        assert "BIKE_URBAN" not in allowed_services(intent, "URBAN", now.timestamp())[0]


def riders() -> tuple[Rider, Rider]:
    return (
        Rider("A", PHENIKAA, DONG_DA, 1, 0, 1200, 14, 40, 194000, 300000),
        Rider("B", LA_PHU, NGUYEN_TRAI, 1, 600, 2400, 9, 28, 133000, 200000),
    )


def test_forward_only_insertion_includes_already_traveled_distance() -> None:
    a, b = riders()
    plan = PoolPlan(
        PHENIKAA, 0, (a,), (Stop("A", "PICKUP", PHENIKAA), Stop("A", "DROPOFF", DONG_DA))
    )
    route = FixtureRouting()
    matrix = route.matrix("car", [PHENIKAA, LA_PHU, NGUYEN_TRAI, DONG_DA])
    result = insert(plan, b, matrix)
    assert result is not None
    assert result.fares["A"]["charged"] == 143000
    moving = replace(
        plan,
        now=60,
        completed_stop_index=0,
        riders=(replace(a, actual_pickup=0, traveled_km=5),),
        elapsed_km=5,
        elapsed_minutes=12,
    )
    result = insert(moving, b, matrix)
    # Additional5km remains in the detour calculation; treating it as zero would admit this.
    assert result is None


def test_capacity_and_social_constraints_rechecked_for_all_riders() -> None:
    a, b = riders()
    matrix = FixtureRouting().matrix("car", [PHENIKAA, LA_PHU, NGUYEN_TRAI, DONG_DA])
    stops = (
        Stop("A", "PICKUP", PHENIKAA),
        Stop("B", "PICKUP", LA_PHU),
        Stop("B", "DROPOFF", NGUYEN_TRAI),
        Stop("A", "DROPOFF", DONG_DA),
    )
    plan = PoolPlan(PHENIKAA, 0, (replace(a, seats=2), replace(b, seats=3)), stops)
    with pytest.raises(DomainError, match="SEGMENT_CAPACITY_EXCEEDED"):
        evaluate(plan, matrix)
    plan = replace(
        plan, riders=(replace(a, same_gender=True, gender="MALE"), replace(b, gender="FEMALE"))
    )
    with pytest.raises(DomainError, match="SOCIAL_CONSTRAINT"):
        evaluate(plan, matrix)
    plan = replace(plan, riders=(replace(a, max_minutes=10), b))
    with pytest.raises(DomainError, match="IN_VEHICLE_TIME_VIOLATION"):
        evaluate(plan, matrix)


def test_rtv_joint_bundle_solver_never_adds_independent_edges() -> None:
    bundles = [
        Bundle("a", "car1", ("r1",), 100),
        Bundle("b", "car1", ("r2",), 150),
        Bundle("c", "car2", ("r2",), 50),
        Bundle("d", "car2", ("r1", "r2"), 300),
    ]
    result = solve_bundles(bundles, {"r1", "r2"})
    assert len({r for b in result.selected for r in b.request_ids}) == sum(
        len(b.request_ids) for b in result.selected
    )
    assert len({b.vehicle_id for b in result.selected}) == len(result.selected)
    assert not result.unassigned
