from __future__ import annotations

from datetime import date

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TimestampMixin
from app.models.enums import MaintenanceAnchor, MaintenanceIntervalUnit, MaintenanceType


class PeriodicMaintenance(IdMixin, TimestampMixin, Base):
    """Contrainte de maintenance périodique portée par une famille d'équipements.

    La règle est définie **une seule fois** sur la famille : tous les
    équipements de cette famille en héritent. L'échéance est calculée à la
    volée depuis l'ancrage (mise en service, première implantation ou date
    fixe) ; aucune date n'est stockée par équipement.
    """

    __tablename__ = "periodic_maintenances"
    __table_args__ = (
        UniqueConstraint(
            "equipment_type_id",
            "code",
            name="uq_periodic_maintenance_type_code",
        ),
    )

    equipment_type_id: Mapped[int] = mapped_column(
        ForeignKey("equipment_types.id", ondelete="CASCADE"),
        index=True,
    )
    supplier_id: Mapped[int | None] = mapped_column(
        ForeignKey("maintenance_suppliers.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    code: Mapped[str] = mapped_column(String(50))
    label: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    interval_value: Mapped[int] = mapped_column(Integer)
    interval_unit: Mapped[str] = mapped_column(
        String(20),
        default=MaintenanceIntervalUnit.MONTHS.value,
    )
    maintenance_type: Mapped[str] = mapped_column(
        String(30),
        default=MaintenanceType.PREVENTIVE_SYSTEMATIC.value,
        index=True,
    )

    anchor: Mapped[str] = mapped_column(
        String(20),
        default=MaintenanceAnchor.COMMISSIONING.value,
    )
    fixed_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    tolerance_days: Mapped[int] = mapped_column(Integer, default=0)
    estimated_duration_minutes: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    equipment_type: Mapped["EquipmentType"] = relationship(
        back_populates="periodic_maintenances"
    )
    supplier: Mapped["MaintenanceSupplier | None"] = relationship(
        back_populates="periodic_maintenances"
    )
    executions: Mapped[list["MaintenanceExecution"]] = relationship(
        back_populates="periodic_maintenance",
        passive_deletes=True,
    )

    def __str__(self) -> str:
        return f"{self.code} - {self.label}"

    @property
    def interval_unit_label(self) -> str:
        try:
            return MaintenanceIntervalUnit(self.interval_unit).label
        except ValueError:
            return self.interval_unit

    @property
    def maintenance_type_label(self) -> str:
        try:
            return MaintenanceType(self.maintenance_type).label
        except ValueError:
            return self.maintenance_type

    @property
    def anchor_label(self) -> str:
        try:
            return MaintenanceAnchor(self.anchor).label
        except ValueError:
            return self.anchor
