"""Schemas des usines / sites."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SiteCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50, examples=["USN-01"])
    name: str = Field(min_length=1, max_length=200, examples=["Usine de Casablanca"])
    description: str | None = None
    address: str | None = None
    city: str | None = None
    country: str | None = None
    timezone: str | None = None
    is_active: bool = True


class SiteUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=50)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    address: str | None = None
    city: str | None = None
    country: str | None = None
    timezone: str | None = None
    is_active: bool | None = None


class SiteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    description: str | None
    address: str | None
    city: str | None
    country: str | None
    timezone: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    location_count: int = 0
    equipment_count: int = 0
