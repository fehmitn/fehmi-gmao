from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TimestampMixin
from app.models.enums import EquipmentStatus


class Equipment(IdMixin, TimestampMixin, Base):
    """Un équipement (« articolo installato » chez WinMaint).

    L'équipement n'est pas directement porteur d'un emplacement texte : il est
    implanté via EquipmentLocation, ce qui donne l'historique des
    déplacements (indispensable pour rattacher une intervention antidatée
    au bon atelier au moment où elle a eu lieu).
    """

    __tablename__ = "equipments"

    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    equipment_type_id: Mapped[int | None] = mapped_column(
        ForeignKey("equipment_types.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    site_id: Mapped[int] = mapped_column(
        ForeignKey("sites.id", ondelete="RESTRICT"),
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        default=EquipmentStatus.OPERATIONAL.value,
        index=True,
    )
    criticality: Mapped[str | None] = mapped_column(String(1), nullable=True, index=True)
    manufacturer: Mapped[str | None] = mapped_column(String(150), nullable=True)
    model: Mapped[str | None] = mapped_column(String(150), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    purchase_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    commissioning_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    acquisition_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    warranty_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_critical: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    site: Mapped["Site"] = relationship(back_populates="equipments")
    equipment_type: Mapped["EquipmentType | None"] = relationship(back_populates="equipments")
    placements: Mapped[list["EquipmentLocation"]] = relationship(
        back_populates="equipment",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"
