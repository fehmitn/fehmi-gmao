"""Journal d'audit : qui modifie quoi, quand et pourquoi."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.enums import AuditAction
from app.models.user import User
from app.repositories.audit import AuditRepository


class AuditService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = AuditRepository(db)

    def record(
        self,
        action: AuditAction | str,
        entity_type: str,
        entity_id: int | None = None,
        *,
        actor: User | None = None,
        reason: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> AuditLog:
        log = AuditLog(
            actor_id=actor.id if actor is not None else None,
            actor_label=actor.display_name if actor is not None else "système",
            action=str(action),
            entity_type=entity_type,
            entity_id=entity_id,
            reason=(reason or "").strip() or None,
            payload=payload,
        )
        return self.repository.add(log)
