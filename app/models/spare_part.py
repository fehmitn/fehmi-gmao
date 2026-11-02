from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TimestampMixin
from app.models.enums import StockMovementType


def _today() -> date:
    """Horloge du domaine, importée tardivement pour éviter un cycle."""
    from app.services.clock import today

    return today()


class SparePart(IdMixin, TimestampMixin, Base):
    """Pièce de rechange stockée et consommable lors d'une intervention.

    Le stock courant n'est jamais modifié directement depuis la fiche : il
    évolue uniquement par des mouvements append-only (entrée, sortie,
    inventaire), afin de conserver la traçabilité des consommations.
    """

    __tablename__ = "spare_parts"

    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    unit: Mapped[str] = mapped_column(String(30), default="pièce")
    manufacturer: Mapped[str | None] = mapped_column(String(150), nullable=True)
    manufacturer_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    supplier_id: Mapped[int | None] = mapped_column(
        ForeignKey("maintenance_suppliers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    site_id: Mapped[int | None] = mapped_column(
        ForeignKey("sites.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    storage_location: Mapped[str | None] = mapped_column(String(150), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0"), nullable=False
    )
    min_quantity: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0"), nullable=False
    )
    max_quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    supplier = relationship("MaintenanceSupplier", lazy="joined")
    site = relationship("Site", lazy="joined")
    movements: Mapped[list["StockMovement"]] = relationship(
        back_populates="spare_part",
        order_by="StockMovement.movement_date.desc(), StockMovement.id.desc()",
    )

    @property
    def is_out_of_stock(self) -> bool:
        return (self.quantity or Decimal("0")) <= 0

    @property
    def is_low_stock(self) -> bool:
        if not self.is_active:
            return False
        return (self.quantity or Decimal("0")) <= (self.min_quantity or Decimal("0"))

    @property
    def stock_status_label(self) -> str:
        if self.is_out_of_stock:
            return "Rupture"
        if self.is_low_stock:
            return "Sous le seuil"
        return "Disponible"

    @property
    def stock_status_css(self) -> str:
        if self.is_out_of_stock:
            return "text-bg-danger"
        if self.is_low_stock:
            return "text-bg-warning"
        return "text-bg-success"

    @property
    def stock_value(self) -> Decimal:
        if self.unit_cost is None:
            return Decimal("0")
        return (self.quantity or Decimal("0")) * self.unit_cost

    @property
    def supplier_name(self) -> str | None:
        return self.supplier.name if self.supplier else None

    @property
    def site_code(self) -> str | None:
        return self.site.code if self.site else None

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


class StockMovement(IdMixin, Base):
    """Mouvement de stock append-only d'une pièce de rechange."""

    __tablename__ = "stock_movements"

    spare_part_id: Mapped[int] = mapped_column(
        ForeignKey("spare_parts.id", ondelete="RESTRICT"), index=True
    )
    movement_type: Mapped[str] = mapped_column(String(20), index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    quantity_delta: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    resulting_quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    movement_date: Mapped[date] = mapped_column(Date, default=_today, index=True)
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    work_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("work_orders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    spare_part = relationship("SparePart", back_populates="movements")
    work_order = relationship("WorkOrder", lazy="joined")
    actor = relationship("User", lazy="joined")

    @property
    def movement_type_label(self) -> str:
        return StockMovementType(self.movement_type).label

    @property
    def movement_type_css(self) -> str:
        return StockMovementType(self.movement_type).css

    @property
    def delta_label(self) -> str:
        delta = self.quantity_delta or Decimal("0")
        if delta > 0:
            return f"+{delta:g}"
        return f"{delta:g}"

    @property
    def actor_name(self) -> str | None:
        return self.actor.display_name if self.actor else None

    @property
    def work_order_code(self) -> str | None:
        return self.work_order.code if self.work_order else None

    @property
    def total_cost(self) -> Decimal | None:
        """Coût du mouvement, figé au prix unitaire de l'époque."""
        if self.unit_cost is None:
            return None
        return (self.quantity or Decimal("0")) * self.unit_cost

    def __str__(self) -> str:
        return f"{self.spare_part_id} {self.movement_type} {self.quantity}"
