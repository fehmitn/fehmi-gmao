from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin


class MaintenanceExecution(IdMixin, Base):
    """Réalisation d'un ordre de travail rattaché à une maintenance périodique.

    La projection de l'échéancier reste théorique : les dates sont calculées
    depuis l'ancrage de la règle. À la saisie d'une réalisation, on fige
    l'échéance théorique de référence et l'écart en jours, afin de logger le
    retard **par rapport au référentiel** même si la règle évolue ensuite.

    Le journal est append-only : pas de mise à jour, pour préserver la trace.
    """

    __tablename__ = "maintenance_executions"

    equipment_id: Mapped[int] = mapped_column(
        ForeignKey("equipments.id", ondelete="CASCADE"),
        index=True,
    )
    periodic_maintenance_id: Mapped[int] = mapped_column(
        ForeignKey("periodic_maintenances.id", ondelete="RESTRICT"),
        index=True,
    )
    performed_on: Mapped[date] = mapped_column(Date, index=True)
    theoretical_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    delay_days: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    performed_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
    )
    operating_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)

    equipment: Mapped["Equipment"] = relationship(
        back_populates="maintenance_executions"
    )
    periodic_maintenance: Mapped["PeriodicMaintenance"] = relationship(
        back_populates="executions"
    )
    performed_by: Mapped["User | None"] = relationship()

    def __str__(self) -> str:
        if self.delay_days is None:
            return (
                f"{self.equipment_id} / {self.periodic_maintenance_id} "
                f"@ {self.performed_on} ({self.operating_hours} h)"
            )
        return (
            f"{self.equipment_id} / {self.periodic_maintenance_id} "
            f"@ {self.performed_on} ({self.delay_days:+d} j)"
        )

    @property
    def delay_label(self) -> str | None:
        if self.delay_days is None:
            return None
        if self.delay_days > 0:
            return f"{self.delay_days} j de retard"
        if self.delay_days < 0:
            return f"{abs(self.delay_days)} j d'avance"
        return "à l'échéance"

    @property
    def delay_css(self) -> str | None:
        if self.delay_days is None:
            return None
        if self.delay_days > 0:
            return "text-bg-danger"
        if self.delay_days < 0:
            return "text-bg-info"
        return "text-bg-success"
