"""Routers de l'API REST."""

from app.api.audit import router as audit_router
from app.api.equipment import router as equipment_router
from app.api.equipment_types import router as equipment_types_router
from app.api.interventions import router as interventions_router
from app.api.locations import router as locations_router
from app.api.maintenance_execution import router as maintenance_execution_router
from app.api.maintenance_schedule import router as maintenance_schedule_router
from app.api.maintenance_suppliers import router as maintenance_suppliers_router
from app.api.maintenance_tools import router as maintenance_tools_router
from app.api.periodic_maintenance import router as periodic_maintenance_router
from app.api.sites import router as sites_router
from app.api.spare_parts import router as spare_parts_router
from app.api.work_orders import router as work_orders_router

__all__ = [
    "audit_router",
    "equipment_router",
    "equipment_types_router",
    "interventions_router",
    "locations_router",
    "maintenance_execution_router",
    "maintenance_schedule_router",
    "maintenance_suppliers_router",
    "maintenance_tools_router",
    "periodic_maintenance_router",
    "sites_router",
    "spare_parts_router",
    "work_orders_router",
]
