"""Routes API : pièces de rechange et mouvements de stock."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.spare_part import (
    SparePartCreate,
    SparePartRead,
    SparePartUpdate,
    StockMovementCreate,
    StockMovementRead,
)
from app.services.spare_part_service import SparePartService

router = APIRouter(prefix="/api/spare-parts", tags=["spare-parts"])


@router.get("", response_model=list[SparePartRead])
def list_spare_parts(
    search: str | None = None,
    category: str | None = None,
    low_stock_only: bool = False,
    active_only: bool = False,
    db: Session = Depends(get_db),
) -> list[SparePartRead]:
    service = SparePartService(db)
    return [
        SparePartRead.model_validate(item)
        for item in service.list(
            search=search,
            category=category,
            low_stock_only=low_stock_only,
            active_only=active_only,
        )
    ]


@router.get("/summary")
def spare_parts_summary(db: Session = Depends(get_db)) -> dict[str, object]:
    return SparePartService(db).summary()


@router.post("", response_model=SparePartRead, status_code=status.HTTP_201_CREATED)
def create_spare_part(
    payload: SparePartCreate,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> SparePartRead:
    service = SparePartService(db)
    return SparePartRead.model_validate(service.create(payload, actor=actor))


@router.get("/{spare_part_id}", response_model=SparePartRead)
def get_spare_part(
    spare_part_id: int, db: Session = Depends(get_db)
) -> SparePartRead:
    service = SparePartService(db)
    return SparePartRead.model_validate(service.get(spare_part_id))


@router.put("/{spare_part_id}", response_model=SparePartRead)
def update_spare_part(
    spare_part_id: int,
    payload: SparePartUpdate,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> SparePartRead:
    service = SparePartService(db)
    part = service.update(service.get(spare_part_id), payload, actor=actor)
    return SparePartRead.model_validate(part)


@router.delete("/{spare_part_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_spare_part(
    spare_part_id: int,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    service = SparePartService(db)
    service.delete(service.get(spare_part_id), actor=actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{spare_part_id}/movements", response_model=list[StockMovementRead])
def list_movements(
    spare_part_id: int, db: Session = Depends(get_db)
) -> list[StockMovementRead]:
    service = SparePartService(db)
    service.get(spare_part_id)
    return [
        StockMovementRead.model_validate(item)
        for item in service.movements(spare_part_id)
    ]


@router.post(
    "/{spare_part_id}/movements",
    response_model=StockMovementRead,
    status_code=status.HTTP_201_CREATED,
)
def create_movement(
    spare_part_id: int,
    payload: StockMovementCreate,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> StockMovementRead:
    service = SparePartService(db)
    part = service.get(spare_part_id)
    return StockMovementRead.model_validate(
        service.record_movement(part, payload, actor=actor)
    )
