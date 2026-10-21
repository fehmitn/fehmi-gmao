from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin


class AuditLog(IdMixin, Base):
    """Piste d'audit.

    Sert deux objectifs pédagogiques :
      1. tracer qui modifie quoi (traçabilité) ;
      2. tracer explicitement les saisies rétroactives (action « backdate »)
         avec le motif de la dérogation.
    """

    __tablename__ = "audit_logs"

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
    )
    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    actor_label: Mapped[str] = mapped_column(String(150), default="système")
    action: Mapped[str] = mapped_column(String(30), index=True)
    entity_type: Mapped[str] = mapped_column(String(50), index=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    actor: Mapped["User | None"] = relationship()

    def __str__(self) -> str:
        return f"{self.occurred_at} {self.action} {self.entity_type}#{self.entity_id}"
