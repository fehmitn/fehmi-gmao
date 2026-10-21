"""Routes API : équipements (inventaire) et leurs implantations."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.enums import EquipmentStatus
from app.models.user import User
from app.schemas.equipment import (
    EquipmentCreate,
    EquipmentRead,
    EquipmentUpdate,
    PlacementCreate,
    PlacementRead,
)
from app.services.equipment_service import EquipmentService
from app.services.placement_service import PlacementService

router = APIRouter(prefix="/api/equipments", tags=["equipments"])


@router.get("", response_model=list[EquipmentRead])
def list_equipments(
    site_id: int | None = None,
    location_id: int | None = None,
    include_descendants: bool = True,
    equipment_type_id: int | None = None,
    status_filter: EquipmentStatus | None = None,
    criticality: str | None = None,
    category: str | None = None,
    search: str | None = None,
    page: int = 1,
    size: int = 20,
    db: Session = Depends(get_db),
) -> list[EquipmentRead]:
    service = EquipmentService(db)
    result = service.list(
        site_id=site_id,
        location_id=location_id,
        include_descendants=include_descendants,
        equipment_type_id=equipment_type_id,
        status=status_filter.value if status_filter else None,
        criticality=criticality,
        category=category,
        search=search,
        page=page,
        size=size,
    )
    return [EquipmentRead.model_validate(item) for item in result.items]


@router.post("", response_model=EquipmentRead, status_code=status.HTTP_201_CREATED)
def create_equipment(
    payload: EquipmentCreate,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> EquipmentRead:
    service = EquipmentService(db)
    return EquipmentRead.model_validate(service.create(payload, actor=actor))


@router.get("/{equipment_id}", response_model=EquipmentRead)
def get_equipment(equipment_id: int, db: Session = Depends(get_db)) -> EquipmentRead:
    service = EquipmentService(db)
    return EquipmentRead.model_validate(service.get(equipment_id))


@router.put("/{equipment_id}", response_model=EquipmentRead)
def update_equipment(
    equipment_id: int,
    payload: EquipmentUpdate,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> EquipmentRead:
    service = EquipmentService(db)
    equipment = service.update(service.get(equipment_id), payload, actor=actor)
    return EquipmentRead.model_validate(equipment)


@router.delete("/{equipment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_equipment(
    equipment_id: int,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    service = EquipmentService(db)
    service.delete(service.get(equipment_id), actor=actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------- implantations
@router.get("/{equipment_id}/placements", response_model=list[PlacementRead])
def list_placements(
    equipment_id: int,
    db: Session = Depends(get_db),
) -> list[PlacementRead]:
    service = PlacementService(db)
    return [
        PlacementRead.model_validate(service.enrich(placement))
        for placement in service.history(equipment_id)
    ]


@router.post(
    "/{equipment_id}/placements",
    response_model=PlacementRead,
    status_code=status.HTTP_201_CREATED,
)
def create_placement(
    equipment_id: int,
    payload: PlacementCreate,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> PlacementRead:
    equipment_service = EquipmentService(db)
    equipment = equipment_service.get(equipment_id)
    service = PlacementService(db)
    placement = service.move(equipment, payload, actor=actor)
    return PlacementRead.model_validate(service.enrich(placement))
