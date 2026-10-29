"""Discrete-event adapter over the application's real pooling and pricing functions.

FixtureRouting is an explicit local test provider; replacing it with OsrmRouting
uses the same matrix and insertion code. Outcomes are never sampled for matching.
"""

from __future__ import annotations

import heapq
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from fractions import Fraction
from typing import Any

import numpy as np

from app.domain.pooling import EvaluatedPlan, PoolPlan, Rider, Stop, insert
from app.domain.pricing import fixed_fare, floor_money, pool_quote, seat_reference, settlement
from app.domain.types import Point, Service
from app.routing import FixtureRouting, RoutingProvider
from research.simulator import ScenarioRequest, SimulationConfig, _stable_seed


@dataclass
class _UrbanState:
    id: str
    plan: PoolPlan
    fares: dict[str, dict[str, Any]] = field(default_factory=dict)
    pickups: dict[str, float] = field(default_factory=dict)
    dropoffs: dict[str, float] = field(default_factory=dict)
    requests: dict[str, ScenarioRequest] = field(default_factory=dict)
    observed_overlap: set[str] = field(default_factory=set)
    locked: dict[str, tuple[str, int, str]] = field(default_factory=dict)
    anchor_plan: PoolPlan | None = None
    timeline: list[tuple[float, int, float]] = field(default_factory=list)
    strategic: bool = False
    vehicle: str = ""
    confirmed: bool = False


class DomainSimulationEngine:
    """Finite vehicle supply, moving plans, actual insertion, and scheduled seat lifecycle."""

    def __init__(
        self,
        config: SimulationConfig,
        routing: RoutingProvider | None = None,
        *,
        rescue_intercity: bool = True,
        batch_matching: bool = False,
        car_count: int = 40,
        bike_count: int = 60,
    ) -> None:
        self.config, self.routing = config, routing or FixtureRouting()
        self.routing_mode = self.routing.mode
        self.rescue_intercity = rescue_intercity
        self.batch_matching = batch_matching
        self.now = datetime.fromisoformat(config.start_utc).timestamp()
        self.plans: dict[str, _UrbanState] = {}
        self._active_plans: set[str] = set()
        self.trips: dict[str, dict[str, Any]] = {}
        self._outcomes: dict[str, dict[str, Any]] = {}
        self._bookings: dict[str, dict[str, Any]] = {}
        self._events: list[tuple[float, int, str, str]] = []
        self._counter = 0
        self._decisions: list[dict[str, Any]] = []
        self._reservations: dict[str, list[tuple[float, float]]] = {
            **{f"car-{i}": [] for i in range(car_count)},
            **{f"bike-{i}": [] for i in range(bike_count)},
        }
        self._fund = 5_000_000
        self._contribution = 0
        self._guarantees = 0
        self._vehicle_km = 0.0
        self._new_completions: list[str] = []
        self._batch_runs = 0
        self._batch_assigned = 0
        if batch_matching:
            self._schedule(self.now + 30, "BATCH", "all")

    def _schedule(self, at: float, kind: str, target: str) -> None:
        self._counter += 1
        heapq.heappush(self._events, (at, self._counter, kind, target))

    def _available(self, vehicle: str, start: float, end: float) -> bool:
        fixed_busy = any(start < b and a < end for a, b in self._reservations[vehicle])
        pool_busy = any(
            state.vehicle == vehicle
            and state.plan.status != "PLAN_COMPLETED"
            and start < max(state.dropoffs.values()) + 300
            and min(state.pickups.values()) < end
            for state in (self.plans[key] for key in sorted(self._active_plans))
        )
        return not (fixed_busy or pool_busy)

    def _reserve(self, vehicle: str, start: float, end: float) -> None:
        self._reservations[vehicle].append((start, end))

    def _base_candidate(
        self,
        request: ScenarioRequest,
        service: str,
        candidate_id: str,
        km: float,
        minutes: float,
        price: int,
        *,
        eta: float = 5,
        existing: bool = False,
    ) -> dict[str, Any]:
        private = (
            fixed_fare(Service.CAR_URBAN_PRIVATE, km, minutes)
            if request.mode == "URBAN"
            else fixed_fare(Service.CAR_INTERCITY_PRIVATE, km, minutes)
        )
        quote = pool_quote(private) if service == Service.CAR_URBAN_POOL else {}
        return {
            "candidate_id": candidate_id,
            "service_code": str(service),
            "candidate_source_type": "EXISTING_POOL_PLAN"
            if existing
            else "SCHEDULED_INTERCITY_TRIP"
            if service == Service.CAR_INTERCITY_POOL
            else "NEW_SINGLE_VEHICLE",
            "direct_distance_km": km,
            "direct_duration_min": minutes,
            "effective_price_vnd": price,
            "planned_pickup_eta_min": eta,
            "in_vehicle_duration_min": minutes,
            "schedule_deviation_min": 0,
            "detour_ratio": 0.0,
            "extra_stops_count": 0,
            "walk_m": 0,
            "max_passenger_detour_ratio": 0.3,
            "max_walk_m": 0,
            "pool_quote_price_vnd": quote.get("quote", 0),
            "pool_unmatched_price_vnd": quote.get("unmatched", 0),
            "fare_matched_est_vnd": quote.get("matched_estimate", 0),
            "is_existing_plan": int(existing),
            "p_match_oof_est": 1.0 if existing else 0.5,
            "p_fulfill_oof_est": 0.9,
            "driver_rating_bayesian": 4.7,
            "active_pool_requests_15m_in_origin_zone": sum(
                1
                for state in (self.plans[key] for key in sorted(self._active_plans))
                for r in state.requests.values()
                if 0 <= request.time - r.time < 900
            ),
            "open_pool_plans_same_direction_in_radius": sum(
                self.plans[key].plan.status == "PLAN_OPEN_SEARCHING"
                for key in sorted(self._active_plans)
            ),
            "_private": private,
        }

    def quote(self, request: ScenarioRequest) -> list[dict[str, Any]]:
        start, end = Point(*request.pickup), Point(*request.dropoff)
        car = self.routing.route("car", start, end)
        if car.km > 150:
            return []
        preferred = max(request.preferred, request.earliest)
        candidates = []
        if request.mode == "URBAN":
            codes = [Service.CAR_URBAN_PRIVATE]
            if request.passengers == 1 and not request.has_luggage:
                codes.append(Service.BIKE_URBAN)
            if request.passengers <= 2:
                codes.append(Service.CAR_URBAN_POOL)
            for code in codes:
                bike = code == Service.BIKE_URBAN
                route = self.routing.route("motorbike", start, end) if bike else car
                fare = fixed_fare(code, route.km, route.minutes)
                if code == Service.CAR_URBAN_POOL:
                    quote = pool_quote(fare)
                    if quote["unmatched"] > request.budget_max:
                        continue
                    price = floor_money(Fraction(quote["matched_estimate"] + quote["unmatched"], 2))
                    rider = Rider(
                        request.id,
                        start,
                        end,
                        request.passengers,
                        request.earliest,
                        request.latest,
                        car.km,
                        car.minutes,
                        fare,
                        request.budget_max,
                        gender=request.gender,
                        same_gender=request.same_gender,
                    )
                    active = [
                        self.plans[key]
                        for key in sorted(self._active_plans)
                        if self.plans[key].plan.status == "PLAN_OPEN_SEARCHING"
                        and self.plans[key].confirmed
                    ][:20]
                    points = [start, end] + [
                        point
                        for state in active
                        for point in (
                            state.plan.current,
                            *(stop.point for stop in state.plan.stops),
                        )
                    ]
                    matrix = self.routing.matrix("car", points)
                    for state in active:
                        result = insert(state.plan, rider, matrix)
                        if result is None:
                            continue
                        if any(
                            min(state.pickups.values()) < b
                            and a < max(result.dropoff_times.values()) + 300
                            for a, b in self._reservations[state.vehicle]
                        ):
                            continue
                        row = self._base_candidate(
                            request,
                            str(code),
                            f"{request.id}:existing:{state.id}",
                            car.km,
                            car.minutes,
                            result.fares[rider.id]["charged"],
                            existing=True,
                        )
                        row.update(
                            {
                                "_state": state.id,
                                "_evaluation": result,
                                "_rider": rider,
                                "detour_ratio": result.detours[rider.id],
                                "p_match_oof_est": 1.0,
                                "fare_matched_est_vnd": result.fares[rider.id]["charged"],
                                "in_vehicle_duration_min": (
                                    result.dropoff_times[rider.id] - result.pickup_times[rider.id]
                                )
                                / 60,
                            }
                        )
                        candidates.append(row)
                else:
                    price = fare
                    if fare > request.budget_max:
                        continue
                vehicles = [
                    vehicle
                    for vehicle in self._reservations
                    if vehicle.startswith("bike" if bike else "car")
                    and self._available(vehicle, preferred, preferred + route.minutes * 60 + 300)
                ][:2]
                for vehicle in vehicles:
                    row = self._base_candidate(
                        request,
                        str(code),
                        f"{request.id}:{code}:{vehicle}",
                        route.km,
                        route.minutes,
                        price,
                    )
                    row.update(_vehicle=vehicle)
                    if code == Service.CAR_URBAN_POOL:
                        row["_rider"] = rider
                    candidates.append(row)
        else:
            fare = fixed_fare(Service.CAR_INTERCITY_PRIVATE, car.km, car.minutes)
            if fare <= request.budget_max:
                vehicles = [
                    vehicle
                    for vehicle in self._reservations
                    if vehicle.startswith("car")
                    and self._available(
                        vehicle, preferred - 1800, preferred + car.minutes * 120 + 1800
                    )
                ][:2]
                for vehicle in vehicles:
                    row = self._base_candidate(
                        request,
                        Service.CAR_INTERCITY_PRIVATE,
                        f"{request.id}:intercity-private:{vehicle}",
                        car.km,
                        car.minutes,
                        fare,
                        eta=20,
                    )
                    row["_vehicle"] = vehicle
                    candidates.append(row)
            if 72 <= (request.preferred - request.time) / 3600 <= 168:
                departure = np.ceil(request.preferred / 1800) * 1800
                for offset in range(2):
                    at = float(departure + offset * 1800)
                    if (
                        not request.earliest <= at <= request.latest
                        or at - request.time > 168 * 3600
                    ):
                        continue
                    trip_id = f"{request.corridor}:{int(at)}"
                    if trip_id not in self.trips:
                        self.trips[trip_id] = {
                            "id": trip_id,
                            "departure": at,
                            "corridor": request.corridor,
                            "seat_price": seat_reference(fare),
                            "private": fare,
                            "minutes": car.minutes,
                            "status": "OPEN_FOR_BOOKING",
                            "bookings": [],
                            "seats": 0,
                            "minimum": 3,
                            "origin": request.pickup,
                            "destination": request.dropoff,
                        }
                        self._schedule(at - 72 * 3600, "CLOSE_TRIP", trip_id)
                    trip = self.trips[trip_id]
                    price = trip["seat_price"] * request.passengers
                    if (
                        trip["status"] == "OPEN_FOR_BOOKING"
                        and trip["seats"] + request.passengers <= 4
                        and price <= request.budget_max
                    ):
                        row = self._base_candidate(
                            request,
                            Service.CAR_INTERCITY_POOL,
                            f"{request.id}:scheduled:{trip_id}",
                            car.km,
                            car.minutes,
                            price,
                            eta=0,
                        )
                        row.update(_trip=trip_id, _seats=request.passengers)
                        candidates.append(row)
        return candidates

    def book(self, request: ScenarioRequest, candidate: Mapping[str, Any]) -> str:
        booking_id = request.id + ":booking"
        service = str(candidate["service_code"])
        self._bookings[booking_id] = {
            "request": request,
            "candidate": dict(candidate),
            "price": int(candidate["effective_price_vnd"]),
            "service": service,
        }
        self._outcomes[booking_id] = {"driver_accepted": 1, "ride_started": 0, "completed": 0}
        if service == Service.CAR_INTERCITY_POOL:
            trip = self.trips[str(candidate["_trip"])]
            trip["bookings"].append(booking_id)
            trip["seats"] += request.passengers
            return booking_id
        if candidate.get("_state"):
            state = self.plans[str(candidate["_state"])]
            if state.strategic:
                # A real driver refusal changes behavior and removes the guarantee; no fake match.
                self._outcomes[booking_id].update(driver_accepted=0, outcome_time=request.time)
                for rider in state.plan.riders:
                    if rider.id not in state.locked:
                        quote = pool_quote(rider.private_fare)
                        state.locked[rider.id] = (
                            "UNMATCHED_LOCKED",
                            quote["quote"],
                            "DRIVER_DECLINED",
                        )
                state.plan = replace(state.plan, status="PLAN_CLOSED_TO_NEW")
                return booking_id
            result: EvaluatedPlan = candidate["_evaluation"]
            state.plan, state.fares = result.plan, result.fares
            state.pickups = state.pickups | result.pickup_times
            state.dropoffs = state.dropoffs | result.dropoff_times
            state.requests[request.id] = request
            state.plan = replace(
                state.plan,
                riders=tuple(
                    replace(rider, old_exact=Fraction(result.fares[rider.id]["exact"]))
                    for rider in state.plan.riders
                ),
            )
            self._anchor(state)
            return booking_id
        driver_draw = np.random.default_rng(
            _stable_seed(self.config.master_seed, "driver_accept", request.id)
        ).random()
        if driver_draw < 0.04:
            self._outcomes[booking_id].update(driver_accepted=0, outcome_time=request.time)
            return booking_id
        start = max(request.earliest, request.preferred)
        if service == Service.CAR_URBAN_POOL:
            rider: Rider = candidate["_rider"]
            state_id = request.id + ":plan"
            plan = PoolPlan(
                Point(*request.pickup),
                request.time,
                (rider,),
                (Stop(rider.id, "PICKUP", rider.pickup), Stop(rider.id, "DROPOFF", rider.dropoff)),
            )
            state = _UrbanState(
                state_id,
                plan,
                pickups={rider.id: start},
                dropoffs={rider.id: start + rider.direct_minutes * 60},
                requests={rider.id: request},
                strategic=np.random.default_rng(
                    _stable_seed(self.config.master_seed, "strategic", state_id)
                ).random()
                < self.config.strategic_driver_share,
                vehicle=str(candidate["_vehicle"]),
            )
            self.plans[state_id] = state
            self._active_plans.add(state_id)
            self._anchor(state)
            self._outcomes[booking_id]["driver_accepted"] = None
            self._schedule(request.time + 20, "CONFIRM_URBAN", state_id)
            self._schedule(min(start, request.time + 60), "URBAN_TICK", state_id)
        else:
            minutes = float(candidate["direct_duration_min"])
            self._reserve(
                str(candidate["_vehicle"]),
                start - (1800 if "INTERCITY" in service else 0),
                start + minutes * (120 if "INTERCITY" in service else 60) + 300,
            )
            self._schedule(start, "START_FIXED", booking_id)
            self._schedule(start + minutes * 60, "COMPLETE_FIXED", booking_id)
        return booking_id

    def _anchor(self, state: _UrbanState) -> None:
        state.anchor_plan = state.plan
        cumulative = state.plan.elapsed_km
        position = state.plan.current
        begun = state.plan.completed_stop_index >= 0
        timeline = []
        for index, stop in enumerate(
            state.plan.stops[state.plan.completed_stop_index + 1 :],
            state.plan.completed_stop_index + 1,
        ):
            if begun:
                cumulative += self.routing.route("car", position, stop.point).km
            at = (
                state.pickups[stop.rider_id]
                if stop.kind == "PICKUP"
                else state.dropoffs[stop.rider_id]
            )
            timeline.append((at, index, cumulative))
            position, begun = stop.point, True
        state.timeline = timeline

    def _sync_urban(self, state: _UrbanState, now: float) -> None:
        anchor = state.anchor_plan
        if anchor is None or state.plan.status in ("PLAN_COMPLETED", "PLAN_ABORTED"):
            return
        cumulative = anchor.elapsed_km
        position = anchor.current
        previous_time = anchor.now
        previous_km = cumulative
        completed = anchor.completed_stop_index
        for at, index, distance in state.timeline:
            stop = anchor.stops[index]
            if now >= at:
                cumulative, position, completed = distance, stop.point, index
                previous_time, previous_km = at + 60, distance
            else:
                fraction = min(1.0, max(0.0, (now - previous_time) / max(1, at - previous_time)))
                cumulative = previous_km + fraction * (distance - previous_km)
                position = Point(
                    position.lat + fraction * (stop.point.lat - position.lat),
                    position.lon + fraction * (stop.point.lon - position.lon),
                )
                break

        def distance_at(timestamp: float) -> float:
            last_time, last_km = anchor.now, anchor.elapsed_km
            for at, _, km in state.timeline:
                if timestamp < at:
                    return last_km + min(
                        1.0, max(0.0, (timestamp - last_time) / max(1, at - last_time))
                    ) * (km - last_km)
                last_time, last_km = at + 60, km
            return last_km

        for left in anchor.riders:
            for right in anchor.riders:
                overlap_start = max(anchor.now, state.pickups[left.id], state.pickups[right.id])
                overlap_end = min(now, state.dropoffs[left.id], state.dropoffs[right.id])
                if (
                    left.id < right.id
                    and overlap_end > overlap_start
                    and distance_at(overlap_end) > distance_at(overlap_start) + 1e-9
                ):
                    state.observed_overlap.update([left.id, right.id])
        updated = []
        for rider in anchor.riders:
            picked = state.pickups[rider.id] <= now
            pickup_distance = next(
                (
                    distance
                    for _, index, distance in state.timeline
                    if anchor.stops[index].rider_id == rider.id
                    and anchor.stops[index].kind == "PICKUP"
                ),
                anchor.elapsed_km,
            )
            traveled = (
                rider.traveled_km
                + max(
                    0,
                    cumulative
                    - (anchor.elapsed_km if rider.actual_pickup is not None else pickup_distance),
                )
                if picked
                else 0
            )
            drop_distance = next(
                (
                    distance
                    for _, index, distance in state.timeline
                    if anchor.stops[index].rider_id == rider.id
                    and anchor.stops[index].kind == "DROPOFF"
                ),
                cumulative,
            )
            if picked:
                self._outcomes[rider.id + ":booking"]["ride_started"] = 1
            if (
                picked
                and rider.id not in state.locked
                and (drop_distance - cumulative < 3 or now >= state.dropoffs[rider.id])
            ):
                if rider.id in state.observed_overlap and rider.id in state.fares:
                    status, final, cause = (
                        "MATCHED_LOCKED",
                        int(state.fares[rider.id]["charged"]),
                        "NONE",
                    )
                else:
                    status, final, cause = (
                        "UNMATCHED_LOCKED",
                        pool_quote(rider.private_fare)["unmatched"],
                        "NO_COMPATIBLE",
                    )
                state.locked[rider.id] = status, final, cause
            lock = state.locked.get(rider.id)
            updated.append(
                replace(
                    rider,
                    actual_pickup=state.pickups[rider.id] if picked else None,
                    traveled_km=traveled,
                    frozen=lock is not None,
                    frozen_charged=lock[1] if lock else None,
                )
            )
            outcome = self._outcomes[rider.id + ":booking"]
            if now >= state.dropoffs[rider.id] and not outcome.get("completed"):
                status, final, cause = state.locked[rider.id]
                outcome.update(
                    completed=1,
                    pool_final_matched=int(status == "MATCHED_LOCKED"),
                    unmatched_cause=cause,
                    final_price_vnd=final,
                    outcome_time=state.dropoffs[rider.id],
                    outcome_at=datetime.fromtimestamp(state.dropoffs[rider.id], UTC).isoformat(),
                )
                split = settlement(Service.CAR_URBAN_POOL, final, status, rider.private_fare, cause)
                self._fund += split["fund"] - split["guarantee"]
                self._contribution += split["fund"]
                self._guarantees += split["guarantee"]
                self._new_completions.append(rider.id + ":booking")
        first_pickup = min(state.pickups.values())
        status = (
            "PLAN_COMPLETED"
            if all(now >= at for at in state.dropoffs.values())
            else "PLAN_CLOSED_TO_NEW"
            if len(state.locked) == len(anchor.riders)
            else state.plan.status
        )
        state.plan = replace(
            anchor,
            current=position,
            now=now,
            riders=tuple(updated),
            completed_stop_index=completed,
            elapsed_km=cumulative,
            elapsed_minutes=max(0, (now - first_pickup) / 60),
            status=status,
        )
        if status == "PLAN_COMPLETED":
            self._active_plans.discard(state.id)

    def next_event_at(self) -> float | None:
        return self._events[0][0] if self._events else None

    def decisions(self) -> list[dict[str, Any]]:
        result, self._decisions = self._decisions, []
        return result

    def respond(self, booking_id: str, accept: bool) -> None:
        booking = self._bookings[booking_id]
        trip = self.trips[booking["trip"]]
        booking["response"] = accept
        if trip["status"] == "TOPUP_OFFERED":
            if not accept:
                trip["status"] = "UNDER_MIN_DRIVER_DECISION"
            elif all(self._bookings[b].get("response") is True for b in trip["bookings"]):
                trip["status"] = "CONFIRMED_TOPUP"
                for member in trip["bookings"]:
                    self._bookings[member]["price"] = (
                        trip["topup_seat"] * self._bookings[member]["request"].passengers
                    )
                self._confirm_trip(trip)
        elif trip["status"] == "MERGE_PENDING_CONFIRMATION" and not accept:
            trip["bookings"].remove(booking_id)
            trip["seats"] -= booking["request"].passengers
            self._outcomes[booking_id].update(
                completed=0, trip_confirmed_at_T72=0, final_price_vnd=0, outcome_time=self.now
            )

    def _confirm_trip(self, trip: dict[str, Any]) -> None:
        if not trip.get("completion_scheduled"):
            self._schedule(trip["departure"], "START_TRIP", trip["id"])
            self._schedule(trip["departure"] + trip["minutes"] * 60, "COMPLETE_TRIP", trip["id"])
            trip["completion_scheduled"] = True
        for booking in trip["bookings"]:
            self._outcomes[booking]["trip_confirmed_at_T72"] = 1

    def _cancel_trip(self, trip: dict[str, Any]) -> None:
        trip["status"] = "CANCELLED_LOW_DEMAND"
        for booking in trip["bookings"]:
            self._outcomes[booking].update(
                trip_confirmed_at_T72=0,
                completed=0,
                final_price_vnd=0,
                outcome_time=self.now,
                outcome_at=datetime.fromtimestamp(self.now, UTC).isoformat(),
            )

    def _under_min(self, trip: dict[str, Any]) -> None:
        trip["status"] = "UNDER_MIN_DRIVER_DECISION"
        self._schedule(trip["departure"] - 60 * 3600, "UNDER_MIN", trip["id"])

    def _topup(self, trip: dict[str, Any]) -> None:
        if not trip["bookings"]:
            self._cancel_trip(trip)
            return
        trip["status"] = "TOPUP_OFFERED"
        trip["topup_seat"] = floor_money(Fraction(trip["private"], trip["seats"]))
        for booking_id in trip["bookings"]:
            booking = self._bookings[booking_id]
            booking["trip"] = trip["id"]
            self._decisions.append(
                {
                    "booking_id": booking_id,
                    "request_id": booking["request"].id,
                    "final_price_vnd": trip["topup_seat"] * booking["request"].passengers,
                }
            )
        self._schedule(self.now + 6 * 3600, "TOPUP_TIMEOUT", trip["id"])

    def _close_trip(self, trip: dict[str, Any]) -> None:
        if trip["status"] != "OPEN_FOR_BOOKING":
            return
        if trip["seats"] >= trip["minimum"]:
            trip["status"] = "CONFIRMED"
            self._confirm_trip(trip)
        elif not trip["seats"]:
            self._cancel_trip(trip)
        elif not self.rescue_intercity:
            self._under_min(trip)
        else:
            neighbors = [
                self.trips[key]
                for delta in (-2, -1, 1, 2)
                if (key := f"{trip['corridor']}:{int(trip['departure'] + delta * 1800)}")
                in self.trips
            ]
            compatible = [
                other
                for other in neighbors
                if other["status"] == "OPEN_FOR_BOOKING"
                and 0 < other["seats"]
                and trip["seats"] + other["seats"] <= 4
                and all(
                    self._bookings[b]["request"].earliest
                    <= trip["departure"]
                    <= self._bookings[b]["request"].latest
                    for b in other["bookings"]
                )
            ]
            if compatible:
                source = sorted(compatible, key=lambda other: other["id"])[0]
                for booking_id in source["bookings"]:
                    booking = self._bookings[booking_id]
                    booking["price"] = min(
                        booking["price"], trip["seat_price"] * booking["request"].passengers
                    )
                    booking["trip"] = trip["id"]
                    self._decisions.append(
                        {
                            "booking_id": booking_id,
                            "request_id": booking["request"].id,
                            "final_price_vnd": booking["price"],
                        }
                    )
                trip["bookings"].extend(source["bookings"])
                trip["seats"] += source["seats"]
                source["status"] = "MERGED"
                trip["status"] = "MERGE_PENDING_CONFIRMATION"
                self._schedule(self.now + 2 * 3600, "MERGE_CHECK", trip["id"])
            else:
                self._topup(trip)

    def _batch(self) -> None:
        """Only not-yet-accepted Pool offers move; deposited riders stay on their plan."""
        from app.domain.batch_matcher import Bundle, solve_bundles

        pending = [
            self.plans[key]
            for key in sorted(self._active_plans)
            if not self.plans[key].confirmed and len(self.plans[key].plan.riders) == 1
        ][:10]
        targets = [
            self.plans[key]
            for key in sorted(self._active_plans)
            if self.plans[key].confirmed and self.plans[key].plan.status == "PLAN_OPEN_SEARCHING"
        ][:10]
        if not pending or not targets:
            return
        points = [
            point
            for state in pending + targets
            for point in (state.plan.current, *(stop.point for stop in state.plan.stops))
        ]
        matrix = self.routing.matrix("car", points)
        bundles = []
        for target in targets:
            feasible = []
            old_total = (
                sum((Fraction(fare["exact"]) for fare in target.fares.values()), Fraction())
                if target.fares
                else Fraction(target.plan.riders[0].private_fare)
            )
            for source in pending:
                rider = source.plan.riders[0]
                result = insert(target.plan, rider, matrix)
                if result is not None:
                    feasible.append((source, result))
                    new_total = sum(
                        (Fraction(fare["exact"]) for fare in result.fares.values()), Fraction()
                    )
                    bundles.append(
                        Bundle(
                            f"{target.id}|{source.id}",
                            target.id,
                            (rider.id,),
                            int(old_total + rider.private_fare - new_total),
                            (result, (source.id,)),
                        )
                    )
            for index, (left, first) in enumerate(feasible):
                for right, _ in feasible[index + 1 :]:
                    # The second insertion evaluates the joint route. Independent edges are never added.
                    result = insert(first.plan, right.plan.riders[0], matrix)
                    if result is not None:
                        new_total = sum(
                            (Fraction(fare["exact"]) for fare in result.fares.values()), Fraction()
                        )
                        gain = (
                            old_total
                            + left.plan.riders[0].private_fare
                            + right.plan.riders[0].private_fare
                            - new_total
                        )
                        bundles.append(
                            Bundle(
                                f"{target.id}|{left.id}|{right.id}",
                                target.id,
                                (left.plan.riders[0].id, right.plan.riders[0].id),
                                int(gain),
                                (result, (left.id, right.id)),
                            )
                        )
        solution = solve_bundles(bundles, {state.plan.riders[0].id for state in pending})
        self._batch_runs += 1
        for bundle in solution.selected:
            target = self.plans[bundle.vehicle_id]
            result, source_ids = bundle.payload
            if any(self.plans[source_id].confirmed for source_id in source_ids):
                continue
            if any(
                min(target.pickups.values()) < end
                and begin < max(result.dropoff_times.values()) + 300
                for begin, end in self._reservations[target.vehicle]
            ):
                continue
            target.plan, target.fares = result.plan, result.fares
            target.pickups = target.pickups | result.pickup_times
            target.dropoffs = target.dropoffs | result.dropoff_times
            target.plan = replace(
                target.plan,
                riders=tuple(
                    replace(rider, old_exact=Fraction(result.fares[rider.id]["exact"]))
                    for rider in target.plan.riders
                ),
            )
            for source_id in source_ids:
                source = self.plans[source_id]
                target.requests.update(source.requests)
                source.plan = replace(source.plan, status="PLAN_ABORTED")
                self._active_plans.discard(source_id)
                for rider in source.plan.riders:
                    self._outcomes[rider.id + ":booking"]["driver_accepted"] = 1
                self._batch_assigned += len(source.plan.riders)
            self._anchor(target)

    def advance(self, now: float) -> None:
        if now < self.now:
            raise ValueError("Simulation clock cannot move backwards")
        self.now = now
        for key in sorted(self._active_plans):
            self._sync_urban(self.plans[key], now)
        for vehicle, reservations in self._reservations.items():
            self._reservations[vehicle] = [(a, b) for a, b in reservations if b > now]
        while self._events and self._events[0][0] <= now:
            _, _, kind, target = heapq.heappop(self._events)
            if kind == "URBAN_TICK":
                state = self.plans[target]
                if state.plan.status not in ("PLAN_COMPLETED", "PLAN_ABORTED"):
                    self._schedule(
                        min(now + 60, max(state.dropoffs.values())), "URBAN_TICK", target
                    )
            elif kind == "CONFIRM_URBAN":
                state = self.plans[target]
                if state.plan.status != "PLAN_ABORTED":
                    state.confirmed = True
                    for rider in state.plan.riders:
                        self._outcomes[rider.id + ":booking"]["driver_accepted"] = 1
            elif kind == "BATCH":
                self._batch()
                horizon = (
                    datetime.fromisoformat(self.config.start_utc).timestamp()
                    + self.config.days * 86400
                    + 60
                )
                if now + 30 <= horizon:
                    self._schedule(now + 30, "BATCH", "all")
            elif kind == "START_FIXED":
                self._outcomes[target]["ride_started"] = 1
            elif kind == "COMPLETE_FIXED":
                booking = self._bookings[target]
                self._outcomes[target].update(
                    completed=1,
                    final_price_vnd=booking["price"],
                    outcome_time=now,
                    outcome_at=datetime.fromtimestamp(now, UTC).isoformat(),
                )
                self._vehicle_km += float(booking["candidate"]["direct_distance_km"])
                self._new_completions.append(target)
            elif kind == "CLOSE_TRIP":
                self._close_trip(self.trips[target])
            elif kind == "MERGE_CHECK":
                trip = self.trips[target]
                if trip["status"] == "MERGE_PENDING_CONFIRMATION":
                    if trip["seats"] >= trip["minimum"]:
                        trip["status"] = "CONFIRMED"
                        self._confirm_trip(trip)
                    else:
                        self._topup(trip)
            elif kind == "TOPUP_TIMEOUT":
                trip = self.trips[target]
                if trip["status"] in ("TOPUP_OFFERED", "UNDER_MIN_DRIVER_DECISION"):
                    self._under_min(trip)
            elif kind == "UNDER_MIN":
                trip = self.trips[target]
                if trip["status"] == "UNDER_MIN_DRIVER_DECISION":
                    run = (
                        np.random.default_rng(
                            _stable_seed(self.config.master_seed, "run_under_min", target)
                        ).random()
                        < 0.25
                    )
                    if run:
                        trip["status"] = "CONFIRMED_UNDER_MIN"
                        self._confirm_trip(trip)
                    else:
                        self._cancel_trip(trip)
            elif kind in ("START_TRIP", "COMPLETE_TRIP"):
                trip = self.trips[target]
                for booking_id in trip["bookings"]:
                    self._outcomes[booking_id]["ride_started"] = 1
                    if kind == "COMPLETE_TRIP":
                        self._outcomes[booking_id].update(
                            completed=1,
                            final_price_vnd=self._bookings[booking_id]["price"],
                            outcome_time=now,
                            outcome_at=datetime.fromtimestamp(now, UTC).isoformat(),
                        )
                        self._new_completions.append(booking_id)
                if kind == "COMPLETE_TRIP":
                    trip["status"] = "COMPLETED"

    def outcomes(self) -> Mapping[str, Mapping[str, Any]]:
        return self._outcomes

    def observed_completions(self) -> list[str]:
        completed, self._new_completions = self._new_completions, []
        return completed

    def metrics(self) -> Mapping[str, Any]:
        pool = [
            outcome
            for booking, outcome in self._outcomes.items()
            if self._bookings[booking]["service"] == Service.CAR_URBAN_POOL
            and outcome.get("completed")
        ]
        matched = sum(outcome.get("pool_final_matched", 0) for outcome in pool)
        return {
            "selected_bookings": len(self._outcomes),
            "completed_bookings": sum(
                outcome.get("completed", 0) for outcome in self._outcomes.values()
            ),
            "pool_completed": len(pool),
            "pool_matched": matched,
            "p_actual_booking": matched / len(pool) if pool else None,
            "fund_initial_vnd": 5_000_000,
            "fund_balance_vnd": self._fund,
            "fund_contributions_vnd": self._contribution,
            "guarantee_payouts_vnd": self._guarantees,
            "vehicle_km_fixed": self._vehicle_km,
            "intercity_published": len(self.trips),
            "intercity_cancelled_low_demand": sum(
                trip["status"] == "CANCELLED_LOW_DEMAND" for trip in self.trips.values()
            ),
            "intercity_merged": sum(trip["status"] == "MERGED" for trip in self.trips.values()),
            "rescue_intercity_enabled": self.rescue_intercity,
            "intercity_published_with_bookings": sum(
                bool(trip["bookings"]) for trip in self.trips.values()
            ),
            "intercity_cancelled_low_demand_with_bookings": sum(
                trip["status"] == "CANCELLED_LOW_DEMAND" and bool(trip["bookings"])
                for trip in self.trips.values()
            ),
            "batch_matching_enabled": self.batch_matching,
            "batch_solver_runs": self._batch_runs,
            "batch_assigned_requests": self._batch_assigned,
        }
