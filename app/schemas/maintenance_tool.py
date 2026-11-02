"""Schemas des équipements de maintenance, étalonnages et utilisations."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    CalibrationResult,
    MaintenanceIntervalUnit,
    ToolStatus,
)


class MaintenanceToolCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50, examples=["OUT-PIED-01"])
    name: str = Field(
        min_length=1, max_length=200, examples=["Pied à coulisse numérique"]
    )
    description: str | None = None
    category: str | None = Field(default="Instrument de mesure", max_length=100)
    manufacturer: str | None = None
    model: str | None = None
    serial_number: str | None = None
    site_id: int | None = None
    storage_location: str | None = None
    status: ToolStatus = ToolStatus.AVAILABLE
    requires_calibration: bool = False
    calibration_interval_value: int | None = Field(default=None, ge=1)
    calibration_interval_unit: MaintenanceIntervalUnit = MaintenanceIntervalUnit.MONTHS
    last_calibration_date: date | None = None
    next_calibration_date: date | None = None
    calibration_provider_id: int | None = None
    legal_reference: str | None = None
    purchase_date: date | None = None
    commissioning_date: date | None = None
    is_active: bool = True
    notes: str | None = None


class MaintenanceToolUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=50)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    category: str | None = Field(default=None, max_length=100)
    manufacturer: str | None = None
    model: str | None = None
    serial_number: str | None = None
    site_id: int | None = None
    storage_location: str | None = None
    status: ToolStatus | None = None
    requires_calibration: bool | None = None
    calibration_interval_value: int | None = Field(default=None, ge=1)
    calibration_interval_unit: MaintenanceIntervalUnit | None = None
    last_calibration_date: date | None = None
    next_calibration_date: date | None = None
    calibration_provider_id: int | None = None
    legal_reference: str | None = None
    purchase_date: date | None = None
    commissioning_date: date | None = None
    is_active: bool | None = None
    notes: str | None = None


class MaintenanceToolRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    description: str | None
    category: str | None
    manufacturer: str | None
    model: str | None
    serial_number: str | None
    site_id: int | None
    storage_location: str | None
    status: str
    requires_calibration: bool
    calibration_interval_value: int | None
    calibration_interval_unit: str
    last_calibration_date: date | None
    next_calibration_date: date | None
    calibration_provider_id: int | None
    legal_reference: str | None
    purchase_date: date | None
    commissioning_date: date | None
    is_active: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime

    status_label: str | None = None
    status_css: str | None = None
    calibration_periodicity_label: str | None = None
    calibration_days_remaining: int | None = None
    calibration_status: str | None = None
    calibration_status_label: str | None = None
    calibration_status_css: str | None = None
    calibration_blocked: bool = False
    checkout_block_reason: str | None = None
    provider_name: str | None = None
    site_code: str | None = None


class CalibrationCreate(BaseModel):
    calibrated_on: date
    next_due_date: date | None = None
    provider_id: int | None = None
    certificate_number: str | None = Field(default=None, max_length=100)
    result: CalibrationResult = CalibrationResult.PASSED
    cost: Decimal | None = Field(default=None, ge=0)
    notes: str | None = None


class CalibrationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tool_id: int
    calibrated_on: date
    next_due_date: date | None
    provider_id: int | None
    certificate_number: str | None
    result: str
    cost: Decimal | None
    notes: str | None
    actor_id: int | None
    recorded_at: datetime
    result_label: str | None = None
    result_css: str | None = None
    provider_name: str | None = None
    actor_name: str | None = None


class ToolUsageCreate(BaseModel):
    work_order_id: int | None = None
    used_by_id: int | None = None
    started_on: date | None = None
    notes: str | None = None


class ToolUsageReturn(BaseModel):
    ended_on: date | None = None
    return_notes: str | None = None


class ToolUsageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tool_id: int
    work_order_id: int | None
    used_by_id: int | None
    started_on: date
    ended_on: date | None
    notes: str | None
    return_notes: str | None
    created_at: datetime
    updated_at: datetime
    is_open: bool = False
    duration_days: int | None = None
    used_by_name: str | None = None
    work_order_code: str | None = None


class ToolStatusUpdate(BaseModel):
    status: ToolStatus
