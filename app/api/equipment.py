from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.equipment import EquipmentCreate, EquipmentRead
from app.services.equipment import EquipmentAlreadyExistsError, EquipmentService

router = APIRouter(prefix="/equipments", tags=["equipments"])


@router.post(
    "",
    response_model=EquipmentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_equipment(
    payload: EquipmentCreate,
    db: Session = Depends(get_db),
) -> EquipmentRead:
    service = EquipmentService(db)
    try:
        equipment = service.create_equipment(payload)
    except EquipmentAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return EquipmentRead.model_validate(equipment)
