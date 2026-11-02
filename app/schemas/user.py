"""Schemas de gestion des utilisateurs et de l'authentification."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import UserRole


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=50, examples=["jdupont"])
    display_name: str = Field(min_length=1, max_length=150, examples=["Jean Dupont"])
    role: UserRole = UserRole.TECHNICIEN
    password: str | None = Field(default=None, min_length=4, max_length=128)
    is_active: bool = True


class UserUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=1, max_length=50)
    display_name: str | None = Field(default=None, min_length=1, max_length=150)
    role: UserRole | None = None
    password: str | None = Field(default=None, min_length=4, max_length=128)
    is_active: bool | None = None


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: str
    role: str
    is_active: bool
    has_password: bool = False
    open_work_order_count: int = 0
    created_at: datetime
    updated_at: datetime


class LoginRequest(BaseModel):
    username: str
    password: str


class PasswordChange(BaseModel):
    current_password: str | None = None
    new_password: str = Field(min_length=4, max_length=128)


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="allow")

    id: int
    occurred_at: datetime
    actor_id: int | None = None
    actor_username: str | None = None
    action: str
    entity_type: str
    entity_id: int | None = None
    payload: dict | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    action_label: str | None = None
    entity_label: str | None = None
    payload_summary: str | None = None
    reason: str | None = None

