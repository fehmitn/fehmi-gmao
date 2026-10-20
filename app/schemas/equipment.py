from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.equipment import EquipmentStatus


class EquipmentCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50, examples=["EQ-001"])
    name: str = Field(min_length=1, max_length=200, examples=["Pompe centrifuge P-12"])
    description: str | None = None
    category: str = Field(min_length=1, max_length=100, examples=["Pompe"])
    location: str = Field(min_length=1, max_length=200, examples=["Atelier A / Ligne 2"])
    manufacturer: str | None = None
    serial_number: str | None = None
    status: EquipmentStatus = EquipmentStatus.OPERATIONAL


class EquipmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    description: str | None
    category: str
    location: str
    manufacturer: str | None
    serial_number: str | None
    status: str
    created_at: datetime
    updated_at: datetime
