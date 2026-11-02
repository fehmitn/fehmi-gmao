"""Schemas de l'analyse de maintenance (fiabilité, coûts, alertes)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel


def format_minutes(minutes: float | None) -> str | None:
    """Durée lisible en heures/minutes, arrondie à la minute."""
    if minutes is None:
        return None
    total = int(round(minutes))
    hours, remainder = divmod(total, 60)
    if hours:
        return f"{hours} h {remainder:02d} min"
    return f"{remainder} min"


def format_cost(value: Decimal | None) -> str:
    """Montant en euros avec séparateurs français."""
    amount = Decimal(value or 0)
    text = f"{amount:,.2f}"
    return text.replace(",", " ").replace(".", ",")


def format_percent(value: float | None) -> str:
    if value is None:
        return "—"
    text = f"{value * 100:.1f}"
    return text.replace(".", ",") + " %"


class EquipmentKpi(BaseModel):
    """Indicateurs de fiabilité et de coût d'un équipement sur une période."""

    equipment_id: int
    equipment_code: str
    equipment_name: str
    site_code: str | None = None
    failure_count: int = 0
    failure_count_12m: int = 0
    downtime_minutes: int = 0
    mttr_minutes: float | None = None
    mtbf_minutes: float | None = None
    availability: float | None = None
    parts_cost: Decimal = Decimal("0")
    last_failure_on: date | None = None
    recurrent: bool = False

    @property
    def mttr_label(self) -> str:
        return format_minutes(self.mttr_minutes) or "—"

    @property
    def mtbf_label(self) -> str:
        return format_minutes(self.mtbf_minutes) or "—"

    @property
    def downtime_label(self) -> str:
        return format_minutes(self.downtime_minutes) or "—"

    @property
    def availability_label(self) -> str:
        return format_percent(self.availability)

    @property
    def parts_cost_label(self) -> str:
        return format_cost(self.parts_cost)

    @property
    def last_failure_label(self) -> str:
        if self.last_failure_on is None:
            return "—"
        return self.last_failure_on.strftime("%d/%m/%Y")

    @property
    def recurrent_label(self) -> str:
        if not self.recurrent:
            return ""
        return f"Pannes récurrentes ({self.failure_count_12m} sur 12 mois)"


class CostLine(BaseModel):
    """Coût des pièces consommées sur un ordre de travail."""

    work_order_id: int
    code: str
    equipment_id: int
    equipment_code: str
    equipment_name: str
    is_corrective: bool
    parts_cost: Decimal

    @property
    def cost_label(self) -> str:
        return format_cost(self.parts_cost)

    @property
    def kind_label(self) -> str:
        return "Corrective" if self.is_corrective else "Préventive"


class AnalyticsSummary(BaseModel):
    """Synthèse complète affichée sur la page d'analyse."""

    days: int
    start_date: date
    end_date: date
    equipment_count: int
    total_failures: int
    total_downtime_minutes: int
    global_mttr_minutes: float | None
    global_availability: float | None
    total_parts_cost: Decimal
    equipment: list[EquipmentKpi]
    cost_lines: list[CostLine]

    @property
    def global_mttr_label(self) -> str:
        return format_minutes(self.global_mttr_minutes) or "—"

    @property
    def global_availability_label(self) -> str:
        return format_percent(self.global_availability)

    @property
    def total_parts_cost_label(self) -> str:
        return format_cost(self.total_parts_cost)

    @property
    def total_downtime_label(self) -> str:
        return format_minutes(self.total_downtime_minutes) or "—"


class InterventionAlert(BaseModel):
    """Demande corrective non affectée depuis trop longtemps."""

    work_order_id: int
    code: str
    equipment_code: str
    equipment_name: str
    description: str | None = None
    created_on: date
    age_days: int

    @property
    def age_label(self) -> str:
        if self.age_days <= 0:
            return "du jour"
        return f"{self.age_days} j"


class OverdueWorkOrderAlert(BaseModel):
    """OT préventif dont l'échéance est dépassée."""

    work_order_id: int
    code: str
    equipment_code: str
    equipment_name: str
    due_date: date
    days_late: int
    status_label: str
    priority_label: str

    @property
    def late_label(self) -> str:
        return f"{self.days_late} j"


class DashboardAlerts(BaseModel):
    """Alertes d'exploitation affichées sur le tableau de bord."""

    threshold_days: int
    unassigned: list[InterventionAlert]
    overdue_work_orders: list[OverdueWorkOrderAlert]

    @property
    def unassigned_count(self) -> int:
        return len(self.unassigned)

    @property
    def overdue_work_order_count(self) -> int:
        return len(self.overdue_work_orders)

    @property
    def total_count(self) -> int:
        return self.unassigned_count + self.overdue_work_order_count
