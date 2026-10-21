"""Schemas des types / familles d'équipements."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Criticality


class EquipmentTypeCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50, examples=["PMP-CF"])
    name: str = Field(min_length=1, max_length=200, examples=["Pompe centrifuge"])
    category: str = Field(min_length=1, max_length=100, examples=["Pompes"])
    manufacturer: str | None = None
    model: str | None = None
    description: str | None = None
    criticality: Criticality | None = None
    technical_specs: dict[str, Any] | None = None
    is_active: bool = True


class EquipmentTypeUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=50)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    manufacturer: str | None = None
    model: str | None = None
    description: str | None = None
    criticality: Criticality | None = None
    technical_specs: dict[str, Any] | None = None
    is_active: bool | None = None


class EquipmentTypeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    category: str
    manufacturer: str | None
    model: str | None
    description: str | None
    criticality: str | None
    technical_specs: dict[str, Any] | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    equipment_count: int = 0
