"""Schemas des ordres de travail."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import WorkOrderPriority, WorkOrderStatus


class WorkOrderCreate(BaseModel):
    equipment_id: int
    periodic_maintenance_id: int | None = None
    assigned_to_id: int | None = None
    priority: WorkOrderPriority = WorkOrderPriority.NORMAL
    due_date: date | None = None
    due_operating_hours: int | None = None
    description: str | None = None
    notes: str | None = None


class WorkOrderAssignment(BaseModel):
    assigned_to_id: int | None = None


class WorkOrderStatusUpdate(BaseModel):
    status: WorkOrderStatus


class WorkOrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    equipment_id: int
    equipment_code: str | None = None
    equipment_name: str | None = None
    periodic_maintenance_id: int | None
    operation_code: str | None = None
    operation_label: str | None = None
    assigned_to_id: int | None
    assigned_to_name: str | None = None
    created_by_id: int | None = None
    created_by_name: str | None = None
    is_corrective: bool = False
    kind_label: str | None = None
    status: str
    status_label: str
    priority: str
    priority_label: str
    due_date: date | None
    due_operating_hours: int | None
    description: str | None
    notes: str | None
    work_done: str | None = None
    started_at: date | None
    completed_at: date | None
    intervention_started_at: datetime | None = None
    intervention_ended_at: datetime | None = None
    intervention_duration_minutes: int | None = None
    intervention_duration_label: str | None = None
    created_at: datetime
    updated_at: datetime


class WorkOrderGenerationResult(BaseModel):
    created: int = 0
    skipped: int = 0
    work_orders: list[WorkOrderRead] = Field(default_factory=list)
