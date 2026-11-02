"""Schemas de l'échéancier de maintenance périodique."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class MaintenanceScheduleRow(BaseModel):
    equipment_id: int
    equipment_code: str
    equipment_name: str
    site_id: int
    site_code: str | None
    site_name: str | None
    location_code: str | None
    location_name: str | None

    equipment_type_id: int
    equipment_type_code: str | None
    equipment_type_name: str | None

    periodic_maintenance_id: int
    operation_code: str
    operation_label: str
    periodicity_label: str
    maintenance_type_label: str
    tolerance_days: int
    estimated_duration_minutes: int | None

    supplier_id: int | None
    supplier_name: str | None

    anchor_date: date | None
    previous_due_date: date | None
    next_due_date: date | None
    due_date: date | None
    days_remaining: int | None
    status: str
    status_label: str
    status_css: str

    last_performed_on: date | None = None
    last_delay_days: int | None = None
    last_delay_label: str | None = None
    is_hour_based: bool = False
    current_operating_hours: int | None = None
    due_operating_hours: int | None = None
    hours_remaining: int | None = None
    last_performed_hours: int | None = None


class MaintenanceScheduleSummary(BaseModel):
    total: int = 0
    overdue_count: int = 0
    due_soon_count: int = 0
    no_anchor_count: int = 0
    late_execution_count: int = 0
    hours_based_count: int = 0
    hours_waiting_count: int = 0
    hours_no_reading_count: int = 0
    rows: list[MaintenanceScheduleRow] = []
