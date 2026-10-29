from sqlalchemy import text
from sqlalchemy.orm import Session

from app.context import Context
from app.domain.trips import allowed_services
from app.domain.types import Point
from app.models import TripRequest, User
from app.schemas import TripIntent


def create_request(
    session: Session, context: Context, user: User, intent: TripIntent
) -> TripRequest:
    origin, dest = Point(**intent.pickup.model_dump()), Point(**intent.dropoff.model_dump())
    direct = context.routing.route("car", origin, dest)
    mode = context.areas.classify(origin, dest, direct.km)
    if session.bind.dialect.name == "postgresql":
        rows = session.execute(
            text("""SELECT kind,
            ST_Covers(geom,ST_SetSRID(ST_MakePoint(:plon,:plat),4326)) AS pickup_in,
            ST_Covers(geom,ST_SetSRID(ST_MakePoint(:dlon,:dlat),4326)) AS dropoff_in
            FROM service_areas"""),
            {"plat": origin.lat, "plon": origin.lon, "dlat": dest.lat, "dlon": dest.lon},
        ).all()
        areas = {row.kind: (row.pickup_in, row.dropoff_in) for row in rows}
        if "total" not in areas or not all(areas["total"]):
            from app.domain.errors import DomainError

            raise DomainError("OUT_OF_SERVICE_AREA", status=422)
    allowed, rejections = allowed_services(intent, mode, context.clock.now())
    data = intent.model_dump(mode="json")
    data["car_direct_km"], data["car_direct_min"] = direct.km, direct.minutes
    data["verified_gender"] = user.gender
    row = TripRequest(
        user_id=user.id,
        mode=mode,
        data=data,
        allowed=allowed,
        rejections=rejections,
        created_at=context.clock.now(),
    )
    session.add(row)
    session.flush()
    return row
