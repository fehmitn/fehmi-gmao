"""Schemas des équipements et de leurs implantations."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Criticality, EquipmentStatus, MovementType


class EquipmentCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50, examples=["PMP-001"])
    name: str = Field(min_length=1, max_length=200, examples=["Pompe centrifuge P-12"])
    description: str | None = None
    equipment_type_id: int | None = None
    location_id: int = Field(description="Emplacement d'installation")
    status: EquipmentStatus = EquipmentStatus.OPERATIONAL
    criticality: Criticality | None = None
    manufacturer: str | None = None
    model: str | None = None
    serial_number: str | None = None
    purchase_date: date | None = None
    commissioning_date: date | None = None
    acquisition_cost: Decimal | None = None
    warranty_end_date: date | None = None
    is_critical: bool = False
    effective_from: date | None = Field(
        default=None,
        description="Date d'effet de l'implantation (aujourd'hui par défaut)",
    )
    derogation_reason: str | None = Field(
        default=None,
        description="Motif obligatoire si la date d'effet est antérieure à aujourd'hui",
    )


class EquipmentUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=50)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    equipment_type_id: int | None = None
    status: EquipmentStatus | None = None
    criticality: Criticality | None = None
    manufacturer: str | None = None
    model: str | None = None
    serial_number: str | None = None
    purchase_date: date | None = None
    commissioning_date: date | None = None
    acquisition_cost: Decimal | None = None
    warranty_end_date: date | None = None
    is_critical: bool | None = None
    is_active: bool | None = None


class EquipmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    description: str | None
    equipment_type_id: int | None
    site_id: int
    status: str
    criticality: str | None
    manufacturer: str | None
    model: str | None
    serial_number: str | None
    purchase_date: date | None
    commissioning_date: date | None
    acquisition_cost: Decimal | None
    warranty_end_date: date | None
    is_critical: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

    # Champs enrichis par le service
    site_code: str | None = None
    site_name: str | None = None
    equipment_type_code: str | None = None
    equipment_type_name: str | None = None
    current_location_id: int | None = None
    current_location_code: str | None = None
    current_location_name: str | None = None
    current_location_path: str | None = None
    installation_date: date | None = None


class PlacementCreate(BaseModel):
    """Demande de déplacement d'un équipement."""

    location_id: int
    effective_from: date | None = Field(
        default=None,
        description="Date d'effet du déplacement (aujourd'hui par défaut)",
    )
    movement_type: MovementType = MovementType.DEPLACEMENT
    reason: str | None = None
    derogation_reason: str | None = Field(
        default=None,
        description="Motif obligatoire si la date d'effet est antérieure à aujourd'hui",
    )


class PlacementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    equipment_id: int
    location_id: int
    effective_from: date
    effective_to: date | None
    movement_type: str
    reason: str | None
    recorded_at: datetime
    entry_delay_days: int | None
    derogation_reason: str | None
    created_by: int | None
    location_code: str | None = None
    location_name: str | None = None
    location_path: str | None = None
    is_current: bool = False
