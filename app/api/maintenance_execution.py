"""Routes API : réalisations d'ordres de travail de maintenance périodique."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.maintenance_execution import (
    MaintenanceExecutionCreate,
    MaintenanceExecutionRead,
)
from app.services.equipment_service import EquipmentService
from app.services.maintenance_execution_service import MaintenanceExecutionService
from app.services.periodic_maintenance_service import PeriodicMaintenanceService

router = APIRouter(tags=["maintenance-executions"])


@router.get(
    "/api/equipments/{equipment_id}/maintenance-executions",
    response_model=list[MaintenanceExecutionRead],
)
def list_executions(
    equipment_id: int,
    db: Session = Depends(get_db),
) -> list[MaintenanceExecutionRead]:
    service = MaintenanceExecutionService(db)
    return [
        MaintenanceExecutionRead.model_validate(item)
        for item in service.list_for_equipment(equipment_id)
    ]


@router.post(
    "/api/equipments/{equipment_id}/maintenance-executions",
    response_model=MaintenanceExecutionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_execution(
    equipment_id: int,
    payload: MaintenanceExecutionCreate,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> MaintenanceExecutionRead:
    equipment = EquipmentService(db).get(equipment_id)
    rule = PeriodicMaintenanceService(db).get(payload.periodic_maintenance_id)
    service = MaintenanceExecutionService(db)
    execution = service.create(equipment, rule, payload, actor=actor)
    return MaintenanceExecutionRead.model_validate(execution)
