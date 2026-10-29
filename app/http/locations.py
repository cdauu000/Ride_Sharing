from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field, field_validator

from app.geocoding import GeocoderBusy
from app.http.dependencies import Ctx
from app.route_preview import PreviewBusy
from app.schemas import Coordinate, InputModel
from app.security import authenticate

router = APIRouter()


class AddressSearch(InputModel):
    query: str = Field(min_length=3, max_length=250)

    @field_validator("query")
    @classmethod
    def normalize(cls, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < 3 or any(ord(char) < 32 for char in value):
            raise ValueError("Enter a complete address")
        return value


class AddressResult(Coordinate):
    id: str
    label: str = Field(min_length=1, max_length=500)
    kind: Literal["address", "street", "place"]
    source: str | None = None
    precision: Literal["reference"] | None = None


class AddressResults(InputModel):
    items: list[AddressResult]
    attribution: str = "© OpenStreetMap contributors · Photon"


def signed_in_id(request: Request, context: Ctx) -> str:
    # Release the authentication transaction before waiting for external HTTP.
    with context.db.transaction() as session:
        return authenticate(session, context, request.cookies.get("rise_access")).id


@router.post("/locations/search", response_model=AddressResults)
def search_address(
    payload: AddressSearch, context: Ctx, user_id: Annotated[str, Depends(signed_in_id)]
) -> dict:
    try:
        items = context.geocoding.search(payload.query, user_id)
        if any(item.get("source") for item in items):
            return {
                "items": items,
                "attribution": "Local supplementary place catalog; see each result's source",
            }
        return {"items": items}
    except GeocoderBusy as exc:
        raise HTTPException(
            status_code=429,
            detail={"code": exc.code},
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc


class RouteQuery(InputModel):
    pickup: Coordinate
    dropoff: Coordinate


class RoadGeometry(InputModel):
    type: Literal["LineString"]
    coordinates: list[tuple[float, float]]


class RoadWaypoint(InputModel):
    location: tuple[float, float]
    distance_m: float


class RoadResult(InputModel):
    distance_m: float
    duration_s: float
    geometry: RoadGeometry
    waypoints: list[RoadWaypoint]
    profile: Literal["car"]
    attribution: str


@router.post("/locations/route", response_model=RoadResult)
def road_route(
    payload: RouteQuery, context: Ctx, user_id: Annotated[str, Depends(signed_in_id)]
) -> dict:
    try:
        return context.road_preview.route(payload.pickup, payload.dropoff, user_id)
    except PreviewBusy as exc:
        raise HTTPException(
            status_code=429,
            detail={"code": exc.code},
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
