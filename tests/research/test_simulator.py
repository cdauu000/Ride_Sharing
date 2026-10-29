from dataclasses import replace
from datetime import datetime

from app.domain.types import Service
from research.domain_engine import DomainSimulationEngine
from research.simulator import ScenarioRequest, SimulationConfig, Simulator, generate_requests


def request(
    identifier: str,
    at: float,
    *,
    pickup: tuple[float, float] = (20.9610, 105.7470),
    dropoff: tuple[float, float] = (21.0130, 105.8240),
    party: int = 1,
    earliest_offset: float = 300,
) -> ScenarioRequest:
    return ScenarioRequest(
        identifier,
        identifier,
        at,
        "URBAN",
        pickup,
        dropoff,
        at,
        at + earliest_offset,
        at + 2400,
        party,
        False,
        False,
        70_000,
        300_000,
        "corridor-0",
        False,
    )


def choose_pool(
    engine: DomainSimulationEngine, trip: ScenarioRequest, existing: bool = False
) -> dict:
    candidates = engine.quote(trip)
    return next(
        candidate
        for candidate in candidates
        if candidate["service_code"] == Service.CAR_URBAN_POOL
        and bool(candidate.get("_state")) == existing
    )


def finish(engine: DomainSimulationEngine, until: float) -> None:
    while (at := engine.next_event_at()) is not None and at <= until:
        engine.advance(at)
        for decision in engine.decisions():
            engine.respond(decision["booking_id"], False)
    engine.advance(until)


def test_same_seed_produces_identical_observations_and_exogenous_stream() -> None:
    config = SimulationConfig(master_seed=42, request_count=60, days=2)
    first = Simulator(config, DomainSimulationEngine(config)).run()
    second = Simulator(config, DomainSimulationEngine(config)).run()
    assert first.rows == second.rows
    assert first.manifest["dataset_sha256"] == second.manifest["dataset_sha256"]
    assert all("theta_price" not in row and "utility_true" not in row for row in first.rows)
    changed_policy = Simulator(config, DomainSimulationEngine(config, rescue_intercity=False)).run()
    assert (
        first.manifest["exogenous_stream_sha256"]
        == changed_policy.manifest["exogenous_stream_sha256"]
    )


def test_actual_insert_and_overlap_create_match_labels() -> None:
    config = SimulationConfig(master_seed=1000, request_count=2, strategic_driver_share=0)
    engine = DomainSimulationEngine(config)
    now = datetime.fromisoformat(config.start_utc).timestamp()
    first = request("first", now)
    first_id = engine.book(first, choose_pool(engine, first))
    second = request(
        "second",
        now + 60,
        pickup=(20.9830, 105.7310),
        dropoff=(20.9950, 105.8070),
        earliest_offset=600,
    )
    engine.advance(second.time)
    candidate = choose_pool(engine, second, existing=True)
    second_id = engine.book(second, candidate)
    finish(engine, now + 3 * 3600)
    assert engine.outcomes()[first_id]["pool_final_matched"] == 1
    assert engine.outcomes()[second_id]["pool_final_matched"] == 1
    assert engine.outcomes()[first_id]["final_price_vnd"] <= 155_000
    metrics = engine.metrics()
    assert (
        metrics["fund_balance_vnd"]
        == 5_000_000 + metrics["fund_contributions_vnd"] - metrics["guarantee_payouts_vnd"]
    )


def test_two_passengers_one_booking_is_not_a_successful_match() -> None:
    config = SimulationConfig(master_seed=1000, request_count=1, strategic_driver_share=0)
    engine = DomainSimulationEngine(config)
    now = datetime.fromisoformat(config.start_utc).timestamp()
    trip = request("alone", now, party=2)
    booking_id = engine.book(trip, choose_pool(engine, trip))
    finish(engine, now + 3 * 3600)
    assert engine.outcomes()[booking_id]["pool_final_matched"] == 0
    assert engine.outcomes()[booking_id]["final_price_vnd"] == 174_000
    assert engine.metrics()["guarantee_payouts_vnd"] == 7300


def test_exogenous_demand_contains_both_modes_and_deterministic_weather() -> None:
    config = SimulationConfig(request_count=100, days=2)
    requests = generate_requests(config)
    assert requests == generate_requests(config)
    assert {trip.mode for trip in requests} == {"URBAN", "INTERCITY"}
    assert requests != generate_requests(replace(config, master_seed=1001))


def test_batch_moves_only_pending_offer_and_uses_shared_solver() -> None:
    config = SimulationConfig(master_seed=1000, request_count=2, days=1, strategic_driver_share=0)
    engine = DomainSimulationEngine(config, batch_matching=True)
    now = datetime.fromisoformat(config.start_utc).timestamp()
    first = request("first", now)
    first_id = engine.book(first, choose_pool(engine, first))
    finish(engine, now + 25)
    second = request(
        "second",
        now + 25,
        pickup=(20.9830, 105.7310),
        dropoff=(20.9950, 105.8070),
        earliest_offset=600,
    )
    second_id = engine.book(second, choose_pool(engine, second))
    finish(engine, now + 31)
    assert engine.metrics()["batch_solver_runs"] == 1
    assert engine.metrics()["batch_assigned_requests"] == 1
    assert engine.plans["first:plan"].confirmed
    assert engine.plans["second:plan"].plan.status == "PLAN_ABORTED"
    finish(engine, now + 3 * 3600)
    assert engine.outcomes()[first_id]["pool_final_matched"] == 1
    assert engine.outcomes()[second_id]["pool_final_matched"] == 1
