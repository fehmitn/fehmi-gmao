"""Schemas du projet GMAO."""

from app.schemas.dashboard import DashboardStats, SiteSummary
from app.schemas.equipment import (
    EquipmentCreate,
    EquipmentRead,
    EquipmentUpdate,
    PlacementCreate,
    PlacementRead,
)
from app.schemas.equipment_type import (
    EquipmentTypeCreate,
    EquipmentTypeRead,
    EquipmentTypeUpdate,
)
from app.schemas.location import (
    LocationCreate,
    LocationRead,
    LocationTypeCreate,
    LocationTypeRead,
    LocationUpdate,
)
from app.schemas.site import SiteCreate, SiteRead, SiteUpdate
from app.schemas.user import AuditLogRead, UserRead

__all__ = [
    "AuditLogRead",
    "DashboardStats",
    "EquipmentCreate",
    "EquipmentRead",
    "EquipmentTypeCreate",
    "EquipmentTypeRead",
    "EquipmentTypeUpdate",
    "EquipmentUpdate",
    "LocationCreate",
    "LocationRead",
    "LocationTypeCreate",
    "LocationTypeRead",
    "LocationUpdate",
    "PlacementCreate",
    "PlacementRead",
    "SiteCreate",
    "SiteRead",
    "SiteSummary",
    "SiteUpdate",
    "UserRead",
]
