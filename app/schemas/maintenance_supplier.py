"""Schemas du référentiel des fournisseurs de maintenance."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class MaintenanceSupplierCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50, examples=["SUP-HYDRO"])
    name: str = Field(min_length=1, max_length=200, examples=["Hydro Prestations"])
    contact_name: str | None = None
    phone: str | None = None
    email: str | None = None
    specialty: str | None = None
    notes: str | None = None
    is_active: bool = True


class MaintenanceSupplierUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=50)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    contact_name: str | None = None
    phone: str | None = None
    email: str | None = None
    specialty: str | None = None
    notes: str | None = None
    is_active: bool | None = None


class MaintenanceSupplierRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    contact_name: str | None
    phone: str | None
    email: str | None
    specialty: str | None
    notes: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    periodic_maintenance_count: int = 0
