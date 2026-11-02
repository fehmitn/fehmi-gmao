"""Schemas des pièces de rechange et des mouvements de stock."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import StockMovementType


class SparePartCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50, examples=["PR-ROUL-6205"])
    name: str = Field(min_length=1, max_length=200, examples=["Roulement 6205 2RS"])
    description: str | None = None
    category: str | None = Field(default=None, max_length=100)
    unit: str = Field(default="pièce", max_length=30)
    manufacturer: str | None = None
    manufacturer_reference: str | None = None
    supplier_id: int | None = None
    site_id: int | None = None
    storage_location: str | None = None
    quantity: Decimal = Field(default=Decimal("0"), ge=0)
    min_quantity: Decimal = Field(default=Decimal("0"), ge=0)
    max_quantity: Decimal | None = Field(default=None, ge=0)
    unit_cost: Decimal | None = Field(default=None, ge=0)
    is_active: bool = True
    notes: str | None = None


class SparePartUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=50)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    category: str | None = Field(default=None, max_length=100)
    unit: str | None = Field(default=None, max_length=30)
    manufacturer: str | None = None
    manufacturer_reference: str | None = None
    supplier_id: int | None = None
    site_id: int | None = None
    storage_location: str | None = None
    min_quantity: Decimal | None = Field(default=None, ge=0)
    max_quantity: Decimal | None = Field(default=None, ge=0)
    unit_cost: Decimal | None = Field(default=None, ge=0)
    is_active: bool | None = None
    notes: str | None = None


class SparePartRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    description: str | None
    category: str | None
    unit: str
    manufacturer: str | None
    manufacturer_reference: str | None
    supplier_id: int | None
    site_id: int | None
    storage_location: str | None
    quantity: Decimal
    min_quantity: Decimal
    max_quantity: Decimal | None
    unit_cost: Decimal | None
    is_active: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime

    # Propriétés calculées / relations
    is_low_stock: bool = False
    is_out_of_stock: bool = False
    stock_status_label: str | None = None
    stock_status_css: str | None = None
    stock_value: Decimal | None = None
    supplier_name: str | None = None
    site_code: str | None = None
    movement_count: int = 0


class StockMovementCreate(BaseModel):
    movement_type: StockMovementType
    quantity: Decimal = Field(
        ge=0,
        description=(
            "Quantité du mouvement. Pour un inventaire, il s'agit de la "
            "quantité réellement comptée."
        ),
    )
    movement_date: date | None = None
    reference: str | None = Field(default=None, max_length=100)
    notes: str | None = None
    work_order_id: int | None = None


class StockMovementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    spare_part_id: int
    movement_type: str
    quantity: Decimal
    quantity_delta: Decimal
    resulting_quantity: Decimal
    movement_date: date
    reference: str | None
    notes: str | None
    work_order_id: int | None
    actor_id: int | None
    movement_type_label: str | None = None
    movement_type_css: str | None = None
    delta_label: str | None = None
    actor_name: str | None = None
    work_order_code: str | None = None
