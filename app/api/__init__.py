"""Routers de l'API REST."""

from app.api.audit import router as audit_router
from app.api.equipment import router as equipment_router
from app.api.equipment_types import router as equipment_types_router
from app.api.locations import router as locations_router
from app.api.sites import router as sites_router

__all__ = [
    "audit_router",
    "equipment_router",
    "equipment_types_router",
    "locations_router",
    "sites_router",
]
