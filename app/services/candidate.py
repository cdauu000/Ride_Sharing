from datetime import datetime
from math import cos, pi
from typing import Any

from shapely.geometry import Point as GeoPoint
from shapely.geometry import Polygon
from shapely.ops import nearest_points
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import baseline
from app.context import Context
from app.domain.pooling import insert
from app.domain.pricing import fixed_fare, floor_money, pool_quote
from app.domain.recommendation import baseline_score, diverse_top_k
from app.domain.trips import pickup_window
from app.domain.types import Point, Service
from app.models import Candidate, Driver, Plan, ScheduledTrip, TripRequest, User, uid
from app.routing import haversine
from app.services.pooling import plan_from_row, rider_from_request, serialize_result


def driver_available(
    session: Session, driver_id: str, start: float, end: float, ignore_plan: str | None = None
) -> bool:
    plans = session.scalars(
        select(Plan).where(
            Plan.driver_id == driver_id, Plan.status.not_in(["PLAN_COMPLETED", "PLAN_ABORTED"])
        )
    )
    for plan in plans:
        if plan.id == ignore_plan:
            continue
        if max(start, plan.data.get("busy_start", 0)) < min(
            end, plan.data.get("busy_end", float("inf"))
        ):
            return False
    trips = session.scalars(
        select(ScheduledTrip).where(
            ScheduledTrip.driver_id == driver_id,
            ScheduledTrip.status.not_in(
                ["COMPLETED", "CANCELLED_LOW_DEMAND", "MERGED", "CANCELLED_BY_DRIVER"]
            ),
        )
    )
    for trip in trips:
        if max(start, trip.departure_time - 1800) < min(
            end, trip.departure_time + (trip.data["direct_min"] * 2 + 60) * 60
        ):
            return False
    return True


def circle_boundary(anchor: Point, radius_km: float, coordinate: Point) -> Point:
    polygon = Polygon(
        [
            (
                anchor.lon + radius_km / 111.32 / cos(anchor.lat * pi / 180) * cos(i * 2 * pi / 64),
                anchor.lat + radius_km / 111.32 * __import__("math").sin(i * 2 * pi / 64),
            )
            for i in range(64)
        ]
    )
    point = GeoPoint(coordinate.lon, coordinate.lat)
    if polygon.covers(point):
        return coordinate
    nearest = nearest_points(polygon.boundary, point)[0]
    return Point(nearest.y, nearest.x)


def safe_candidate(row: Candidate) -> dict[str, Any]:
    hidden = {
        "physical_plan",
        "busy_start",
        "busy_end",
        "pickup_time",
        "boundary_pick",
        "boundary_drop",
        "features",
    }
    return {
        "id": row.id,
        "scheduled_trip_id": row.target_id
        if row.source_type == "SCHEDULED_INTERCITY_TRIP"
        else None,
        "ride_plan_id": row.target_id if row.source_type == "EXISTING_POOL_PLAN" else None,
        "service_code": row.service_code,
        "source_type": row.source_type,
        "source_plan_version": row.source_plan_version,
        "expires_at": datetime.fromtimestamp(
            row.expires_at, __import__("datetime").UTC
        ).isoformat(),
        **{k: v for k, v in row.data.items() if k not in hidden},
    }


def generate(session: Session, context: Context, request: TripRequest) -> dict[str, Any]:
    now, data, run_id = context.clock.now(), request.data, uid()
    pickup, dropoff = Point(**data["pickup"]), Point(**data["dropoff"])
    driver_query = select(Driver).where(
        Driver.online.is_(True),
        Driver.active.is_(True),
        Driver.lat.is_not(None),
        Driver.lon.is_not(None),
    )
    if session.bind.dialect.name == "postgresql" and data["booking_type"] == "NOW":
        driver_query = driver_query.where(
            text(
                "ST_DWithin(location_geom::geography, ST_SetSRID(ST_MakePoint(:pickup_lon,:pickup_lat),4326)::geography, 5000)"
            )
        )
        drivers = list(
            session.scalars(driver_query.params(pickup_lon=pickup.lon, pickup_lat=pickup.lat))
        )
    else:
        drivers = list(session.scalars(driver_query))
    drivers.sort(key=lambda d: (haversine(Point(d.lat, d.lon), pickup), d.id))
    drivers = drivers[:30]
    pool_plans = list(
        session.scalars(
            select(Plan)
            .where(
                Plan.service_code == Service.CAR_URBAN_POOL, Plan.status == "PLAN_OPEN_SEARCHING"
            )
            .order_by(Plan.id)
            .limit(18)
        )
    )
    if Service.CAR_URBAN_POOL not in request.allowed:
        pool_plans = []
    pure_plans = {plan.id: plan_from_row(session, context, plan) for plan in pool_plans}
    scheduled = list(
        session.scalars(
            select(ScheduledTrip)
            .where(
                ScheduledTrip.status == "OPEN_FOR_BOOKING",
                ScheduledTrip.departure_time >= now + 72 * 3600,
                ScheduledTrip.departure_time <= now + 168 * 3600,
            )
            .order_by(ScheduledTrip.departure_time)
            .limit(10)
        )
    )
    if Service.CAR_INTERCITY_POOL not in request.allowed:
        scheduled = []
    points = [pickup, dropoff] + [Point(d.lat, d.lon) for d in drivers]
    for plan in pure_plans.values():
        points.extend(
            [
                plan.current,
                *[s.point for s in plan.stops],
                *[r.pickup for r in plan.riders],
                *[r.dropoff for r in plan.riders],
            ]
        )
    boundaries = {}
    for trip in scheduled:
        origin, dest = Point(**trip.data["origin"]), Point(**trip.data["destination"])
        boundary_pick = circle_boundary(origin, trip.data["pickup_zone_radius_km"], pickup)
        boundary_drop = circle_boundary(dest, trip.data["dropoff_zone_radius_km"], dropoff)
        boundaries[trip.id] = (boundary_pick, boundary_drop)
        points.extend([origin, dest, boundary_pick, boundary_drop])
        from app.services.intercity import active_bookings

        for booking in active_bookings(session, trip.id):
            existing = session.get(TripRequest, booking.request_id)
            points.extend([Point(**existing.data["pickup"]), Point(**existing.data["dropoff"])])
    matrices = {}
    if any(service != Service.BIKE_URBAN for service in request.allowed):
        matrices["car"] = context.routing.matrix("car", points)
    if Service.BIKE_URBAN in request.allowed:
        matrices["motorbike"] = context.routing.matrix(
            "motorbike",
            [pickup, dropoff] + [Point(d.lat, d.lon) for d in drivers if d.vehicle_type == "BIKE"],
        )
    candidates: list[Candidate] = []
    rejected = dict(request.rejections)

    def add(
        service: str, target: str, source: str, version: int, driver: Driver, details: dict
    ) -> None:
        user = session.get(User, driver.id)
        details.update(
            driver_id=driver.id,
            driver_name=user.name.split()[-1],
            pricing_version=baseline()["pricing_version"],
            routing_mode=context.routing.mode,
        )
        item = {"id": uid(), "service_code": service, **details}
        item["score"] = baseline_score(item, data)
        details["score"] = item["score"]
        row = Candidate(
            id=item["id"],
            request_id=request.id,
            run_id=run_id,
            service_code=service,
            target_id=target,
            source_type=source,
            source_plan_version=version,
            pricing_version=baseline()["pricing_version"],
            expires_at=now + 120,
            data=details,
        )
        candidates.append(row)

    for service in request.allowed:
        earliest, latest, preferred = pickup_window(data, service, request.created_at)
        profile = "motorbike" if service == Service.BIKE_URBAN else "car"
        matrix = matrices[profile]
        direct = matrix.leg(pickup, dropoff)
        if service == Service.CAR_INTERCITY_POOL:
            for trip in scheduled:
                driver = session.get(Driver, trip.driver_id)
                if (
                    not driver.active
                    or driver.kyc_status != "VERIFIED"
                    or not driver.accepts_intercity
                ):
                    continue
                if trip.seats_total - trip.seats_booked < data["passenger_count"]:
                    continue
                if not earliest <= trip.departure_time <= latest:
                    continue
                boundary_pick, boundary_drop = boundaries[trip.id]
                extra_pick = matrix.leg(pickup, boundary_pick).km
                extra_drop = matrix.leg(boundary_drop, dropoff).km
                if max(extra_pick, extra_drop) > 10:
                    continue
                surcharge = floor_money(4000 * (extra_pick + extra_drop))
                price = trip.seat_price_vnd * data["passenger_count"] + surcharge
                if price > data["budget_max"]:
                    continue
                from app.services.intercity import optimize_order

                if optimize_order(session, context, trip, request, matrix=matrix) is None:
                    continue
                pickup_time = trip.departure_time
                max_minutes = data.get("max_in_vehicle_time_min") or direct.minutes * 1.5 + 10
                if direct.minutes > max_minutes or (
                    data.get("latest_arrival")
                    and pickup_time + direct.minutes * 60
                    > datetime.fromisoformat(data["latest_arrival"]).timestamp()
                ):
                    continue
                add(
                    service,
                    trip.id,
                    "SCHEDULED_INTERCITY_TRIP",
                    trip.plan_version,
                    driver,
                    {
                        "price": price,
                        "quote": price,
                        "unmatched": price,
                        "matched_estimate": price,
                        "expected_price": price,
                        "pickup_eta_min": max(0, (pickup_time - now) / 60),
                        "duration_min": direct.minutes,
                        "distance_km": direct.km,
                        "detour_ratio": 0,
                        "pickup_time": pickup_time,
                        "door_surcharge_vnd": surcharge,
                        "p_match_label": "Không áp dụng",
                        "p_fulfill_est": 0.95
                        if trip.seats_booked + data["passenger_count"] >= trip.min_seats_to_run
                        else 0.5,
                    },
                )
            continue
        price = fixed_fare(service, direct.km, direct.minutes)
        pool = pool_quote(price) if service == Service.CAR_URBAN_POOL else None
        cap = pool["unmatched"] if pool else price
        if cap > data["budget_max"]:
            rejected[service] = "BUDGET_EXCEEDED"
            continue
        if service == Service.CAR_URBAN_POOL:
            for plan in pool_plans:
                driver = session.get(Driver, plan.driver_id)
                if (
                    not driver.online
                    or not driver.active
                    or not driver.pool_enabled
                    or driver.kyc_status != "VERIFIED"
                ):
                    continue
                pure = pure_plans[plan.id]
                result = insert(pure, rider_from_request(request), matrix)
                if result is None:
                    continue
                physical = serialize_result(result)
                fare = result.fares[request.id]["charged"]
                pickup_time = result.pickup_times[request.id]
                add(
                    service,
                    plan.id,
                    "EXISTING_POOL_PLAN",
                    plan.plan_version,
                    driver,
                    {
                        "price": fare,
                        "quote": pool["quote"],
                        "unmatched": pool["unmatched"],
                        "matched_estimate": fare,
                        "expected_price": fare,
                        "p_match_est": 1.0,
                        "p_match_label": "Cao",
                        "pickup_eta_min": max(0, (pickup_time - now) / 60),
                        "duration_min": (result.dropoff_times[request.id] - pickup_time) / 60,
                        "distance_km": direct.km,
                        "detour_ratio": result.detours[request.id],
                        "pickup_time": pickup_time,
                        "physical_plan": physical,
                        "private_fare_vnd": price,
                    },
                )
        count = 0
        for driver in drivers:
            if driver.vehicle_type != ("BIKE" if service == Service.BIKE_URBAN else "CAR4"):
                continue
            if "INTERCITY" in service and (
                not driver.accepts_intercity or driver.kyc_status != "VERIFIED"
            ):
                continue
            if "URBAN" in service and not driver.accepts_urban:
                continue
            if pool and (not driver.pool_enabled or driver.kyc_status != "VERIFIED"):
                continue
            if (
                haversine(Point(driver.lat, driver.lon), pickup) > 5
                and data["booking_type"] == "NOW"
            ):
                continue
            approach = matrix.leg(Point(driver.lat, driver.lon), pickup)
            pickup_time = max(earliest, preferred, now + approach.minutes * 60)
            if pickup_time > latest:
                continue
            if (
                data.get("max_in_vehicle_time_min")
                and direct.minutes > data["max_in_vehicle_time_min"]
            ):
                continue
            if (
                data.get("latest_arrival")
                and pickup_time + direct.minutes * 60
                > datetime.fromisoformat(data["latest_arrival"]).timestamp()
            ):
                continue
            return_buffer = direct.minutes if "INTERCITY" in service else 0
            busy_start, busy_end = (
                pickup_time - 1800,
                pickup_time + (direct.minutes + return_buffer + 30) * 60,
            )
            if "INTERCITY" in service:
                busy_start = earliest - 1800
                busy_end = latest + (direct.minutes + return_buffer + 60) * 60
            if not driver_available(session, driver.id, busy_start, busy_end):
                continue
            pmatch = 0.5
            estimate = pool["matched_estimate"] if pool else price
            expected = round(pmatch * estimate + (1 - pmatch) * cap) if pool else price
            add(
                service,
                driver.id,
                "NEW_SINGLE_VEHICLE",
                0,
                driver,
                {
                    "price": estimate,
                    "quote": pool["quote"] if pool else price,
                    "unmatched": cap,
                    "matched_estimate": estimate,
                    "expected_price": expected,
                    "p_match_est": pmatch if pool else 0,
                    "p_match_label": "Trung bình" if pool else "Không áp dụng",
                    "p_match_source": "BETA_PRIOR" if pool else "NOT_APPLICABLE",
                    "pickup_eta_min": (pickup_time - now) / 60,
                    "duration_min": direct.minutes,
                    "distance_km": direct.km,
                    "detour_ratio": 0,
                    "pickup_time": pickup_time,
                    "busy_start": busy_start,
                    "busy_end": busy_end,
                    "private_fare_vnd": price,
                },
            )
            count += 1
            if count >= 15:
                break
    from app.services.features import observed_features

    feature_rows = observed_features(session, request, [safe_candidate(c) for c in candidates], now)
    if context.models and candidates:
        probabilities = context.models.match.predict(feature_rows)
        scores = context.models.scores(
            feature_rows, use_fulfillment=context.models.can_multiply_fulfillment
        )
        for candidate, probability, score in zip(candidates, probabilities, scores, strict=True):
            candidate.data = {
                **candidate.data,
                "score": float(score),
                "model_version": context.models.version,
            }
            if candidate.service_code == Service.CAR_URBAN_POOL:
                p = float(probability)
                candidate.data.update(
                    p_match_est=p,
                    p_match_source="CALIBRATED_MODEL"
                    if context.models.match.calibration_status == "VALIDATION_FITTED"
                    else "MODEL_REQUIRES_CALIBRATION_VALIDATION",
                    p_match_label="Cao" if p >= 0.65 else "Trung bình" if p >= 0.35 else "Thấp",
                    expected_price=round(
                        p * candidate.data["matched_estimate"]
                        + (1 - p) * candidate.data["unmatched"]
                    ),
                )
    for candidate, features in zip(candidates, feature_rows, strict=True):
        candidate.data = {**candidate.data, "features": features}
    # Store only snapshots actually exposed; hidden plan payload never leaves the server.
    visible = diverse_top_k([safe_candidate(c) for c in candidates])
    visible_ids = {item["id"] for item in visible}
    for candidate in candidates:
        if candidate.id in visible_ids:
            item = next(item for item in visible if item["id"] == candidate.id)
            candidate.data = {
                **candidate.data,
                **{
                    k: item[k]
                    for k in ("shown_position", "shown_reason", "exposure_propensity", "labels")
                },
            }
            session.add(candidate)
    for service in request.allowed:
        if not any(c.service_code == service for c in candidates):
            rejected.setdefault(service, "NO_FEASIBLE_SUPPLY")
    session.flush()
    return {"run_id": run_id, "items": visible, "rejection_reasons": rejected}
