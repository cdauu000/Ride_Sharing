from fractions import Fraction

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.domain.errors import DomainError
from app.domain.pricing import (
    FareInput,
    allocate,
    bounds,
    cancellation,
    fixed_fare,
    floor_money,
    pool_quote,
    price_pool,
    q,
    seat_reference,
    settlement,
)


def test_revision9_canonical_pool_vector() -> None:
    inputs = [FareInput("A", 194000, 40, detour=0.25), FareInput("B", 133000, 28)]
    fares = price_pool(inputs, q(248500), 52)
    assert [fares[key]["charged"] for key in ("A", "B")] == [143000, 105000]
    assert sum(Fraction(r["exact"]) for r in fares.values()) == 248500
    assert sum(Fraction(r["rounding"]) for r in fares.values()) == 500
    split = [settlement("CAR_URBAN_POOL", r["charged"], "MATCHED_LOCKED") for r in fares.values()]
    assert sum(s["driver_total"] for s in split) == 210800
    assert sum(s["platform"] for s in split) == 29760
    assert sum(s["fund"] for s in split) == 7440


def test_two_seats_never_change_quote_reference() -> None:
    inputs = [FareInput("A", 194000, 40, seats=2, detour=0.25), FareInput("B", 133000, 28)]
    result = price_pool(inputs, q(248500), 52)
    assert [result[k]["charged"] for k in ("A", "B")] == [148000, 99000]
    assert pool_quote(194000)["quote"] == 155000
    assert pool_quote(194000)["unmatched"] == 174000


def test_floor_rejection_and_simultaneous_bounds() -> None:
    inputs = [FareInput("0", 45000, 10, detour=0.3, walk_ratio=0.2)] + [
        FareInput(str(i), 205000, 40) for i in range(1, 4)
    ]
    result = allocate(inputs, 280000)
    assert result["0"] == 20000
    assert result["1"] == Fraction(260000, 3)
    with pytest.raises(DomainError, match="INFEASIBLE_LOWER_BOUND"):
        allocate(inputs, 220000)


def test_dynamic_price_preserves_frozen_and_decreases_old() -> None:
    old = price_pool(
        [FareInput("A", 194000, 40, detour=0.25), FareInput("B", 133000, 28)], q(248500), 52
    )
    new = price_pool(
        [
            FareInput("A", 194000, 40, detour=0.28, old_exact=Fraction(old["A"]["exact"])),
            FareInput(
                "B",
                133000,
                28,
                old_exact=Fraction(old["B"]["exact"]),
                frozen=True,
                frozen_charged=105000,
            ),
            FareInput("C", 64000, 20, detour=0.05),
        ],
        q(288500),
        60,
    )
    assert [new[k]["charged"] for k in ("A", "B", "C")] == [135000, 105000, 48000]
    assert new["B"]["exact"] == old["B"]["exact"]


def test_unmatched_and_driver_decline_exact_money() -> None:
    split = settlement("CAR_URBAN_POOL", 174000, "UNMATCHED_LOCKED", 194000)
    assert split["guarantee"] == 7300
    assert split["driver_total"] == 155200
    declined = settlement("CAR_URBAN_POOL", 155000, "UNMATCHED_LOCKED", 194000, "DRIVER_DECLINED")
    assert declined["driver_total"] == 131750 and declined["guarantee"] == 0


def test_all_service_and_cancellation_vectors() -> None:
    assert fixed_fare("BIKE_URBAN", 14, 35) == 81000
    assert fixed_fare("CAR_URBAN_PRIVATE", 14, 40) == 194000
    assert fixed_fare("CAR_INTERCITY_PRIVATE", 65, 95) == 637000
    assert seat_reference(637000) == 200000
    assert settlement("CAR_INTERCITY_POOL", 636000, "TOPUP_LOCKED")["driver_total"] == 540600
    assert cancellation("CAR_INTERCITY_POOL", 200000, 0, 10000, 36, True) == {
        "fee": 100000,
        "driver": 90000,
        "fund": 0,
        "platform": 10000,
    }
    assert cancellation("CAR_URBAN_POOL", 174000, 155000, 121, 0, False, has_coriders=True) == {
        "fee": 31000,
        "driver": 15500,
        "fund": 15500,
        "platform": 0,
    }


@settings(max_examples=10000, deadline=None)
@given(
    st.lists(
        st.tuples(st.integers(25000, 500000), st.integers(1, 2), st.integers(0, 30)),
        min_size=2,
        max_size=4,
    ),
    st.integers(0, 1000),
)
def test_exact_allocation_properties(samples: list[tuple[int, int, int]], mix: int) -> None:
    items = [
        FareInput(str(i), p, 40, seats=s, detour=d / 100) for i, (p, s, d) in enumerate(samples)
    ]
    floors = sum(bounds(i)[0] for i in items)
    caps = sum(bounds(i)[1] for i in items)
    target = floors + (caps - floors) * Fraction(mix, 1000)
    allocated = allocate(items, target)
    assert sum(allocated.values()) == target
    for item in items:
        low, high, _ = bounds(item)
        fare = allocated[item.id]
        assert low <= fare <= high
        charged = floor_money(fare)
        assert charged <= pool_quote(item.private)["quote"]
        split = settlement("CAR_URBAN_POOL", charged, "MATCHED_LOCKED")
        assert split["driver_base"] + split["platform"] + split["fund"] == charged
