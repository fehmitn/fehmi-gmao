"""Routes API de la maintenance corrective."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.enums import WorkOrderStatus
from app.models.user import User
from app.schemas.intervention import (
    InterventionAssignment,
    InterventionCancel,
    InterventionFinish,
    InterventionPartCreate,
    InterventionPartRead,
    InterventionPartUse,
    InterventionRead,
    InterventionRequestCreate,
    InterventionStart,
)
from app.services.intervention_service import InterventionService

router = APIRouter(prefix="/api/interventions", tags=["interventions"])


@router.get("", response_model=list[InterventionRead])
def list_interventions(
    status_filter: WorkOrderStatus | None = None,
    assigned_to_id: int | None = None,
    search: str | None = None,
    open_only: bool = False,
    db: Session = Depends(get_db),
) -> list:
    return InterventionService(db).list(
        status=status_filter.value if status_filter else None,
        assigned_to_id=assigned_to_id,
        search=search,
        open_only=open_only,
    )


@router.post("", response_model=InterventionRead, status_code=status.HTTP_201_CREATED)
def create_intervention_request(
    payload: InterventionRequestCreate,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> object:
    return InterventionService(db).create_request(payload, actor=actor)


@router.get("/{intervention_id}", response_model=InterventionRead)
def get_intervention(intervention_id: int, db: Session = Depends(get_db)) -> object:
    return InterventionService(db).get(intervention_id)


@router.put("/{intervention_id}/assignment", response_model=InterventionRead)
def assign_intervention(
    intervention_id: int,
    payload: InterventionAssignment,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> object:
    service = InterventionService(db)
    return service.assign(
        service.get(intervention_id), payload.assigned_to_id, actor=actor
    )


@router.post("/{intervention_id}/start", response_model=InterventionRead)
def start_intervention(
    intervention_id: int,
    payload: InterventionStart,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> object:
    service = InterventionService(db)
    return service.start(service.get(intervention_id), payload, actor=actor)


@router.post("/{intervention_id}/finish", response_model=InterventionRead)
def finish_intervention(
    intervention_id: int,
    payload: InterventionFinish,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> object:
    service = InterventionService(db)
    return service.finish(service.get(intervention_id), payload, actor=actor)


@router.post("/{intervention_id}/cancel", response_model=InterventionRead)
def cancel_intervention(
    intervention_id: int,
    payload: InterventionCancel,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> object:
    service = InterventionService(db)
    return service.cancel(service.get(intervention_id), payload, actor=actor)


@router.get("/{intervention_id}/parts", response_model=list[InterventionPartRead])
def list_intervention_parts(
    intervention_id: int, db: Session = Depends(get_db)
) -> list:
    service = InterventionService(db)
    service.get(intervention_id)
    return service.parts(intervention_id)


@router.post(
    "/{intervention_id}/parts",
    response_model=InterventionPartRead,
    status_code=status.HTTP_201_CREATED,
)
def request_intervention_part(
    intervention_id: int,
    payload: InterventionPartCreate,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> object:
    service = InterventionService(db)
    return service.request_part(service.get(intervention_id), payload, actor=actor)


@router.post(
    "/{intervention_id}/parts/{part_id}/use", response_model=InterventionPartRead
)
def use_intervention_part(
    intervention_id: int,
    part_id: int,
    payload: InterventionPartUse,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> object:
    service = InterventionService(db)
    work_order = service.get(intervention_id)
    return service.use_part(
        work_order, service.get_part(work_order, part_id), payload, actor=actor
    )


@router.post(
    "/{intervention_id}/parts/{part_id}/cancel", response_model=InterventionPartRead
)
def cancel_intervention_part(
    intervention_id: int,
    part_id: int,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> object:
    service = InterventionService(db)
    work_order = service.get(intervention_id)
    return service.cancel_part(
        work_order, service.get_part(work_order, part_id), actor=actor
    )
