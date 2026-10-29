"""Revision 9 §§10–19,28. Rational allocations; integer VND at settlement."""

from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from app.config import baseline
from app.domain.errors import DomainError
from app.domain.types import Service


def q(value: int | float | str | Fraction) -> Fraction:
    return value if isinstance(value, Fraction) else Fraction(str(value))


def floor_money(value: int | float | str | Fraction, step: int = 1000) -> int:
    if q(value) < 0:
        raise DomainError("NEGATIVE_MONEY", status=422)
    return int(q(value) // step) * step


def fixed_fare(service: Service | str, km: float, minutes: float) -> int:
    if km <= 0 or minutes <= 0:
        raise DomainError("INVALID_ROUTE", status=422)
    cfg = baseline()
    group = cfg[
        "bike_urban"
        if service == Service.BIKE_URBAN
        else "car_intercity_private"
        if "INTERCITY" in service
        else "car_urban"
    ]
    return floor_money(
        q(group["base_vnd"])
        + q(group["per_km_vnd"]) * q(km)
        + q(group.get("per_min_vnd", 0)) * q(minutes)
    )


def plan_fare(km: float, minutes: float, stops: int) -> Fraction:
    cfg = baseline()["car_urban"]
    return (
        q(cfg["base_vnd"])
        + q(cfg["per_km_vnd"]) * q(km)
        + q(cfg["per_min_vnd"]) * q(minutes)
        + q(cfg["extra_stop_fee_vnd"]) * max(0, stops - 2)
    )


def pool_quote(private: int) -> dict[str, int]:
    cfg = baseline()["car_urban"]
    quote = floor_money(q(private) * (1 - q(cfg["d_min"])))
    unmatched = floor_money(quote + q(cfg["unmatched_passenger_share_alpha"]) * (private - quote))
    return {
        "private_fare": private,
        "quote": quote,
        "gap": private - quote,
        "unmatched": unmatched,
        "matched_estimate": floor_money(q(private) * (1 - q(cfg["d_matched_typical"]))),
    }


@dataclass(frozen=True)
class FareInput:
    id: str
    private: int
    direct_minutes: float
    seats: int = 1
    detour: float = 0
    walk_ratio: float = 0
    old_exact: Fraction | None = None
    frozen: bool = False
    frozen_charged: int | None = None


def bounds(item: FareInput) -> tuple[Fraction, Fraction, Fraction]:
    cfg = baseline()["car_urban"]
    if item.seats not in (1, 2) or item.private <= 0 or item.detour < 0 or item.walk_ratio < 0:
        raise DomainError("INVALID_FARE_INPUT", status=422)
    factor = 1 + q(cfg["party_seat_surcharge_gamma"]) * (item.seats - 1)
    cap = q(item.private) * (1 - q(cfg["d_min"]))
    if item.old_exact is not None:
        cap = min(cap, item.old_exact)
    floor = min(cap, max(q(cfg["base_vnd"]), q(item.private) * (1 - q(cfg["d_max"])) * factor))
    weight = (
        q(item.private)
        * (
            1
            + q(cfg["detour_weight_lambda"]) * q(item.detour)
            + q(cfg["walk_weight_mu"]) * q(item.walk_ratio)
        )
        / factor
    )
    return floor, cap, weight


def allocate(items: list[FareInput], target: Fraction | int) -> dict[str, Fraction]:
    """Exact breakpoint water filling. No epsilon or iterative float clamping."""
    if not items or len({item.id for item in items}) != len(items):
        raise DomainError("EMPTY_OR_DUPLICATE_ALLOCATION")
    target = q(target)
    edges = {item.id: bounds(item) for item in items}
    floors = sum((row[0] for row in edges.values()), Fraction())
    caps = sum((row[1] for row in edges.values()), Fraction())
    if target < floors:
        raise DomainError("INFEASIBLE_LOWER_BOUND")
    if target > caps:
        raise DomainError("INFEASIBLE_UPPER_BOUND")

    def values(tau: Fraction) -> dict[str, Fraction]:
        return {
            item.id: min(
                edges[item.id][1], max(edges[item.id][0], item.private - tau * edges[item.id][2])
            )
            for item in items
        }

    breaks = sorted(
        {(item.private - edge) / edges[item.id][2] for item in items for edge in edges[item.id][:2]}
    )
    for low, high in zip(breaks, breaks[1:], strict=False):
        at_low, at_high = values(low), values(high)
        sum_low, sum_high = sum(at_low.values()), sum(at_high.values())
        if sum_low == target:
            return at_low
        if sum_high <= target < sum_low:
            tau = low + (sum_low - target) * (high - low) / (sum_low - sum_high)
            return values(tau)
    result = values(breaks[-1])
    if sum(result.values()) != target:
        raise DomainError("ALLOCATION_INTERNAL_ERROR", status=500)
    return result


def price_pool(
    items: list[FareInput], total: Fraction, minutes: float, enforce_economics: bool = True
) -> dict[str, dict[str, Any]]:
    cfg = baseline()["car_urban"]
    if total > sum(item.private for item in items) * (1 - q(cfg["d_min"])):
        raise DomainError("PASSENGER_SHAREABILITY_REJECTED")
    locked = [item for item in items if item.frozen]
    unlocked = [item for item in items if not item.frozen]
    if any(item.old_exact is None or item.frozen_charged is None for item in locked):
        raise DomainError("INVALID_FROZEN_PRICE")
    fares = allocate(unlocked, total - sum((item.old_exact for item in locked), Fraction()))
    fares.update({item.id: item.old_exact for item in locked})
    rows: dict[str, dict[str, Any]] = {}
    for item in items:
        exact = fares[item.id]
        charged = item.frozen_charged if item.frozen else floor_money(exact)
        floor, cap, weight = bounds(item)
        rows[item.id] = {
            "exact": str(exact),
            "charged": charged,
            "rounding": str(exact - charged),
            "floor": str(floor),
            "cap": str(cap),
            "weight": str(weight),
        }
    if enforce_economics:
        payout = q("0.85") * sum(row["charged"] for row in rows.values())
        if payout < max(q("0.8") * item.private for item in items):
            raise DomainError("DRIVER_TOTAL_PAYOUT_REJECTED")
        if minutes <= 0 or any(item.direct_minutes <= 0 for item in items):
            raise DomainError("INVALID_DURATION")
        if payout / q(minutes) < max(
            q("0.8") * item.private / q(item.direct_minutes) for item in items
        ):
            raise DomainError("DRIVER_HOURLY_RATE_REJECTED")
    return rows


def settlement(
    service: str,
    charged: int,
    price_status: str = "FIXED_LOCKED",
    private: int = 0,
    cause: str = "NO_COMPATIBLE",
) -> dict[str, int]:
    if service == Service.CAR_URBAN_POOL:
        matched = price_status == "MATCHED_LOCKED"
        driver = charged * 85 // 100
        fund = charged * 3 // 100 if matched else 0
        guarantee = (
            max(0, private * 80 // 100 - driver)
            if (
                not matched
                and cause in {"NO_COMPATIBLE", "CORIDER_CANCELLED_EARLY", "PASSENGER_REJECTED_POOL"}
            )
            else 0
        )
    else:
        commission = (
            10
            if service == Service.CAR_INTERCITY_POOL and price_status != "TOPUP_LOCKED"
            else 15
            if "INTERCITY" in service
            else 20
        )
        driver, fund, guarantee = charged * (100 - commission) // 100, 0, 0
    return {
        "gross": charged,
        "driver_base": driver,
        "platform": charged - driver - fund,
        "fund": fund,
        "guarantee": guarantee,
        "driver_total": driver + guarantee,
    }


def seat_reference(private: int) -> int:
    return floor_money(q(private) * q("0.85") / (3 * q("0.9")))


def cancellation(
    service: str,
    fare: int,
    quote: int,
    seconds_since_confirmed: float,
    lead_hours: float,
    scheduled: bool,
    no_show: bool = False,
    has_coriders: bool = False,
    driver_fault: bool = False,
    confirmed_trip: bool = True,
    merge_free_window: bool = False,
) -> dict[str, int]:
    if driver_fault or seconds_since_confirmed < 0 or merge_free_window:
        fee, driver_rate, fund_rate = 0, 0, 0
    elif service == Service.CAR_INTERCITY_POOL:
        rate = (
            1 if no_show or lead_hours <= 24 else 0.5 if confirmed_trip and lead_hours < 72 else 0
        )
        fee, driver_rate, fund_rate = int(q(fare) * q(rate)), 90, 0
    elif service == Service.CAR_INTERCITY_PRIVATE:
        free = not no_show and (lead_hours > 2 if scheduled else seconds_since_confirmed <= 120)
        fee, driver_rate, fund_rate = (0 if free else fare * 20 // 100), 85, 0
    elif not no_show and seconds_since_confirmed <= 120:
        fee, driver_rate, fund_rate = 0, 0, 0
    elif service == Service.CAR_URBAN_POOL:
        fee, driver_rate, fund_rate = (
            quote * 20 // 100,
            (50 if has_coriders else 85),
            (50 if has_coriders else 15),
        )
    else:
        fee, driver_rate, fund_rate = min(20000, fare * 20 // 100), 80, 0
    driver, fund = fee * driver_rate // 100, fee * fund_rate // 100
    return {"fee": fee, "driver": driver, "fund": fund, "platform": fee - driver - fund}
