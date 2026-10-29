from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Coordinate(InputModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class Register(InputModel):
    email: str = Field(min_length=5, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=12, max_length=128)
    role: Literal["PASSENGER", "DRIVER"] = "PASSENGER"
    vehicle_type: Literal["BIKE", "CAR4"] = "CAR4"


class Login(InputModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)


class TripIntent(InputModel):
    pickup: Coordinate
    dropoff: Coordinate
    pickup_label: str | None = Field(default=None, min_length=1, max_length=500)
    dropoff_label: str | None = Field(default=None, min_length=1, max_length=500)
    vehicle_preference: Literal["ANY", "BIKE", "CAR"] = "ANY"
    ride_preference: Literal["ANY", "PRIVATE", "POOL"] = "ANY"
    booking_type: Literal["NOW", "SCHEDULED"] = "NOW"
    passenger_count: int = Field(default=1, ge=1, le=4)
    has_luggage: bool = False
    budget_min: int = Field(default=100000, ge=0, le=100000000)
    budget_max: int = Field(default=1000000, gt=0, le=100000000)
    preferred_departure: datetime | None = None
    earliest_departure: datetime | None = None
    latest_departure: datetime | None = None
    latest_arrival: datetime | None = None
    max_passenger_detour_ratio: float = Field(default=0.3, ge=0, le=1)
    max_in_vehicle_time_min: float | None = Field(default=None, gt=0, le=1440)
    max_walk_m: int = Field(default=0, ge=0, le=500)
    is_raining: bool = False
    same_gender_coride: bool = False

    @field_validator(
        "preferred_departure", "earliest_departure", "latest_departure", "latest_arrival"
    )
    @classmethod
    def aware_datetime(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("Timezone offset is required")
        return value

    @model_validator(mode="after")
    def coherent(self) -> "TripIntent":
        if self.budget_min > self.budget_max:
            raise ValueError("budget_min must not exceed budget_max")
        if self.pickup == self.dropoff:
            raise ValueError("Origin and destination must differ")
        if self.booking_type == "SCHEDULED" and any(
            value is None
            for value in (self.preferred_departure, self.earliest_departure, self.latest_departure)
        ):
            raise ValueError("Scheduled requests require all three departure timestamps")
        if self.earliest_departure and self.latest_departure:
            if (
                not self.earliest_departure
                <= (self.preferred_departure or self.earliest_departure)
                <= self.latest_departure
            ):
                raise ValueError("earliest <= preferred <= latest is required")
        return self


class DriverSettings(InputModel):
    online: bool = True
    accepts_urban: bool = True
    pool_enabled: bool = False
    accepts_intercity: bool = False
    max_additional_pickups: int = Field(default=3, ge=0, le=3)
    max_driver_detour_km: float = Field(default=10, ge=0, le=50)
    max_driver_detour_min: float = Field(default=30, ge=0, le=120)


class SelectCandidate(InputModel):
    candidate_id: str = Field(min_length=1, max_length=64)


class PublishTrip(InputModel):
    corridor_id: str = Field(min_length=2, max_length=100)
    origin: Coordinate
    destination: Coordinate
    departure_time: datetime
    departure_flex_min: int = Field(default=30, ge=0, le=120)
    min_seats_to_run: Literal[2, 3] = 3
    seat_price_vnd: int | None = Field(default=None, gt=0)
    pickup_zone_radius_km: float = Field(default=2, gt=0, le=5)
    dropoff_zone_radius_km: float = Field(default=2, gt=0, le=5)

    @field_validator("departure_time")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Timezone offset is required")
        return value


class Decision(InputModel):
    decision: Literal["RUN", "CANCEL"]


class TopupResponse(InputModel):
    decision: Literal["ACCEPT", "DECLINE"]


class Reason(InputModel):
    reason_code: str = Field(default="USER_REQUEST", min_length=1, max_length=80)


class DisputeAllocation(InputModel):
    passenger_vnd: int = Field(ge=0)
    driver_vnd: int = Field(ge=0)
    platform_vnd: int = Field(ge=0)


class Arrival(InputModel):
    booking_id: str = Field(min_length=1, max_length=36)


class KycReview(InputModel):
    status: Literal["VERIFIED", "REJECTED"]
    verified_gender: Literal["MALE", "FEMALE", "OTHER", "UNKNOWN"] = "UNKNOWN"


class Rating(InputModel):
    score: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=1000)


class UserView(BaseModel):
    id: str
    email: str
    name: str
    role: str


class DisplayPoint(Coordinate):
    label: str


class BookingView(BaseModel):
    id: str
    request_id: str
    service_code: str
    ride_status: str
    price_status: str
    escrow_status: str
    driver_id: str | None
    ride_plan_id: str | None
    scheduled_trip_id: str | None
    seat_count: int
    quoted_price_cap_vnd: int
    pool_quote_price_vnd: int
    current_estimated_price_vnd: int
    final_price_vnd: int | None
    cancellation_fee_vnd: int
    unmatched_cause: str
    offer_id: str | None = None
    pickup: DisplayPoint | None = None
    dropoff: DisplayPoint | None = None
