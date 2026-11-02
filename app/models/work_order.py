from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TimestampMixin
from app.models.enums import WorkOrderPriority, WorkOrderStatus


class WorkOrder(IdMixin, TimestampMixin, Base):
    """Ordre de travail ouvert à réaliser."""

    __tablename__ = "work_orders"

    code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    equipment_id: Mapped[int] = mapped_column(ForeignKey("equipments.id"), index=True)
    periodic_maintenance_id: Mapped[int | None] = mapped_column(
        ForeignKey("periodic_maintenances.id"), nullable=True, index=True
    )
    assigned_to_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(20), default=WorkOrderStatus.OPEN.value, index=True)
    priority: Mapped[str] = mapped_column(String(20), default=WorkOrderPriority.NORMAL.value)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_operating_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    completed_at: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Maintenance corrective : une demande peut être créée par tout utilisateur,
    # affectée à un technicien, puis exécutée avec des horodatages précis.
    is_corrective: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    intervention_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    intervention_ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    work_done: Mapped[str | None] = mapped_column(Text, nullable=True)

    equipment = relationship("Equipment", lazy="joined")
    periodic_maintenance = relationship("PeriodicMaintenance", lazy="joined")
    assigned_to = relationship("User", foreign_keys=[assigned_to_id], lazy="joined")
    created_by = relationship("User", foreign_keys=[created_by_id], lazy="joined")
    intervention_parts: Mapped[list["InterventionPart"]] = relationship(
        back_populates="work_order",
        order_by="InterventionPart.id",
    )

    @property
    def status_label(self) -> str:
        return WorkOrderStatus(self.status).label

    @property
    def status_css(self) -> str:
        return WorkOrderStatus(self.status).css

    @property
    def priority_label(self) -> str:
        return WorkOrderPriority(self.priority).label

    @property
    def equipment_code(self) -> str | None:
        return self.equipment.code if self.equipment else None

    @property
    def equipment_name(self) -> str | None:
        return self.equipment.name if self.equipment else None

    @property
    def operation_label(self) -> str | None:
        return self.periodic_maintenance.label if self.periodic_maintenance else None

    @property
    def operation_code(self) -> str | None:
        return self.periodic_maintenance.code if self.periodic_maintenance else None

    @property
    def assigned_to_name(self) -> str | None:
        return self.assigned_to.display_name if self.assigned_to else None

    @property
    def created_by_name(self) -> str | None:
        return self.created_by.display_name if self.created_by else None

    @property
    def kind_label(self) -> str:
        return "Corrective" if self.is_corrective else "Préventive"

    @property
    def is_closed(self) -> bool:
        return self.status in (
            WorkOrderStatus.DONE.value,
            WorkOrderStatus.CANCELLED.value,
        )

    @property
    def intervention_duration_minutes(self) -> int | None:
        if not self.intervention_started_at or not self.intervention_ended_at:
            return None
        delta = self.intervention_ended_at - self.intervention_started_at
        return max(0, int(delta.total_seconds() // 60))

    @property
    def intervention_duration_label(self) -> str | None:
        minutes = self.intervention_duration_minutes
        if minutes is None:
            return None
        hours, remainder = divmod(minutes, 60)
        if hours:
            return f"{hours} h {remainder:02d} min"
        return f"{remainder} min"

    def __str__(self) -> str:
        return self.code
