from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.repositories.base import Page


class AuditRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(
        self,
        *,
        action: str | None = None,
        entity_type: str | None = None,
        actor_id: int | None = None,
        search: str | None = None,
        page: int = 1,
        size: int = 50,
    ) -> Page[AuditLog]:
        conditions = []
        if action:
            conditions.append(AuditLog.action == action)
        if entity_type:
            conditions.append(AuditLog.entity_type == entity_type)
        if actor_id is not None:
            conditions.append(AuditLog.actor_id == actor_id)
        if search:
            pattern = f"%{search.strip()}%"
            conditions.append(
                AuditLog.reason.ilike(pattern) | AuditLog.actor_label.ilike(pattern)
            )

        total = int(
            self.db.scalar(select(func.count(AuditLog.id)).where(*conditions)) or 0
        )
        page = max(1, page)
        size = max(1, min(size, 500))
        stmt = (
            select(AuditLog)
            .where(*conditions)
            .order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        items = list(self.db.scalars(stmt).all())
        return Page(items=items, total=total, page=page, size=size)

    def add(self, log: AuditLog) -> AuditLog:
        self.db.add(log)
        self.db.commit()
        self.db.refresh(log)
        return log
