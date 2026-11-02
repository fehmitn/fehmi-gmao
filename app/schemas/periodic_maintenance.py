"""Schemas des maintenances périodiques rattachées aux familles d'équipements."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import MaintenanceAnchor, MaintenanceIntervalUnit, MaintenanceType


class PeriodicMaintenanceCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50, examples=["PMP-GRAISSAGE"])
    label: str = Field(min_length=1, max_length=200, examples=["Graissage des paliers"])
    description: str | None = None
    interval_value: int = Field(ge=1, le=10000, examples=[3])
    interval_unit: MaintenanceIntervalUnit = MaintenanceIntervalUnit.MONTHS
    maintenance_type: MaintenanceType = MaintenanceType.PREVENTIVE_SYSTEMATIC
    anchor: MaintenanceAnchor = MaintenanceAnchor.COMMISSIONING
    fixed_date: date | None = Field(
        default=None,
        description="Première échéance, obligatoire si anchor = fixed_date",
    )
    supplier_id: int | None = None
    tolerance_days: int = Field(default=0, ge=0, le=3650)
    estimated_duration_minutes: int | None = Field(default=None, ge=0, le=100000)
    sort_order: int = 0
    is_active: bool = True


class PeriodicMaintenanceUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=50)
    label: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    interval_value: int | None = Field(default=None, ge=1, le=10000)
    interval_unit: MaintenanceIntervalUnit | None = None
    maintenance_type: MaintenanceType | None = None
    anchor: MaintenanceAnchor | None = None
    fixed_date: date | None = None
    supplier_id: int | None = None
    tolerance_days: int | None = Field(default=None, ge=0, le=3650)
    estimated_duration_minutes: int | None = Field(default=None, ge=0, le=100000)
    sort_order: int | None = None
    is_active: bool | None = None


class PeriodicMaintenanceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    equipment_type_id: int
    supplier_id: int | None
    code: str
    label: str
    description: str | None
    interval_value: int
    interval_unit: str
    maintenance_type: str
    anchor: str
    fixed_date: date | None
    tolerance_days: int
    estimated_duration_minutes: int | None
    sort_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    equipment_type_code: str | None = None
    equipment_type_name: str | None = None
    supplier_code: str | None = None
    supplier_name: str | None = None
    interval_unit_label: str | None = None
    maintenance_type_label: str | None = None
    anchor_label: str | None = None
    periodicity_label: str | None = None
    execution_count: int = 0
