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
) -> list:
    repository = AuditRepository(db)
    result = repository.list(
        action=action,
        entity_type=entity_type,
        actor_id=actor_id,
        search=search,
        page=page,
        size=size,
    )
    items = []
    for item in result.items:
        data = {
            "id": item.id,
            "occurred_at": item.occurred_at,
            "actor_id": item.actor_id,
            "actor_username": item.actor_label,
            "action": item.action,
            "entity_type": item.entity_type,
            "entity_id": item.entity_id,
            "payload": item.payload,
            "ip_address": None,
            "user_agent": None,
            "action_label": None,
            "entity_label": None,
            "payload_summary": None,
        }
        if hasattr(item, "reason") and item.reason:
            data["reason"] = item.reason
        try:
            items.append(AuditLogRead.model_validate(data))
        except Exception:
            items.append({**data, "reason": getattr(item, "reason", None)})
    return items


@router.get("/stats/dashboard", response_model=DashboardStats)
def dashboard_stats(db: Session = Depends(get_db)) -> DashboardStats:
    return DashboardService(db).stats()
