"""Routes API : équipements de maintenance, étalonnages et utilisations."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.errors import NotFoundError
from app.models.enums import CalibrationStatus, ToolStatus
from app.models.user import User
from app.schemas.maintenance_tool import (
    CalibrationCreate,
    CalibrationRead,
    MaintenanceToolCreate,
    MaintenanceToolRead,
    MaintenanceToolUpdate,
    ToolStatusUpdate,
    ToolUsageCreate,
    ToolUsageRead,
    ToolUsageReturn,
)
from app.services.maintenance_tool_service import MaintenanceToolService

router = APIRouter(prefix="/api/maintenance-tools", tags=["maintenance-tools"])


@router.get("", response_model=list[MaintenanceToolRead])
def list_tools(
    search: str | None = None,
    category: str | None = None,
    status_filter: ToolStatus | None = None,
    calibration_status: CalibrationStatus | None = None,
    active_only: bool = False,
    db: Session = Depends(get_db),
) -> list[MaintenanceToolRead]:
    service = MaintenanceToolService(db)
    return [
        MaintenanceToolRead.model_validate(item)
        for item in service.list(
            search=search,
            category=category,
            status=status_filter,
            calibration_status=calibration_status,
            active_only=active_only,
        )
    ]


@router.get("/summary")
def tools_summary(db: Session = Depends(get_db)) -> dict[str, int]:
    return MaintenanceToolService(db).summary()


@router.post("", response_model=MaintenanceToolRead, status_code=status.HTTP_201_CREATED)
def create_tool(
    payload: MaintenanceToolCreate,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> MaintenanceToolRead:
    service = MaintenanceToolService(db)
    return MaintenanceToolRead.model_validate(service.create(payload, actor=actor))


@router.get("/{tool_id}", response_model=MaintenanceToolRead)
def get_tool(tool_id: int, db: Session = Depends(get_db)) -> MaintenanceToolRead:
    service = MaintenanceToolService(db)
    return MaintenanceToolRead.model_validate(service.get(tool_id))


@router.put("/{tool_id}", response_model=MaintenanceToolRead)
def update_tool(
    tool_id: int,
    payload: MaintenanceToolUpdate,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> MaintenanceToolRead:
    service = MaintenanceToolService(db)
    tool = service.update(service.get(tool_id), payload, actor=actor)
    return MaintenanceToolRead.model_validate(tool)


@router.put("/{tool_id}/status", response_model=MaintenanceToolRead)
def update_tool_status(
    tool_id: int,
    payload: ToolStatusUpdate,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> MaintenanceToolRead:
    service = MaintenanceToolService(db)
    tool = service.set_status(service.get(tool_id), payload.status, actor=actor)
    return MaintenanceToolRead.model_validate(tool)


@router.delete("/{tool_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tool(
    tool_id: int,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    service = MaintenanceToolService(db)
    service.delete(service.get(tool_id), actor=actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{tool_id}/calibrations", response_model=list[CalibrationRead])
def list_calibrations(
    tool_id: int, db: Session = Depends(get_db)
) -> list[CalibrationRead]:
    service = MaintenanceToolService(db)
    service.get(tool_id)
    return [
        CalibrationRead.model_validate(item)
        for item in service.calibrations(tool_id)
    ]


@router.post(
    "/{tool_id}/calibrations",
    response_model=CalibrationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_calibration(
    tool_id: int,
    payload: CalibrationCreate,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> CalibrationRead:
    service = MaintenanceToolService(db)
    tool = service.get(tool_id)
    return CalibrationRead.model_validate(
        service.add_calibration(tool, payload, actor=actor)
    )


@router.get("/{tool_id}/usages", response_model=list[ToolUsageRead])
def list_usages(tool_id: int, db: Session = Depends(get_db)) -> list[ToolUsageRead]:
    service = MaintenanceToolService(db)
    service.get(tool_id)
    return [
        ToolUsageRead.model_validate(item) for item in service.usages(tool_id)
    ]


@router.post(
    "/{tool_id}/usages",
    response_model=ToolUsageRead,
    status_code=status.HTTP_201_CREATED,
)
def start_usage(
    tool_id: int,
    payload: ToolUsageCreate,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> ToolUsageRead:
    service = MaintenanceToolService(db)
    tool = service.get(tool_id)
    return ToolUsageRead.model_validate(
        service.start_usage(tool, payload, actor=actor)
    )


@router.post("/{tool_id}/usages/{usage_id}/return", response_model=ToolUsageRead)
def end_usage(
    tool_id: int,
    usage_id: int,
    payload: ToolUsageReturn,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> ToolUsageRead:
    service = MaintenanceToolService(db)
    tool = service.get(tool_id)
    usage = service.repository.get_usage(tool_id, usage_id)
    if usage is None:
        raise NotFoundError(f"Utilisation {usage_id} introuvable pour cet outil.")
    return ToolUsageRead.model_validate(
        service.end_usage(tool, usage, payload, actor=actor)
    )
