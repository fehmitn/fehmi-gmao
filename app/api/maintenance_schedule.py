"""Routes API : échéancier de maintenance périodique."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.maintenance_schedule import MaintenanceScheduleSummary
from app.services.maintenance_schedule_service import MaintenanceScheduleService

router = APIRouter(prefix="/api", tags=["maintenance-schedule"])


@router.get("/maintenance-schedule", response_model=MaintenanceScheduleSummary)
def maintenance_schedule(
    site_id: int | None = None,
    equipment_type_id: int | None = None,
    supplier_id: int | None = None,
    horizon_days: int | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
) -> MaintenanceScheduleSummary:
    return MaintenanceScheduleService(db).summary(
        site_id=site_id,
        equipment_type_id=equipment_type_id,
        supplier_id=supplier_id,
        horizon_days=horizon_days,
        search=search,
    )
