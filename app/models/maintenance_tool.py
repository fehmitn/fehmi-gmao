from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TimestampMixin
from app.models.enums import (
    CalibrationResult,
    CalibrationStatus,
    MaintenanceIntervalUnit,
    ToolStatus,
)

#: Délai d'alerte avant l'échéance d'étalonnage (jours).
CALIBRATION_WARNING_DAYS = 30


def _today() -> date:
    """Horloge du domaine, importée tardivement pour éviter un cycle."""
    from app.services.clock import today

    return today()


class MaintenanceTool(IdMixin, TimestampMixin, Base):
    """Équipement de maintenance non consommé (outil, appareil de mesure).

    Il ne s'agit pas d'un équipement de production mais d'un moyen utilisé
    pour réaliser un OT. Sa fiche d'utilisation suit les prêts/restaurations
    et la contrainte légale d'étalonnage périodique.
    """

    __tablename__ = "maintenance_tools"

    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    manufacturer: Mapped[str | None] = mapped_column(String(150), nullable=True)
    model: Mapped[str | None] = mapped_column(String(150), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    site_id: Mapped[int | None] = mapped_column(
        ForeignKey("sites.id", ondelete="SET NULL"), nullable=True, index=True
    )
    storage_location: Mapped[str | None] = mapped_column(String(150), nullable=True)
    status: Mapped[str] = mapped_column(
        String(30), default=ToolStatus.AVAILABLE.value, index=True
    )
    requires_calibration: Mapped[bool] = mapped_column(Boolean, default=False)
    calibration_interval_value: Mapped[int | None] = mapped_column(nullable=True)
    calibration_interval_unit: Mapped[str] = mapped_column(
        String(20), default=MaintenanceIntervalUnit.MONTHS.value
    )
    last_calibration_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    next_calibration_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, index=True
    )
    calibration_provider_id: Mapped[int | None] = mapped_column(
        ForeignKey("maintenance_suppliers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    legal_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    purchase_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    commissioning_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    site = relationship("Site", lazy="joined")
    calibration_provider = relationship("MaintenanceSupplier", lazy="joined")
    calibrations: Mapped[list["ToolCalibration"]] = relationship(
        back_populates="tool",
        order_by="ToolCalibration.calibrated_on.desc(), ToolCalibration.id.desc()",
    )
    usages: Mapped[list["ToolUsage"]] = relationship(
        back_populates="tool",
        order_by="ToolUsage.started_on.desc(), ToolUsage.id.desc()",
    )

    @property
    def status_label(self) -> str:
        return ToolStatus(self.status).label

    @property
    def status_css(self) -> str:
        return ToolStatus(self.status).css

    @property
    def calibration_periodicity_label(self) -> str | None:
        if not self.calibration_interval_value:
            return None
        from app.services.periodicity import periodicity_label

        try:
            return periodicity_label(
                self.calibration_interval_value, self.calibration_interval_unit
            )
        except ValueError:
            return None

    @property
    def calibration_days_remaining(self) -> int | None:
        if self.next_calibration_date is None:
            return None
        return (self.next_calibration_date - _today()).days

    @property
    def calibration_status(self) -> CalibrationStatus:
        if not self.requires_calibration:
            return CalibrationStatus.NOT_REQUIRED
        if self.next_calibration_date is None:
            return CalibrationStatus.MISSING
        days = self.calibration_days_remaining or 0
        if days < 0:
            return CalibrationStatus.OVERDUE
        if days <= CALIBRATION_WARNING_DAYS:
            return CalibrationStatus.DUE_SOON
        return CalibrationStatus.VALID

    @property
    def calibration_status_label(self) -> str:
        return self.calibration_status.label

    @property
    def calibration_status_css(self) -> str:
        return self.calibration_status.css

    @property
    def calibration_blocked(self) -> bool:
        """Un outil sans étalonnage valide ne doit pas être utilisé."""
        if not self.requires_calibration:
            return False
        return self.calibration_status in (
            CalibrationStatus.MISSING,
            CalibrationStatus.OVERDUE,
        )

    @property
    def checkout_block_reason(self) -> str | None:
        if not self.is_active:
            return "Outil inactif."
        if ToolStatus(self.status) in (ToolStatus.OUT_OF_SERVICE, ToolStatus.RETIRED):
            return f"Outil {self.status_label.lower()}."
        if ToolStatus(self.status) is ToolStatus.MAINTENANCE:
            return "Outil en maintenance."
        if self.calibration_blocked:
            if self.calibration_status is CalibrationStatus.MISSING:
                return "Aucun étalonnage enregistré : utilisation interdite."
            return "Étalonnage en retard : utilisation interdite."
        return None

    @property
    def open_usage(self) -> "ToolUsage | None":
        for usage in self.usages:
            if usage.ended_on is None:
                return usage
        return None

    @property
    def provider_name(self) -> str | None:
        return self.calibration_provider.name if self.calibration_provider else None

    @property
    def site_code(self) -> str | None:
        return self.site.code if self.site else None

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


class ToolCalibration(IdMixin, Base):
    """Étalonnage ou vérification périodique d'un équipement de maintenance."""

    __tablename__ = "tool_calibrations"

    tool_id: Mapped[int] = mapped_column(
        ForeignKey("maintenance_tools.id", ondelete="RESTRICT"), index=True
    )
    calibrated_on: Mapped[date] = mapped_column(Date, index=True)
    next_due_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    provider_id: Mapped[int | None] = mapped_column(
        ForeignKey("maintenance_suppliers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    certificate_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    result: Mapped[str] = mapped_column(
        String(20), default=CalibrationResult.PASSED.value, index=True
    )
    cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    tool = relationship("MaintenanceTool", back_populates="calibrations")
    provider = relationship("MaintenanceSupplier", lazy="joined")
    actor = relationship("User", lazy="joined")

    @property
    def result_label(self) -> str:
        return CalibrationResult(self.result).label

    @property
    def result_css(self) -> str:
        return CalibrationResult(self.result).css

    @property
    def provider_name(self) -> str | None:
        return self.provider.name if self.provider else None

    @property
    def actor_name(self) -> str | None:
        return self.actor.display_name if self.actor else None

    def __str__(self) -> str:
        return f"{self.tool_id} @ {self.calibrated_on}"


class ToolUsage(IdMixin, TimestampMixin, Base):
    """Ligne de la fiche d'utilisation : prêt d'un outil pour un OT."""

    __tablename__ = "tool_usages"

    tool_id: Mapped[int] = mapped_column(
        ForeignKey("maintenance_tools.id", ondelete="RESTRICT"), index=True
    )
    work_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("work_orders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    used_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    started_on: Mapped[date] = mapped_column(Date, default=_today, index=True)
    ended_on: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    return_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    tool = relationship("MaintenanceTool", back_populates="usages")
    work_order = relationship("WorkOrder", lazy="joined")
    used_by = relationship("User", lazy="joined")

    @property
    def is_open(self) -> bool:
        return self.ended_on is None

    @property
    def duration_days(self) -> int | None:
        if self.ended_on is None:
            return None
        return (self.ended_on - self.started_on).days

    @property
    def used_by_name(self) -> str | None:
        return self.used_by.display_name if self.used_by else None

    @property
    def work_order_code(self) -> str | None:
        return self.work_order.code if self.work_order else None

    def __str__(self) -> str:
        return f"{self.tool_id} / {self.used_by_id} @ {self.started_on}"
