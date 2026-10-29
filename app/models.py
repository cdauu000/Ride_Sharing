"""Persistence schema. Monetary integer columns are VND; exact allocations are rationals."""

from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def uid() -> str:
    return str(uuid4())


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(16))
    gender: Mapped[str] = mapped_column(String(16), default="UNKNOWN")
    created_at: Mapped[float] = mapped_column(Float)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    refresh_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[float] = mapped_column(Float)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class Driver(Base):
    __tablename__ = "driver_profiles"
    id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    vehicle_type: Mapped[str] = mapped_column(String(8))
    license_plate: Mapped[str] = mapped_column(String(50), unique=True)
    capacity: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    online: Mapped[bool] = mapped_column(Boolean, default=False)
    kyc_status: Mapped[str] = mapped_column(String(16), default="NONE")
    accepts_urban: Mapped[bool] = mapped_column(Boolean, default=True)
    pool_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    accepts_intercity: Mapped[bool] = mapped_column(Boolean, default=False)
    max_additional_pickups: Mapped[int] = mapped_column(Integer, default=3)
    max_driver_detour_km: Mapped[float] = mapped_column(Float, default=10)
    max_driver_detour_min: Mapped[float] = mapped_column(Float, default=30)
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    location_at: Mapped[float | None] = mapped_column(Float)
    __table_args__ = (
        CheckConstraint(
            "(vehicle_type = 'BIKE' AND capacity = 1) OR (vehicle_type = 'CAR4' AND capacity = 4)",
            name="vehicle_capacity",
        ),
    )


class TripRequest(Base):
    __tablename__ = "trip_requests"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    mode: Mapped[str] = mapped_column(String(16))
    data: Mapped[dict[str, Any]] = mapped_column(JSON)
    allowed: Mapped[list[str]] = mapped_column(JSON)
    rejections: Mapped[dict[str, str]] = mapped_column(JSON)
    created_at: Mapped[float] = mapped_column(Float)


class PricingConfig(Base):
    __tablename__ = "pricing_configs"
    version: Mapped[str] = mapped_column(String(100), primary_key=True)
    params: Mapped[dict[str, Any]] = mapped_column(JSON)
    digest: Mapped[str] = mapped_column(String(64))


class Plan(Base):
    __tablename__ = "ride_plans"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    driver_id: Mapped[str] = mapped_column(ForeignKey("driver_profiles.id"), index=True)
    service_code: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="PLAN_CREATED", index=True)
    plan_version: Mapped[int] = mapped_column(Integer, default=1)
    pricing_version: Mapped[str] = mapped_column(ForeignKey("pricing_configs.version"))
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ScheduledTrip(Base):
    __tablename__ = "scheduled_trips"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    driver_id: Mapped[str] = mapped_column(ForeignKey("driver_profiles.id"), index=True)
    corridor_id: Mapped[str] = mapped_column(String(100), index=True)
    departure_time: Mapped[float] = mapped_column(Float, index=True)
    seats_total: Mapped[int] = mapped_column(Integer, default=4)
    seats_booked: Mapped[int] = mapped_column(Integer, default=0)
    min_seats_ref: Mapped[int] = mapped_column(Integer, default=3)
    min_seats_to_run: Mapped[int] = mapped_column(Integer, default=3)
    seat_reference_vnd: Mapped[int] = mapped_column(BigInteger)
    seat_price_vnd: Mapped[int] = mapped_column(BigInteger)
    plan_version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(40), default="OPEN_FOR_BOOKING", index=True)
    pricing_version: Mapped[str] = mapped_column(ForeignKey("pricing_configs.version"))
    data: Mapped[dict[str, Any]] = mapped_column(JSON)
    __table_args__ = (
        CheckConstraint(
            "seats_booked >= 0 AND seats_booked <= seats_total AND seats_total <= 4",
            name="seats_bounds",
        ),
        CheckConstraint("min_seats_to_run IN (2,3) AND min_seats_ref = 3", name="threshold_bounds"),
        CheckConstraint(
            "seat_price_vnd * 10 >= seat_reference_vnd * 9 AND seat_price_vnd * 10 <= seat_reference_vnd * 11",
            name="seat_price_band",
        ),
    )


class Candidate(Base):
    __tablename__ = "ride_candidates"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    request_id: Mapped[str] = mapped_column(ForeignKey("trip_requests.id"), index=True)
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    service_code: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[str] = mapped_column(String(36))
    source_type: Mapped[str] = mapped_column(String(32))
    source_plan_version: Mapped[int] = mapped_column(Integer)
    pricing_version: Mapped[str] = mapped_column(ForeignKey("pricing_configs.version"))
    expires_at: Mapped[float] = mapped_column(Float)
    data: Mapped[dict[str, Any]] = mapped_column(JSON)


class Booking(Base):
    __tablename__ = "bookings"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    request_id: Mapped[str] = mapped_column(ForeignKey("trip_requests.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    driver_id: Mapped[str | None] = mapped_column(ForeignKey("driver_profiles.id"), index=True)
    service_code: Mapped[str] = mapped_column(String(32))
    ride_plan_id: Mapped[str | None] = mapped_column(ForeignKey("ride_plans.id"), index=True)
    scheduled_trip_id: Mapped[str | None] = mapped_column(
        ForeignKey("scheduled_trips.id"), index=True
    )
    pricing_version: Mapped[str] = mapped_column(ForeignKey("pricing_configs.version"))
    ride_status: Mapped[str] = mapped_column(String(32), default="HELD")
    price_status: Mapped[str] = mapped_column(String(32), default="QUOTED")
    escrow_status: Mapped[str] = mapped_column(String(32), default="NONE")
    seat_count: Mapped[int] = mapped_column(Integer)
    pool_quote_price_vnd: Mapped[int] = mapped_column(BigInteger, default=0)
    quoted_price_cap_vnd: Mapped[int] = mapped_column(BigInteger)
    current_estimated_price_vnd: Mapped[int] = mapped_column(BigInteger)
    final_price_vnd: Mapped[int | None] = mapped_column(BigInteger)
    cancellation_fee_vnd: Mapped[int] = mapped_column(BigInteger, default=0)
    unmatched_cause: Mapped[str] = mapped_column(String(32), default="NO_COMPATIBLE")
    created_at: Mapped[float] = mapped_column(Float)
    confirmed_at: Mapped[float | None] = mapped_column(Float)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    __table_args__ = (
        CheckConstraint("seat_count BETWEEN 1 AND 4", name="booking_seats"),
        CheckConstraint(
            "final_price_vnd IS NULL OR final_price_vnd <= quoted_price_cap_vnd OR price_status = 'TOPUP_LOCKED'",
            name="final_price_cap",
        ),
        CheckConstraint(
            "quoted_price_cap_vnd >= 0 AND (final_price_vnd IS NULL OR final_price_vnd >= 0)",
            name="nonnegative_prices",
        ),
        Index(
            "active_booking_per_request",
            "request_id",
            unique=True,
            sqlite_where=text("ride_status IN ('HELD','CONFIRMED','RIDE_STARTED')"),
            postgresql_where=text("ride_status IN ('HELD','CONFIRMED','RIDE_STARTED')"),
        ),
    )


class Offer(Base):
    __tablename__ = "offers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    booking_id: Mapped[str] = mapped_column(ForeignKey("bookings.id"), index=True)
    driver_id: Mapped[str] = mapped_column(ForeignKey("driver_profiles.id"), index=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("ride_plans.id"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="PENDING")
    expires_at: Mapped[float] = mapped_column(Float)
    hold_expires_at: Mapped[float] = mapped_column(Float)
    held_version: Mapped[int] = mapped_column(Integer)
    attempt: Mapped[int] = mapped_column(Integer)


class SeatHold(Base):
    __tablename__ = "seat_holds"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    request_id: Mapped[str] = mapped_column(ForeignKey("trip_requests.id"))
    offer_id: Mapped[str] = mapped_column(ForeignKey("offers.id"), unique=True)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE")
    expires_at: Mapped[float] = mapped_column(Float)
    __table_args__ = (
        Index(
            "active_hold_per_request",
            "request_id",
            unique=True,
            sqlite_where=text("status = 'ACTIVE'"),
            postgresql_where=text("status = 'ACTIVE'"),
        ),
    )


class Idempotency(Base):
    __tablename__ = "idempotency_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    key: Mapped[str] = mapped_column(String(128))
    payload_hash: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict[str, Any]] = mapped_column(JSON)
    expires_at: Mapped[float] = mapped_column(Float)
    __table_args__ = (UniqueConstraint("user_id", "key"),)


class Job(Base):
    __tablename__ = "scheduled_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    job_type: Mapped[str] = mapped_column(String(40))
    target_id: Mapped[str] = mapped_column(String(36))
    run_at: Mapped[float] = mapped_column(Float, index=True)
    status: Mapped[str] = mapped_column(String(24), default="PENDING", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    last_error: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class FundAccount(Base):
    __tablename__ = "fund_account"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    balance_vnd: Mapped[int] = mapped_column(BigInteger)
    __table_args__ = (CheckConstraint("balance_vnd >= 0", name="fund_nonnegative"),)


class FundEntry(Base):
    __tablename__ = "fund_ledger"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    booking_id: Mapped[str | None] = mapped_column(ForeignKey("bookings.id"), index=True)
    entry_type: Mapped[str] = mapped_column(String(24))
    operation_id: Mapped[str] = mapped_column(String(160), unique=True)
    amount_signed_vnd: Mapped[int] = mapped_column(BigInteger)
    balance_after_vnd: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[float] = mapped_column(Float)


class Payout(Base):
    __tablename__ = "driver_payouts"
    booking_id: Mapped[str] = mapped_column(ForeignKey("bookings.id"), primary_key=True)
    driver_id: Mapped[str] = mapped_column(ForeignKey("driver_profiles.id"), index=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON)


class Event(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    target_id: Mapped[str] = mapped_column(String(36), index=True)
    kind: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[float] = mapped_column(Float)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Auxiliary(Base):
    __tablename__ = "auxiliary_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    target_id: Mapped[str | None] = mapped_column(String(36), index=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[float] = mapped_column(Float)
    __table_args__ = (
        Index(
            "one_survey_per_respondent",
            "target_id",
            unique=True,
            sqlite_where=text("kind = 'SURVEY'"),
            postgresql_where=text("kind = 'SURVEY'"),
        ),
    )
