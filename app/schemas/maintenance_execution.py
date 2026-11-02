"""Schemas des réalisations d'ordres de travail de maintenance périodique."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class MaintenanceExecutionCreate(BaseModel):
    periodic_maintenance_id: int
    performed_on: date | None = Field(default=None, description="Date de réalisation de l'ordre de travail")
    performed_by_id: int | None = None
    notes: str | None = None
    operating_hours: int | None = Field(default=None, ge=0)


class MaintenanceExecutionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    equipment_id: int
    periodic_maintenance_id: int
    performed_on: date | None = None
    theoretical_due_date: date | None = None
    delay_days: int | None = None
    performed_by_id: int | None
    notes: str | None
    recorded_at: datetime
    operating_hours: int | None = None

    equipment_code: str | None = None
    equipment_name: str | None = None
    maintenance_code: str | None = None
    maintenance_label: str | None = None
    supplier_name: str | None = None
    performed_by_name: str | None = None
    delay_label: str | None = None
    delay_css: str | None = None
