from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TimestampMixin
from app.models.enums import MovementType


class EquipmentLocation(IdMixin, TimestampMixin, Base):
    """Implantation d'un équipement dans un emplacement, avec période.

    Une ligne « ouverte » (effective_to IS NULL) = emplacement courant.
    Une ligne fermée = un déplacement passé. L'historique permet de répondre
    à la question « où était cet équipement le 12/03/2024 ? », indispensable
    pour rattacher correctement une intervention saisie a posteriori.
    """

    __tablename__ = "equipment_locations"
    __table_args__ = (
        Index(
            "uq_equipment_open_placement",
            "equipment_id",
            unique=True,
            sqlite_where=text("effective_to IS NULL"),
        ),
    )

    equipment_id: Mapped[int] = mapped_column(
        ForeignKey("equipments.id", ondelete="CASCADE"),
        index=True,
    )
    location_id: Mapped[int] = mapped_column(
        ForeignKey("locations.id", ondelete="RESTRICT"),
        index=True,
    )
    effective_from: Mapped[date] = mapped_column(Date, index=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    movement_type: Mapped[str] = mapped_column(
        String(30),
        default=MovementType.INSTALLATION.value,
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Empreinte de la rétrodatation (pédagogique) : à quelle date la ligne a
    # été saisie, avec quel retard, et quel motif de dérogation.
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    entry_delay_days: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    derogation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    equipment: Mapped["Equipment"] = relationship(back_populates="placements")
    location: Mapped["Location"] = relationship()

    def __str__(self) -> str:
        return f"{self.equipment_id} @ {self.location_id} ({self.effective_from})"

    @property
    def is_open(self) -> bool:
        return self.effective_to is None

    def covers(self, day: date) -> bool:
        """Vrai si l'implantation était effective au jour donné."""
        if day < self.effective_from:
            return False
        return self.effective_to is None or day <= self.effective_to
