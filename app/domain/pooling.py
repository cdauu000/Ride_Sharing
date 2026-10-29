"""Forward-only insertion and all-rider hard-constraint evaluation (Rev9 §36)."""

from dataclasses import dataclass, field, replace
from fractions import Fraction

from app.domain.errors import DomainError
from app.domain.pricing import FareInput, plan_fare, pool_quote, price_pool
from app.domain.types import Point
from app.routing import Matrix


@dataclass(frozen=True)
class Rider:
    id: str
    pickup: Point
    dropoff: Point
    seats: int
    earliest: float
    latest: float
    direct_km: float
    direct_minutes: float
    private_fare: int
    budget_max: int
    max_detour: float = 0.3
    max_minutes: float | None = None
    latest_arrival: float | None = None
    gender: str = "UNKNOWN"
    same_gender: bool = False
    traveled_km: float = 0
    actual_pickup: float | None = None
    old_exact: Fraction | None = None
    frozen: bool = False
    frozen_charged: int | None = None


@dataclass(frozen=True)
class Stop:
    rider_id: str
    kind: str
    point: Point


@dataclass(frozen=True)
class PoolPlan:
    current: Point
    now: float
    riders: tuple[Rider, ...]
    stops: tuple[Stop, ...]
    completed_stop_index: int = -1
    elapsed_km: float = 0
    elapsed_minutes: float = 0
    capacity: int = 4
    max_driver_detour_km: float = 10
    max_driver_detour_min: float = 30
    max_additional_pickups: int = 3
    status: str = "PLAN_OPEN_SEARCHING"


@dataclass(frozen=True)
class EvaluatedPlan:
    plan: PoolPlan
    total_km: float
    total_minutes: float
    fares: dict[str, dict]
    pickup_times: dict[str, float]
    dropoff_times: dict[str, float]
    detours: dict[str, float]
    overlaps: frozenset[tuple[str, str]] = field(default_factory=frozenset)


def evaluate(plan: PoolPlan, matrix: Matrix, new_id: str | None = None) -> EvaluatedPlan:
    if len(plan.stops) > 8 or len(plan.riders) - 1 > plan.max_additional_pickups:
        raise DomainError("DRIVER_STOP_LIMIT")
    riders = {r.id: r for r in plan.riders}
    if len(riders) != len(plan.riders):
        raise DomainError("DUPLICATE_RIDER")
    onboard = {
        r.id
        for r in plan.riders
        if r.actual_pickup is not None
        and any(
            s.rider_id == r.id and s.kind == "DROPOFF"
            for s in plan.stops[plan.completed_stop_index + 1 :]
        )
    }
    picked = {r.id: r.actual_pickup for r in plan.riders if r.actual_pickup is not None}
    dropped: dict[str, float] = {}
    traveled = {r.id: r.traveled_km for r in plan.riders}
    overlaps: set[tuple[str, str]] = set()
    now, position = plan.now, plan.current
    total_km, total_min = plan.elapsed_km, plan.elapsed_minutes
    fare_started = plan.completed_stop_index >= 0
    for index, stop in enumerate(
        plan.stops[plan.completed_stop_index + 1 :], plan.completed_stop_index + 1
    ):
        if stop.rider_id not in riders:
            raise DomainError("UNKNOWN_STOP_RIDER")
        leg = matrix.leg(position, stop.point)
        load = sum(riders[r].seats for r in onboard)
        if not 0 <= load <= plan.capacity:
            raise DomainError("SEGMENT_CAPACITY_EXCEEDED")
        for r in onboard:
            traveled[r] += leg.km
        if leg.km > 0:
            for a in onboard:
                for b in onboard:
                    if a < b:
                        if (riders[a].same_gender or riders[b].same_gender) and (
                            riders[a].gender == "UNKNOWN" or riders[a].gender != riders[b].gender
                        ):
                            raise DomainError("SOCIAL_CONSTRAINT")
                        overlaps.add((a, b))
        now += leg.minutes * 60
        if fare_started:
            total_km += leg.km
            total_min += leg.minutes
        rider = riders[stop.rider_id]
        if stop.kind == "PICKUP":
            if rider.id in picked:
                raise DomainError("DUPLICATE_PICKUP")
            waiting = max(0, rider.earliest - now)
            now += waiting
            if fare_started:
                total_min += waiting / 60
            if now > rider.latest:
                raise DomainError("PICKUP_WINDOW_VIOLATION")
            picked[rider.id] = now
            onboard.add(rider.id)
            fare_started = True
        elif stop.kind == "DROPOFF":
            if rider.id not in onboard:
                raise DomainError("DROPOFF_BEFORE_PICKUP")
            onboard.remove(rider.id)
            dropped[rider.id] = now
            limit = rider.max_minutes or (rider.direct_minutes * 1.5 + 10)
            if (now - picked[rider.id]) / 60 > limit + 1e-7:
                raise DomainError("IN_VEHICLE_TIME_VIOLATION")
            if rider.latest_arrival is not None and now > rider.latest_arrival:
                raise DomainError("LATEST_ARRIVAL_VIOLATION")
        else:
            raise DomainError("INVALID_STOP_KIND")
        if index < len(plan.stops) - 1:
            now += 60
            total_min += 1
        position = stop.point
    if onboard:
        raise DomainError("MISSING_DROPOFF")
    detours = {}
    inputs = []
    for rider in plan.riders:
        detour = max(0.0, (traveled[rider.id] - rider.direct_km) / rider.direct_km)
        if rider.id in dropped and detour > rider.max_detour + 1e-7:
            raise DomainError("PASSENGER_DETOUR_VIOLATION")
        if pool_quote(rider.private_fare)["unmatched"] > rider.budget_max:
            raise DomainError("BUDGET_EXCEEDED")
        detours[rider.id] = detour
        inputs.append(
            FareInput(
                rider.id,
                rider.private_fare,
                rider.direct_minutes,
                rider.seats,
                detour,
                old_exact=rider.old_exact,
                frozen=rider.frozen,
                frozen_charged=rider.frozen_charged,
            )
        )
    if new_id:
        old_open = {r.id for r in plan.riders if r.id != new_id and not r.frozen}
        if plan.status != "PLAN_OPEN_SEARCHING" or not old_open:
            raise DomainError("PLAN_CLOSED_TO_NEW")
        if not any(
            new_id in pair and any(r in old_open for r in pair if r != new_id) for pair in overlaps
        ):
            raise DomainError("NO_CORIDING_OVERLAP")
    fares = price_pool(inputs, plan_fare(total_km, total_min, len(plan.stops)), total_min)
    return EvaluatedPlan(
        plan, total_km, total_min, fares, picked, dropped, detours, frozenset(overlaps)
    )


def insert(plan: PoolPlan, rider: Rider, matrix: Matrix) -> EvaluatedPlan | None:
    """Enumerate only future positions; completed prefix is immutable."""
    if plan.status != "PLAN_OPEN_SEARCHING" or len(plan.stops) + 2 > 8:
        return None
    best: EvaluatedPlan | None = None
    for p_idx in range(plan.completed_stop_index + 1, len(plan.stops) + 1):
        with_pickup = list(plan.stops)
        with_pickup.insert(p_idx, Stop(rider.id, "PICKUP", rider.pickup))
        for q_idx in range(p_idx + 1, len(with_pickup) + 1):
            stops = with_pickup.copy()
            stops.insert(q_idx, Stop(rider.id, "DROPOFF", rider.dropoff))
            proposed = replace(plan, riders=(*plan.riders, rider), stops=tuple(stops))
            try:
                result = evaluate(proposed, matrix, rider.id)
                baseline_km = max(r.direct_km for r in plan.riders)
                baseline_min = max(r.direct_minutes for r in plan.riders)
                if (
                    result.total_km - baseline_km > plan.max_driver_detour_km
                    or result.total_minutes - baseline_min > plan.max_driver_detour_min
                ):
                    continue
                if best is None or plan_fare(
                    result.total_km, result.total_minutes, len(stops)
                ) < plan_fare(best.total_km, best.total_minutes, len(stops)):
                    best = result
            except DomainError:
                continue
    return best
