"""Versioned HTTP surface, assembled from capability routers."""

from fastapi import APIRouter

from app.http.admin import router as admin_router
from app.http.driver import router as driver_router
from app.http.escrow import router as escrow_router
from app.http.identity import router as identity_router
from app.http.intercity import router as intercity_router
from app.http.locations import router as locations_router
from app.http.passenger import router as passenger_router
from app.http.safety import router as safety_router
from app.http.survey import router as survey_router
from app.http.system import router as system_router

router = APIRouter(prefix="/api")
router.include_router(identity_router)
router.include_router(system_router)
router.include_router(locations_router)
router.include_router(passenger_router)
router.include_router(driver_router)
router.include_router(intercity_router)
router.include_router(admin_router)
router.include_router(safety_router)
router.include_router(survey_router)
router.include_router(escrow_router)
