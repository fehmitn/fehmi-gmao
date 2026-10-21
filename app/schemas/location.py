"""Schemas des emplacements (arborescence par usine)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LocationTypeCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50, examples=["BAT"])
    label: str = Field(min_length=1, max_length=100, examples=["Bâtiment"])
    description: str | None = None
    sort_order: int = 0


class LocationTypeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    label: str
    description: str | None
    sort_order: int
    is_active: bool


class LocationCreate(BaseModel):
    site_id: int
    parent_id: int | None = None
    location_type_id: int
    code: str = Field(min_length=1, max_length=50, examples=["ATL-01"])
    name: str = Field(min_length=1, max_length=200, examples=["Atelier mécanique"])
    description: str | None = None
    is_active: bool = True


class LocationUpdate(BaseModel):
    parent_id: int | None = None
    location_type_id: int | None = None
    code: str | None = Field(default=None, min_length=1, max_length=50)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    is_active: bool | None = None


class LocationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    site_id: int
    parent_id: int | None
    location_type_id: int
    code: str
    name: str
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    path: str = ""
    depth: int = 1
    equipment_count: int = 0
    child_count: int = 0
    site_code: str | None = None
