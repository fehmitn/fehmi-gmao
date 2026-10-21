"""Routes API : journal d'audit et statistiques."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.dashboard import DashboardStats
from app.schemas.user import AuditLogRead
from app.services.dashboard_service import DashboardService
from app.repositories.audit import AuditRepository

router = APIRouter(prefix="/api", tags=["audit"])


@router.get("/audit", response_model=list[AuditLogRead])
def list_audit_logs(
    action: str | None = None,
    entity_type: str | None = None,
    actor_id: int | None = None,
    search: str | None = None,
    page: int = 1,
    size: int = 50,
    db: Session = Depends(get_db),
) -> list[AuditLogRead]:
    repository = AuditRepository(db)
    result = repository.list(
        action=action,
        entity_type=entity_type,
        actor_id=actor_id,
        search=search,
        page=page,
        size=size,
    )
    return [AuditLogRead.model_validate(item) for item in result.items]


@router.get("/stats/dashboard", response_model=DashboardStats)
def dashboard_stats(db: Session = Depends(get_db)) -> DashboardStats:
    return DashboardService(db).stats()
