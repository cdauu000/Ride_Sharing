from dataclasses import dataclass
from enum import StrEnum


class Service(StrEnum):
    BIKE_URBAN = "BIKE_URBAN"
    CAR_URBAN_PRIVATE = "CAR_URBAN_PRIVATE"
    CAR_URBAN_POOL = "CAR_URBAN_POOL"
    CAR_INTERCITY_PRIVATE = "CAR_INTERCITY_PRIVATE"
    CAR_INTERCITY_POOL = "CAR_INTERCITY_POOL"


@dataclass(frozen=True, order=True)
class Point:
    lat: float
    lon: float


@dataclass(frozen=True)
class Leg:
    km: float
    minutes: float
