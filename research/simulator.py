"""Deterministic demand, weather, heterogeneous choice, and engine-driven outcomes.

Hidden preference state is private to the choice mechanism. The feature exporter
receives transaction observations through a separate explicit allowlist.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

import numpy as np

from research.data import canonical_bytes, export_observation


@dataclass(frozen=True)
class SimulationConfig:
    master_seed: int = 1000
    request_count: int = 1000
    days: int = 28
    urban_density: str = "MEDIUM"
    intercity_density: str = "MEDIUM"
    rain_share: float = 0.1
    now_booking_share: float = 0.7
    recurring_user_share: float = 0.2
    strategic_driver_share: float = 0.1
    scenario_version: str = "sim_v9_multi_service"
    pricing_version: str = "price_v9_two_sided_bounded"
    start_utc: str = "2026-01-01T00:00:00+00:00"

    def __post_init__(self) -> None:
        if self.request_count < 1 or self.days < 1:
            raise ValueError("Positive simulation size required")
        if self.urban_density not in ("LOW", "MEDIUM", "HIGH") or self.intercity_density not in (
            "LOW",
            "MEDIUM",
            "HIGH",
        ):
            raise ValueError("Unknown density scenario")
        for value in (
            self.rain_share,
            self.now_booking_share,
            self.recurring_user_share,
            self.strategic_driver_share,
        ):
            if not 0 <= value <= 1:
                raise ValueError("Scenario shares must be probabilities")
        if datetime.fromisoformat(self.start_utc).tzinfo is None:
            raise ValueError("Simulation start must be timezone-aware")


@dataclass(frozen=True)
class ScenarioRequest:
    id: str
    user_id: str
    time: float
    mode: str
    pickup: tuple[float, float]
    dropoff: tuple[float, float]
    preferred: float
    earliest: float
    latest: float
    passengers: int
    has_luggage: bool
    raining: bool
    budget_min: int
    budget_max: int
    corridor: str
    urgent: bool
    gender: str = "UNKNOWN"
    same_gender: bool = False


class SimulationEngine(Protocol):
    routing_mode: str

    def quote(self, request: ScenarioRequest) -> list[dict[str, Any]]: ...
    def book(self, request: ScenarioRequest, candidate: Mapping[str, Any]) -> str: ...
    def advance(self, now: float) -> None: ...
    def next_event_at(self) -> float | None: ...
    def decisions(self) -> list[dict[str, Any]]: ...
    def respond(self, booking_id: str, accept: bool) -> None: ...
    def outcomes(self) -> Mapping[str, Mapping[str, Any]]: ...
    def metrics(self) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class _PassengerTaste:
    price: float
    price_power: float
    time: float
    wait_threshold: float
    detour: float
    comfort: float
    rain_bike: float
    pooling: float
    noise: float
    topup_limit: float


def _stable_seed(master: int, *keys: object) -> int:
    return int.from_bytes(
        hashlib.sha256(":".join(map(str, (master, *keys))).encode()).digest()[:8], "big"
    )


def _taste(seed: int, user_id: str) -> _PassengerTaste:
    rng = np.random.default_rng(_stable_seed(seed, "taste", user_id))
    student = bool(rng.random() < 0.5)
    return _PassengerTaste(
        price=float(rng.lognormal(1.15 if student else 0.6, 0.35)),
        price_power=float(rng.uniform(1.2, 2.2)),
        time=float(rng.lognormal(0, 0.4)),
        wait_threshold=float(rng.uniform(8, 18)),
        detour=float(rng.uniform(2, 6)),
        comfort=float(rng.lognormal(0.3, 0.4)),
        rain_bike=float(rng.lognormal(0.8, 0.3)),
        pooling=float(rng.uniform(0.0, 0.9)),
        noise=float(rng.uniform(0.25, 0.6)),
        topup_limit=float(rng.uniform(0.4, 0.9)),
    )


def generate_requests(config: SimulationConfig) -> list[ScenarioRequest]:
    """NHPP conditional on N; hourly Markov weather and independent exogenous streams."""
    start = datetime.fromisoformat(config.start_utc).timestamp()
    sequence = np.random.SeedSequence(config.master_seed)
    demand_seed, weather_seed, route_seed = sequence.spawn(3)
    demand, weather, routes = (
        np.random.default_rng(seed) for seed in (demand_seed, weather_seed, route_seed)
    )
    hours = config.days * 24
    rain = np.empty(hours, dtype=bool)
    raining = bool(weather.random() < config.rain_share)
    for hour in range(hours):
        if raining:
            raining = not bool(weather.random() < 0.35 * (1 - config.rain_share))
        else:
            raining = bool(weather.random() < 0.35 * config.rain_share)
        rain[hour] = raining
    weights = np.asarray(
        [
            3.0
            if 6 <= (hour + 7) % 24 <= 9 or 16 <= (hour + 7) % 24 <= 19
            else 0.25
            if (hour + 7) % 24 <= 5
            else 1.0
            for hour in range(hours)
        ]
    )
    requested_hours = demand.choice(hours, config.request_count, p=weights / weights.sum())
    times = np.sort(start + requested_hours * 3600 + demand.uniform(0, 3600, config.request_count))
    urban_corridors = [
        ((20.9610, 105.7470), (21.0130, 105.8240)),
        ((20.9830, 105.7310), (20.9950, 105.8070)),
        ((21.0340, 105.7530), (21.0210, 105.8190)),
    ]
    province_destinations = [
        (20.6460, 106.0510),
        (21.1860, 106.0760),
        (20.5410, 105.9140),
        (21.3090, 105.6040),
        (20.9380, 106.3160),
    ]
    requests = []
    for index, now in enumerate(times):
        urban = bool(routes.random() < 0.75)
        mode = "URBAN" if urban else "INTERCITY"
        party = int(routes.choice([1, 2, 3], p=[0.78, 0.18, 0.04]))
        luggage = bool(routes.random() < (0.1 if urban else 0.2))
        urgent = bool(routes.random() < 0.4)
        density = config.urban_density if urban else config.intercity_density
        # Density changes corridor concentration, never the outcome label directly.
        focus = {"LOW": 0.35, "MEDIUM": 0.65, "HIGH": 0.9}[density]
        corridor_index = (
            0 if routes.random() < focus else int(routes.integers(0, 3 if urban else 5))
        )
        pickup, dropoff = (
            urban_corridors[corridor_index]
            if urban
            else (urban_corridors[0][0], province_destinations[corridor_index])
        )
        if urban:
            # Actual coordinates affect root routing and insertion; no match coin flip exists.
            jitter = 0.0015 if density == "HIGH" else 0.004 if density == "MEDIUM" else 0.012
            pickup = (
                pickup[0] + float(routes.normal(0, jitter)),
                pickup[1] + float(routes.normal(0, jitter)),
            )
            dropoff = (
                dropoff[0] + float(routes.normal(0, jitter)),
                dropoff[1] + float(routes.normal(0, jitter)),
            )
            lead = (
                0.0
                if routes.random() < config.now_booking_share
                else float(routes.uniform(0.5, 12)) * 3600
            )
        else:
            lead = (
                float(routes.uniform(72, 166)) * 3600
                if routes.random() < 0.7
                else float(routes.uniform(0, 70)) * 3600
            )
        preferred = float(now + lead)
        if lead:
            width = 15 * 60 if urgent else 45 * 60
            earliest, latest = preferred, preferred + width
        else:
            earliest, latest = float(now + 5 * 60), float(now + (15 if urgent else 20) * 60)
        user = (
            f"recurring-{index % 80}"
            if routes.random() < config.recurring_user_share
            else f"user-{index}"
        )
        budget_max = (
            int(routes.choice([150_000, 220_000, 300_000]))
            if urban
            else int(routes.choice([300_000, 700_000, 1_200_000]))
        )
        requests.append(
            ScenarioRequest(
                id=f"r-{config.master_seed}-{index:07d}",
                user_id=user,
                time=float(now),
                mode=mode,
                pickup=pickup,
                dropoff=dropoff,
                preferred=preferred,
                earliest=earliest,
                latest=latest,
                passengers=party,
                has_luggage=luggage,
                raining=bool(rain[min(hours - 1, int((now - start) // 3600))]),
                budget_min=70_000 if urban else 200_000,
                budget_max=budget_max,
                corridor=f"corridor-{corridor_index}",
                urgent=urgent,
            )
        )
    return requests


def baseline_scores(rows: list[dict[str, Any]]) -> np.ndarray:
    from app.domain.recommendation import baseline_score

    return np.asarray(
        [
            baseline_score(
                {
                    "service_code": row["service_code"],
                    "price": row["effective_price_vnd"],
                    "expected_price": row["effective_price_vnd"],
                    "pickup_eta_min": row["planned_pickup_eta_min"],
                    "duration_min": row["in_vehicle_duration_min"],
                    "detour_ratio": row["detour_ratio"],
                },
                row,
            )
            for row in rows
        ]
    )


@dataclass
class SimulationResult:
    rows: list[dict[str, Any]]
    manifest: dict[str, Any]
    metrics: dict[str, Any]


class Simulator:
    def __init__(
        self,
        config: SimulationConfig,
        engine: SimulationEngine,
        scorer: Callable[[list[dict[str, Any]]], np.ndarray] = baseline_scores,
    ) -> None:
        self.config, self.engine, self.scorer = config, engine, scorer
        self._tastes: dict[str, _PassengerTaste] = {}
        self._requests: dict[str, ScenarioRequest] = {}

    def _utility(self, request: ScenarioRequest, row: Mapping[str, Any]) -> float:
        taste = self._tastes.setdefault(
            request.user_id, _taste(self.config.master_seed, request.user_id)
        )
        bike = row["service_code"] == "BIKE_URBAN"
        pool = "POOL" in row["service_code"]
        distance = float(row["direct_distance_km"])
        wait = float(row["planned_pickup_eta_min"])
        comfort = (0 if request.raining else 0.3) if bike else 0.7 if pool else 1.0
        price = float(row["effective_price_vnd"]) / request.budget_max
        return float(
            4.0
            - taste.price * price**taste.price_power
            - taste.time
            * (float(row["in_vehicle_duration_min"]) + wait)
            / (35 if request.urgent else 60)
            - 0.02 * max(0, wait - taste.wait_threshold) ** 2
            - taste.detour * float(row["detour_ratio"])
            + taste.comfort * comfort
            - taste.rain_bike * bike * request.raining * (distance / 10) ** 1.2
            - taste.pooling * pool
        )

    def _advance(self, until: float) -> None:
        while (at := self.engine.next_event_at()) is not None and at <= until:
            self.engine.advance(at)
            for decision in self.engine.decisions():
                request = self._requests[str(decision["request_id"])]
                taste = self._tastes.setdefault(
                    request.user_id, _taste(self.config.master_seed, request.user_id)
                )
                total = int(decision["final_price_vnd"])
                self.engine.respond(
                    str(decision["booking_id"]), total <= request.budget_max * taste.topup_limit
                )
        self.engine.advance(until)

    def run(self) -> SimulationResult:
        observations: list[dict[str, Any]] = []
        selected_observations: dict[str, dict[str, Any]] = {}
        requests = generate_requests(self.config)
        self._requests = {request.id: request for request in requests}
        history: dict[str, list[tuple[float, str]]] = {}
        salt = hashlib.sha256(f"synthetic:{self.config.master_seed}".encode()).hexdigest()
        outside_count, covered = 0, 0
        regret_total = 0.0
        regret_segments: dict[str, list[float]] = {}
        for request in requests:
            self._advance(request.time)
            completed_ids = (
                self.engine.observed_completions()
                if hasattr(self.engine, "observed_completions")
                else list(self.engine.outcomes())
            )
            for booking_id in completed_ids:
                outcome = self.engine.outcomes()[booking_id]
                observed = selected_observations.get(booking_id)
                if (
                    observed is not None
                    and outcome.get("completed")
                    and not observed.get("history_recorded")
                ):
                    owner = self._requests[str(observed["request_id"])].user_id
                    history.setdefault(owner, []).append(
                        (float(outcome["outcome_time"]), str(observed["service_code"]))
                    )
                    observed["history_recorded"] = True
            candidates = self.engine.quote(request)
            if not candidates:
                continue
            covered += 1
            past = [
                (at, code) for at, code in history.get(request.user_id, []) if at < request.time
            ]
            for row in candidates:
                row.update(
                    {
                        "request_id": request.id,
                        "timestamp_utc": datetime.fromtimestamp(request.time, UTC).isoformat(),
                        "user_id": request.user_id,
                        "mode": request.mode,
                        "booking_type": "NOW" if request.preferred == request.time else "SCHEDULED",
                        "is_raining": int(request.raining),
                        "has_luggage": int(request.has_luggage),
                        "passenger_count": request.passengers,
                        "hour_of_day": datetime.fromtimestamp(request.time + 7 * 3600, UTC).hour,
                        "day_of_week": datetime.fromtimestamp(
                            request.time + 7 * 3600, UTC
                        ).weekday(),
                        "pickup_window_width_min": (request.latest - request.earliest) / 60,
                        "budget_min": request.budget_min,
                        "budget_max": request.budget_max,
                        "lead_time_hours": (request.preferred - request.time) / 3600,
                        "origin_zone_id": request.corridor + "-origin",
                        "dest_zone_id": request.corridor + "-destination",
                        "segment": "URBAN_MULTI"
                        if request.mode == "URBAN"
                        and request.passengers == 1
                        and not request.has_luggage
                        else "URBAN_GROUP"
                        if request.mode == "URBAN"
                        else "INTERCITY",
                        "user_hist_trip_count": len(past),
                        "user_hist_bike_share": (sum(code == "BIKE_URBAN" for _, code in past) + 1)
                        / (len(past) + 3),
                        "user_hist_pool_share": (sum("POOL" in code for _, code in past) + 1)
                        / (len(past) + 3),
                        "user_hist_private_share": (sum("PRIVATE" in code for _, code in past) + 1)
                        / (len(past) + 3),
                        "dataset_version": f"sim-{self.config.master_seed}",
                        "pricing_version": self.config.pricing_version,
                        "scenario_version": self.config.scenario_version,
                        "selected": 0,
                    }
                )
            scores = self.scorer(candidates)
            ranking = sorted(
                range(len(candidates)),
                key=lambda i: (-float(scores[i]), str(candidates[i]["candidate_id"])),
            )
            # Diversity is enforced after either baseline or model scoring.
            seeds = {}
            for index in ranking:
                seeds.setdefault(candidates[index]["service_code"], index)
            chosen_indexes = list(seeds.values())
            chosen_indexes += [index for index in ranking if index not in chosen_indexes][
                : max(0, 6 - len(chosen_indexes))
            ]
            chosen_indexes.sort(
                key=lambda i: (-float(scores[i]), str(candidates[i]["candidate_id"]))
            )
            shown = [candidates[index] for index in chosen_indexes]
            # Aggregate evaluator-only reference. Latent utility never enters exported rows.
            optimum = max(0.0, *[self._utility(request, item) for item in candidates])
            regret = max(0.0, optimum - self._utility(request, shown[0]))
            regret_total += regret
            segment = str(shown[0]["segment"])
            aggregate = regret_segments.setdefault(segment, [0.0, 0.0])
            aggregate[0] += regret
            aggregate[1] += 1
            taste = self._tastes.setdefault(
                request.user_id, _taste(self.config.master_seed, request.user_id)
            )
            utilities = []
            for position, row in enumerate(shown, 1):
                row.update(
                    shown_position=position,
                    shown_reason="DIVERSITY_SEED"
                    if seeds[row["service_code"]] == chosen_indexes[position - 1]
                    else "RANKED_BY_SCORE",
                    exposure_propensity=1.0,
                )
                noise = np.random.default_rng(
                    _stable_seed(self.config.master_seed, "choice", request.id, row["candidate_id"])
                ).gumbel(scale=taste.noise)
                utilities.append(
                    self._utility(request, row) + float(noise) - 0.1 * np.log(position)
                )
            outside_utility = float(
                np.random.default_rng(
                    _stable_seed(self.config.master_seed, "outside", request.id)
                ).gumbel(scale=taste.noise)
            )
            if max(utilities) > outside_utility:
                selected = shown[int(np.argmax(utilities))]
                selected["selected"] = 1
                booking_id = self.engine.book(request, selected)
                selected["booking_id"] = booking_id
                selected_observations[booking_id] = selected
            else:
                outside_count += 1
            observations.extend(shown)
        if requests:
            self._advance(max(request.preferred for request in requests) + 10 * 86400)
        for booking_id, row in selected_observations.items():
            outcome = self.engine.outcomes().get(booking_id, {})
            row.update(
                {
                    key: outcome[key]
                    for key in (
                        "driver_accepted",
                        "trip_confirmed_at_T72",
                        "ride_started",
                        "completed",
                        "pool_final_matched",
                        "unmatched_cause",
                        "final_price_vnd",
                        "outcome_at",
                    )
                    if key in outcome
                }
            )
        safe_rows = [export_observation(row, salt) for row in observations]
        digest = hashlib.sha256(canonical_bytes(safe_rows)).hexdigest()
        manifest = {
            "blueprint_revision": "Revision_9",
            "config": asdict(self.config),
            "dataset_sha256": digest,
            "routing_mode": self.engine.routing_mode,
            "synthetic_data": True,
            "match_labels_source": "shared_domain_insertion_and_actual_coriding",
            "hidden_variables_exported": False,
            "human_survey_calibrated": False,
            "exogenous_stream_sha256": hashlib.sha256(
                canonical_bytes([asdict(request) for request in requests])
            ).hexdigest(),
        }
        metrics = dict(
            self.engine.metrics(),
            requests=len(requests),
            covered_requests=covered,
            coverage_rate=covered / len(requests),
            outside_choices=outside_count,
            expected_utility_regret=regret_total / max(1, covered),
            regret_by_segment={
                key: total / max(1, count) for key, (total, count) in regret_segments.items()
            },
        )
        return SimulationResult(safe_rows, manifest, metrics)
