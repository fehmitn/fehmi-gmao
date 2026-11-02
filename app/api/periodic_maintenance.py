"""Routes API : maintenances périodiques des familles d'équipements."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.periodic_maintenance import (
    PeriodicMaintenanceCreate,
    PeriodicMaintenanceRead,
    PeriodicMaintenanceUpdate,
)
from app.services.periodic_maintenance_service import PeriodicMaintenanceService

router = APIRouter(tags=["periodic-maintenance"])


@router.get(
    "/api/equipment-types/{type_id}/periodic-maintenances",
    response_model=list[PeriodicMaintenanceRead],
)
def list_periodic_maintenances(
    type_id: int,
    db: Session = Depends(get_db),
) -> list[PeriodicMaintenanceRead]:
    service = PeriodicMaintenanceService(db)
    return [
        PeriodicMaintenanceRead.model_validate(item)
        for item in service.list_for_type(type_id)
    ]


@router.post(
    "/api/equipment-types/{type_id}/periodic-maintenances",
    response_model=PeriodicMaintenanceRead,
    status_code=status.HTTP_201_CREATED,
)
def create_periodic_maintenance(
    type_id: int,
    payload: PeriodicMaintenanceCreate,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> PeriodicMaintenanceRead:
    service = PeriodicMaintenanceService(db)
    maintenance = service.create(type_id, payload, actor=actor)
    return PeriodicMaintenanceRead.model_validate(maintenance)


@router.get(
    "/api/periodic-maintenances/{maintenance_id}",
    response_model=PeriodicMaintenanceRead,
)
def get_periodic_maintenance(
    maintenance_id: int,
    db: Session = Depends(get_db),
) -> PeriodicMaintenanceRead:
    service = PeriodicMaintenanceService(db)
    return PeriodicMaintenanceRead.model_validate(service.get(maintenance_id))


@router.put(
    "/api/periodic-maintenances/{maintenance_id}",
    response_model=PeriodicMaintenanceRead,
)
def update_periodic_maintenance(
    maintenance_id: int,
    payload: PeriodicMaintenanceUpdate,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> PeriodicMaintenanceRead:
    service = PeriodicMaintenanceService(db)
    maintenance = service.update(service.get(maintenance_id), payload, actor=actor)
    return PeriodicMaintenanceRead.model_validate(maintenance)


@router.delete(
    "/api/periodic-maintenances/{maintenance_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_periodic_maintenance(
    maintenance_id: int,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    service = PeriodicMaintenanceService(db)
    service.delete(service.get(maintenance_id), actor=actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
