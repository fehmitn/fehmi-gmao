"""Schemas des utilisateurs et du journal d'audit."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import UserRole


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: str
    role: str
    is_active: bool


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    occurred_at: datetime
    actor_id: int | None
    actor_label: str
    action: str
    entity_type: str
    entity_id: int | None
    reason: str | None
    payload: dict | None
