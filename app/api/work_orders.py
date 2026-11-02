"""Routes API des ordres de travail."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.enums import WorkOrderStatus
from app.models.user import User
from app.schemas.work_order import (
    WorkOrderAssignment,
    WorkOrderCreate,
    WorkOrderGenerationResult,
    WorkOrderRead,
    WorkOrderStatusUpdate,
)
from app.services.work_order_service import WorkOrderService

router = APIRouter(prefix="/api/work-orders", tags=["work-orders"])


@router.get("", response_model=list[WorkOrderRead])
def list_work_orders(
    status_filter: WorkOrderStatus | None = None,
    assigned_to_id: int | None = None,
    search: str | None = None,
    open_only: bool = False,
    db: Session = Depends(get_db),
) -> list:
    return WorkOrderService(db).list(
        status=status_filter.value if status_filter else None,
        assigned_to_id=assigned_to_id,
        search=search,
        open_only=open_only,
    )


@router.post("", response_model=WorkOrderRead, status_code=status.HTTP_201_CREATED)
def create_work_order(
    payload: WorkOrderCreate,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> object:
    return WorkOrderService(db).create(payload, actor=actor)


@router.post("/generate", response_model=WorkOrderGenerationResult)
def generate_work_orders(
    assigned_to_id: int | None = None,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> WorkOrderGenerationResult:
    created, skipped = WorkOrderService(db).generate_from_schedule(
        assigned_to_id=assigned_to_id, actor=actor
    )
    return WorkOrderGenerationResult(
        created=len(created),
        skipped=skipped,
        work_orders=[WorkOrderRead.model_validate(item) for item in created],
    )


@router.get("/{work_order_id}", response_model=WorkOrderRead)
def get_work_order(work_order_id: int, db: Session = Depends(get_db)) -> object:
    return WorkOrderService(db).get(work_order_id)


@router.put("/{work_order_id}/assignment", response_model=WorkOrderRead)
def assign_work_order(
    work_order_id: int,
    payload: WorkOrderAssignment,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> object:
    service = WorkOrderService(db)
    return service.assign(service.get(work_order_id), payload, actor=actor)


@router.put("/{work_order_id}/status", response_model=WorkOrderRead)
def update_work_order_status(
    work_order_id: int,
    payload: WorkOrderStatusUpdate,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> object:
    service = WorkOrderService(db)
    return service.update_status(service.get(work_order_id), payload, actor=actor)
