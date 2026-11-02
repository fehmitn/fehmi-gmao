from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin
from app.models.enums import InterventionPartStatus


class InterventionPart(IdMixin, Base):
    """Pièce demandée puis consommée pour une intervention corrective.

    La demande et la consommation sont deux étapes distinctes : le technicien
    commence par demander la pièce, puis la déclare utilisée. La sortie de
    stock n'est créée qu'au moment de l'utilisation, avec le lien vers l'OT.
    """

    __tablename__ = "intervention_parts"

    work_order_id: Mapped[int] = mapped_column(
        ForeignKey("work_orders.id", ondelete="RESTRICT"), index=True
    )
    spare_part_id: Mapped[int] = mapped_column(
        ForeignKey("spare_parts.id", ondelete="RESTRICT"), index=True
    )
    requested_quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    used_quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default=InterventionPartStatus.REQUESTED.value, index=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    used_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    work_order = relationship("WorkOrder", back_populates="intervention_parts")
    spare_part = relationship("SparePart", lazy="joined")
    requested_by = relationship(
        "User", foreign_keys=[requested_by_id], lazy="joined"
    )
    used_by = relationship("User", foreign_keys=[used_by_id], lazy="joined")

    @property
    def status_label(self) -> str:
        return InterventionPartStatus(self.status).label

    @property
    def status_css(self) -> str:
        return InterventionPartStatus(self.status).css

    @property
    def is_pending(self) -> bool:
        return self.status == InterventionPartStatus.REQUESTED.value

    @property
    def spare_part_code(self) -> str | None:
        return self.spare_part.code if self.spare_part else None

    @property
    def spare_part_name(self) -> str | None:
        return self.spare_part.name if self.spare_part else None

    @property
    def unit(self) -> str | None:
        return self.spare_part.unit if self.spare_part else None

    @property
    def available_quantity(self) -> Decimal | None:
        return self.spare_part.quantity if self.spare_part else None

    @property
    def requested_by_name(self) -> str | None:
        return self.requested_by.display_name if self.requested_by else None

    @property
    def used_by_name(self) -> str | None:
        return self.used_by.display_name if self.used_by else None

    @property
    def quantity_label(self) -> str:
        quantity = self.used_quantity if self.used_quantity is not None else self.requested_quantity
        return f"{quantity:g}"

    def __str__(self) -> str:
        return f"{self.work_order_id} / {self.spare_part_id} ({self.status})"
