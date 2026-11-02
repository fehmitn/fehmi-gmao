"""Service d'analyse de maintenance : fiabilité, coûts et alertes.

Les indicateurs sont calculés sur une fenêtre glissante exprimée en jours et
s'appuient sur les interventions correctives terminées (heures de début et de
fin renseignées) ainsi que sur les sorties de stock rattachées aux OT.

Conventions retenues :

* **MTTR** = temps d'arrêt total ÷ nombre d'interventions correctives terminées ;
* **MTBF** = (durée de la fenêtre − temps d'arrêt) ÷ nombre d'interventions ;
* **disponibilité** = 1 − temps d'arrêt ÷ (durée de la fenêtre × nb d'équipements),
  bornée entre 0 et 1 ;
* **panne récurrente** = au moins 3 interventions correctives terminées sur
  les 12 derniers mois.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import StockMovementType, WorkOrderStatus
from app.models.equipment import Equipment
from app.models.spare_part import SparePart, StockMovement
from app.models.work_order import WorkOrder
from app.schemas.analytics import (
    AnalyticsSummary,
    CostLine,
    DashboardAlerts,
    EquipmentKpi,
    InterventionAlert,
    OverdueWorkOrderAlert,
)
from app.services.clock import today

PERIOD_CHOICES = (30, 90, 365)
DEFAULT_PERIOD = 365
RECURRENT_THRESHOLD = 3
RECURRENT_DAYS = 365


def normalize_period(days: int | None) -> int:
    """Ramène la période demandée à une valeur supportée par l'interface."""
    if days in PERIOD_CHOICES:
        return int(days)
    return DEFAULT_PERIOD


class AnalyticsService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------ synthèse
    def summary(self, days: int | None = DEFAULT_PERIOD, site_id: int | None = None) -> AnalyticsSummary:
        """Calcule les indicateurs de tous les équipements actifs."""
        days = normalize_period(days)
        end_date = today()
        start_date = end_date - timedelta(days=days - 1)
        window_minutes = days * 24 * 60
        twelve_months_start = end_date - timedelta(days=RECURRENT_DAYS - 1)

        equipment_stmt = select(Equipment).where(Equipment.is_active.is_(True))
        if site_id is not None:
            equipment_stmt = equipment_stmt.where(Equipment.site_id == site_id)
        equipments = list(self.db.scalars(equipment_stmt.order_by(Equipment.code)).all())
        equipment_ids = {item.id for item in equipments}

        # Interventions correctives terminées sur la fenêtre demandée.
        window_orders = self._completed_corrective(start_date, end_date, equipment_ids)
        # Interventions correctives terminées sur 12 mois (récurrence).
        recurrent_orders = (
            window_orders
            if start_date <= twelve_months_start
            else self._completed_corrective(twelve_months_start, end_date, equipment_ids)
        )

        buckets: dict[int, dict[str, object]] = {
            equipment.id: {
                "failures": 0,
                "downtime": 0,
                "last_failure": None,
            }
            for equipment in equipments
        }
        for work_order in window_orders:
            bucket = buckets.get(work_order.equipment_id)
            if bucket is None:
                continue
            bucket["failures"] = int(bucket["failures"]) + 1
            duration = work_order.intervention_duration_minutes
            if duration is not None:
                bucket["downtime"] = int(bucket["downtime"]) + duration
            ended_on = self._ended_on(work_order)
            if ended_on is not None and (
                bucket["last_failure"] is None or ended_on > bucket["last_failure"]
            ):
                bucket["last_failure"] = ended_on

        recurrent_counts: dict[int, int] = {}
        recurrent_last: dict[int, date | None] = {}
        for work_order in recurrent_orders:
            recurrent_counts[work_order.equipment_id] = (
                recurrent_counts.get(work_order.equipment_id, 0) + 1
            )
            ended_on = self._ended_on(work_order)
            if ended_on is not None and (
                recurrent_last.get(work_order.equipment_id) is None
                or ended_on > recurrent_last[work_order.equipment_id]
            ):
                recurrent_last[work_order.equipment_id] = ended_on

        # Coûts pièces : sorties de stock rattachées à un OT sur la fenêtre.
        work_order_costs = self._work_order_costs(start_date, end_date)
        equipment_costs: dict[int, Decimal] = {}
        cost_orders = self._work_orders_by_id(set(work_order_costs))
        for work_order_id, cost in work_order_costs.items():
            work_order = cost_orders.get(work_order_id)
            if work_order is None or work_order.equipment_id not in equipment_ids:
                continue
            equipment_costs[work_order.equipment_id] = (
                equipment_costs.get(work_order.equipment_id, Decimal("0")) + cost
            )

        rows: list[EquipmentKpi] = []
        for equipment in equipments:
            bucket = buckets[equipment.id]
            failures = int(bucket["failures"])
            downtime = int(bucket["downtime"])
            mttr = downtime / failures if failures else None
            mtbf = (window_minutes - downtime) / failures if failures else None
            if mtbf is not None:
                mtbf = max(0.0, mtbf)
            availability = 1 - (downtime / window_minutes) if window_minutes else None
            if availability is not None:
                availability = min(1.0, max(0.0, availability))
            failures_12m = recurrent_counts.get(equipment.id, 0)
            last_failure = bucket["last_failure"] or recurrent_last.get(equipment.id)
            rows.append(
                EquipmentKpi(
                    equipment_id=equipment.id,
                    equipment_code=equipment.code,
                    equipment_name=equipment.name,
                    site_code=equipment.site.code if equipment.site else None,
                    failure_count=failures,
                    failure_count_12m=failures_12m,
                    downtime_minutes=downtime,
                    mttr_minutes=mttr,
                    mtbf_minutes=mtbf,
                    availability=availability,
                    parts_cost=equipment_costs.get(equipment.id, Decimal("0")),
                    last_failure_on=last_failure,
                    recurrent=failures_12m >= RECURRENT_THRESHOLD,
                )
            )

        rows.sort(key=lambda row: (row.availability if row.availability is not None else 1.0, row.equipment_code))

        total_failures = sum(row.failure_count for row in rows)
        total_downtime = sum(row.downtime_minutes for row in rows)
        total_cost = sum((row.parts_cost for row in rows), Decimal("0"))
        global_mttr = total_downtime / total_failures if total_failures else None
        if equipments:
            global_availability = 1 - total_downtime / (window_minutes * len(equipments))
            global_availability = min(1.0, max(0.0, global_availability))
        else:
            global_availability = None

        cost_lines: list[CostLine] = []
        for work_order_id, cost in work_order_costs.items():
            work_order = cost_orders.get(work_order_id)
            if work_order is None:
                continue
            if site_id is not None and work_order.equipment.site_id != site_id:
                continue
            cost_lines.append(
                CostLine(
                    work_order_id=work_order.id,
                    code=work_order.code,
                    equipment_id=work_order.equipment_id,
                    equipment_code=work_order.equipment_code or "",
                    equipment_name=work_order.equipment_name or "",
                    is_corrective=work_order.is_corrective,
                    parts_cost=cost,
                )
            )
        cost_lines.sort(key=lambda line: (-line.parts_cost, line.code))

        return AnalyticsSummary(
            days=days,
            start_date=start_date,
            end_date=end_date,
            equipment_count=len(equipments),
            total_failures=total_failures,
            total_downtime_minutes=total_downtime,
            global_mttr_minutes=global_mttr,
            global_availability=global_availability,
            total_parts_cost=total_cost,
            equipment=rows,
            cost_lines=cost_lines,
        )

    def kpi_for(self, equipment_id: int, days: int | None = DEFAULT_PERIOD) -> EquipmentKpi | None:
        """Indicateurs d'un équipement, réutilisés sur sa fiche détaillée."""
        summary = self.summary(days=days)
        for row in summary.equipment:
            if row.equipment_id == equipment_id:
                return row
        return None

    def parts_cost(self, work_order_id: int) -> Decimal:
        """Coût des pièces consommées sur un OT, sur toute sa durée de vie."""
        cost_expression = func.coalesce(StockMovement.unit_cost, SparePart.unit_cost)
        total = self.db.scalar(
            select(func.sum(cost_expression * StockMovement.quantity))
            .join(SparePart, SparePart.id == StockMovement.spare_part_id)
            .where(StockMovement.work_order_id == work_order_id)
            .where(StockMovement.movement_type == StockMovementType.EXIT.value)
        )
        return Decimal(str(total)) if total is not None else Decimal("0")

    # ------------------------------------------------------------------- alertes
    def alerts(
        self,
        threshold_days: int = 3,
        limit: int = 10,
    ) -> DashboardAlerts:
        """Alertes d'exploitation : demandes non affectées et OT en retard."""
        threshold_days = max(0, int(threshold_days))
        limit = max(1, int(limit))
        current_date = today()
        cutoff = current_date - timedelta(days=threshold_days)

        unassigned_orders = list(
            self.db.scalars(
                select(WorkOrder)
                .where(WorkOrder.is_corrective.is_(True))
                .where(WorkOrder.assigned_to_id.is_(None))
                .where(WorkOrder.status == WorkOrderStatus.OPEN.value)
                .where(WorkOrder.created_at <= datetime.combine(cutoff, time.max))
                .order_by(WorkOrder.created_at)
            ).all()
        )
        unassigned = []
        for work_order in unassigned_orders[:limit]:
            created_on = work_order.created_at.date()
            unassigned.append(
                InterventionAlert(
                    work_order_id=work_order.id,
                    code=work_order.code,
                    equipment_code=work_order.equipment_code or "",
                    equipment_name=work_order.equipment_name or "",
                    description=work_order.description,
                    created_on=created_on,
                    age_days=max(0, (current_date - created_on).days),
                )
            )

        overdue_orders = list(
            self.db.scalars(
                select(WorkOrder)
                .where(WorkOrder.is_corrective.is_(False))
                .where(WorkOrder.due_date.is_not(None))
                .where(WorkOrder.due_date < current_date)
                .where(
                    WorkOrder.status.not_in(
                        [
                            WorkOrderStatus.DONE.value,
                            WorkOrderStatus.CANCELLED.value,
                        ]
                    )
                )
                .order_by(WorkOrder.due_date, WorkOrder.code)
            ).all()
        )
        overdue = []
        for work_order in overdue_orders[:limit]:
            overdue.append(
                OverdueWorkOrderAlert(
                    work_order_id=work_order.id,
                    code=work_order.code,
                    equipment_code=work_order.equipment_code or "",
                    equipment_name=work_order.equipment_name or "",
                    due_date=work_order.due_date,
                    days_late=max(0, (current_date - work_order.due_date).days),
                    status_label=work_order.status_label,
                    priority_label=work_order.priority_label,
                )
            )

        return DashboardAlerts(
            threshold_days=threshold_days,
            unassigned=unassigned,
            overdue_work_orders=overdue,
        )

    # ------------------------------------------------------------------- interne
    def _completed_corrective(
        self,
        start_date: date,
        end_date: date,
        equipment_ids: set[int],
    ) -> list[WorkOrder]:
        if not equipment_ids:
            return []
        stmt = (
            select(WorkOrder)
            .where(WorkOrder.is_corrective.is_(True))
            .where(WorkOrder.status == WorkOrderStatus.DONE.value)
            .where(WorkOrder.intervention_ended_at.is_not(None))
            .where(WorkOrder.equipment_id.in_(equipment_ids))
            .where(
                WorkOrder.intervention_ended_at
                >= datetime.combine(start_date, time.min)
            )
            .where(
                WorkOrder.intervention_ended_at
                < datetime.combine(end_date + timedelta(days=1), time.min)
            )
            .order_by(WorkOrder.intervention_ended_at)
        )
        return list(self.db.scalars(stmt).all())

    def _work_order_costs(self, start_date: date, end_date: date) -> dict[int, Decimal]:
        cost_expression = func.coalesce(StockMovement.unit_cost, SparePart.unit_cost)
        stmt = (
            select(
                StockMovement.work_order_id,
                func.sum(cost_expression * StockMovement.quantity),
            )
            .join(SparePart, SparePart.id == StockMovement.spare_part_id)
            .where(StockMovement.movement_type == StockMovementType.EXIT.value)
            .where(StockMovement.work_order_id.is_not(None))
            .where(StockMovement.movement_date >= start_date)
            .where(StockMovement.movement_date <= end_date)
            .group_by(StockMovement.work_order_id)
        )
        costs: dict[int, Decimal] = {}
        for work_order_id, total in self.db.execute(stmt).all():
            if work_order_id is None or total is None:
                continue
            costs[int(work_order_id)] = Decimal(str(total))
        return costs

    def _work_orders_by_id(self, work_order_ids: set[int]) -> dict[int, WorkOrder]:
        if not work_order_ids:
            return {}
        orders = self.db.scalars(
            select(WorkOrder).where(WorkOrder.id.in_(work_order_ids))
        ).all()
        return {work_order.id: work_order for work_order in orders}

    @staticmethod
    def _ended_on(work_order: WorkOrder) -> date | None:
        if work_order.intervention_ended_at is None:
            return None
        return work_order.intervention_ended_at.date()
