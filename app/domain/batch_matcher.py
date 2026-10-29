"""RTV set packing over bundles already verified by the real insertion engine."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Bundle:
    id: str
    vehicle_id: str
    request_ids: tuple[str, ...]
    gain_vnd: int
    payload: Any = None


@dataclass(frozen=True)
class BatchSolution:
    selected: tuple[Bundle, ...]
    unassigned: frozenset[str]
    solver_status: str
    fallback: bool


def solve_bundles(
    bundles: list[Bundle],
    requests: set[str],
    time_limit_s: float = 3,
    unassigned_penalty_vnd: int = 50000,
) -> BatchSolution:
    if len({b.id for b in bundles}) != len(bundles) or any(
        not 1 <= len(b.request_ids) <= 2
        or len(set(b.request_ids)) != len(b.request_ids)
        or not set(b.request_ids) <= requests
        for b in bundles
    ):
        raise ValueError("Invalid or duplicate RTV bundle")
    from ortools.sat.python import cp_model

    model = cp_model.CpModel()
    variables = {b.id: model.new_bool_var(b.id) for b in bundles}
    vehicles = {b.vehicle_id for b in bundles}
    for vehicle in vehicles:
        model.add(sum(variables[b.id] for b in bundles if b.vehicle_id == vehicle) <= 1)
    unassigned = {r: model.new_bool_var("unassigned:" + r) for r in sorted(requests)}
    for request in sorted(requests):
        model.add(
            sum(variables[b.id] for b in bundles if request in b.request_ids) + unassigned[request]
            == 1
        )
    model.maximize(
        sum(b.gain_vnd * variables[b.id] for b in bundles)
        - unassigned_penalty_vnd * sum(unassigned.values())
    )
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(0.001, time_limit_s)
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 0
    status = solver.solve(model)
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        chosen = tuple(b for b in bundles if solver.value(variables[b.id]))
        return BatchSolution(
            chosen,
            frozenset(r for r in requests if solver.value(unassigned[r])),
            solver.status_name(status),
            False,
        )
    used_vehicles: set[str] = set()
    used_requests: set[str] = set()
    chosen = []
    for bundle in sorted(bundles, key=lambda b: (-b.gain_vnd, b.id)):
        if bundle.vehicle_id not in used_vehicles and not used_requests.intersection(
            bundle.request_ids
        ):
            chosen.append(bundle)
            used_vehicles.add(bundle.vehicle_id)
            used_requests.update(bundle.request_ids)
    return BatchSolution(
        tuple(chosen), frozenset(requests - used_requests), solver.status_name(status), True
    )
