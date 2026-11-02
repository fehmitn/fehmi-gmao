"""Schemas de la maintenance corrective."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import WorkOrderPriority
from app.schemas.work_order import WorkOrderRead


class InterventionRequestCreate(BaseModel):
    equipment_id: int
    description: str = Field(
        min_length=3,
        max_length=2000,
        description="Symptôme constaté ou nature de la panne.",
    )
    priority: WorkOrderPriority = WorkOrderPriority.NORMAL
    due_date: date | None = None
    notes: str | None = None


class InterventionAssignment(BaseModel):
    assigned_to_id: int | None = None


class InterventionStart(BaseModel):
    started_at: datetime | None = None
    notes: str | None = None


class InterventionFinish(BaseModel):
    ended_at: datetime | None = None
    work_done: str = Field(min_length=3, description="Compte rendu de l'intervention.")
    notes: str | None = None


class InterventionCancel(BaseModel):
    reason: str | None = None


class InterventionPartCreate(BaseModel):
    spare_part_id: int
    quantity: Decimal = Field(gt=0)
    notes: str | None = None


class InterventionPartUse(BaseModel):
    quantity: Decimal | None = Field(default=None, gt=0)
    notes: str | None = None


class InterventionPartRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    work_order_id: int
    spare_part_id: int
    requested_quantity: Decimal
    used_quantity: Decimal | None
    status: str
    status_label: str
    status_css: str
    notes: str | None
    requested_by_id: int | None
    requested_by_name: str | None = None
    used_by_id: int | None
    used_by_name: str | None = None
    requested_at: datetime
    used_at: datetime | None
    spare_part_code: str | None = None
    spare_part_name: str | None = None
    unit: str | None = None
    available_quantity: Decimal | None = None
    quantity_label: str | None = None


class InterventionRead(WorkOrderRead):
    intervention_parts: list[InterventionPartRead] = Field(default_factory=list)
