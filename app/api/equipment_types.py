"""Routes API : types / familles d'équipements."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.equipment_type import (
    EquipmentTypeCreate,
    EquipmentTypeRead,
    EquipmentTypeUpdate,
)
from app.services.equipment_type_service import EquipmentTypeService

router = APIRouter(prefix="/api/equipment-types", tags=["equipment-types"])


@router.get("", response_model=list[EquipmentTypeRead])
def list_equipment_types(
    active_only: bool = False,
    db: Session = Depends(get_db),
) -> list[EquipmentTypeRead]:
    service = EquipmentTypeService(db)
    return [
        EquipmentTypeRead.model_validate(service.enrich(item))
        for item in service.list(active_only)
    ]


@router.post("", response_model=EquipmentTypeRead, status_code=status.HTTP_201_CREATED)
def create_equipment_type(
    payload: EquipmentTypeCreate,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> EquipmentTypeRead:
    service = EquipmentTypeService(db)
    return EquipmentTypeRead.model_validate(service.create(payload, actor=actor))


@router.get("/{type_id}", response_model=EquipmentTypeRead)
def get_equipment_type(type_id: int, db: Session = Depends(get_db)) -> EquipmentTypeRead:
    service = EquipmentTypeService(db)
    return EquipmentTypeRead.model_validate(service.get(type_id))


@router.put("/{type_id}", response_model=EquipmentTypeRead)
def update_equipment_type(
    type_id: int,
    payload: EquipmentTypeUpdate,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> EquipmentTypeRead:
    service = EquipmentTypeService(db)
    equipment_type = service.get(type_id)
    return EquipmentTypeRead.model_validate(service.update(equipment_type, payload, actor=actor))


@router.delete("/{type_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_equipment_type(
    type_id: int,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    service = EquipmentTypeService(db)
    service.delete(service.get(type_id), actor=actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
