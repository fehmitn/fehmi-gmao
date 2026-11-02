"""Service de l'échéancier de maintenance périodique.

L'échéancier est une projection théorique calculée depuis l'ancrage de chaque
règle. Les réalisations d'OT ne déplacent pas les échéances : elles servent à
savoir si l'occurrence théorique la plus récente a été couverte et à logger le
retard réel **par rapport au référentiel**.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.enums import MaintenanceIntervalUnit
from app.models.equipment import Equipment
from app.models.equipment_location import EquipmentLocation
from app.models.maintenance_execution import MaintenanceExecution
from app.models.periodic_maintenance import PeriodicMaintenance
from app.models.site import Site
from app.repositories.equipment_location import EquipmentLocationRepository
from app.repositories.location import LocationRepository
from app.repositories.maintenance_execution import MaintenanceExecutionRepository
from app.repositories.periodic_maintenance import PeriodicMaintenanceRepository
from app.schemas.maintenance_schedule import (
    MaintenanceScheduleRow,
    MaintenanceScheduleSummary,
)
from app.services.clock import today
from app.services.periodicity import (
    next_due_date,
    periodicity_label,
    previous_due_date,
    resolve_anchor_date,
)

STATUS_LABELS = {
    "overdue": "En retard",
    "due_today": "Échéance aujourd'hui",
    "due_soon": "Sous 30 jours",
    "upcoming": "À venir",
    "no_anchor": "Ancrage indisponible",
    "hours_waiting": "En attente du compteur",
    "hours_due_soon": "Contrôle des heures à planifier",
    "hours_overdue": "Seuil d'heures dépassé",
    "hours_no_reading": "Relevé d'heures requis",
}

STATUS_CSS = {
    "overdue": "text-bg-danger",
    "due_today": "text-bg-warning",
    "due_soon": "text-bg-warning",
    "upcoming": "text-bg-secondary",
    "no_anchor": "text-bg-dark",
    "hours_waiting": "text-bg-secondary",
    "hours_due_soon": "text-bg-warning",
    "hours_overdue": "text-bg-danger",
    "hours_no_reading": "text-bg-dark",
}

HOURS_WARNING_THRESHOLD = 10


class MaintenanceScheduleService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.rule_repository = PeriodicMaintenanceRepository(db)
        self.execution_repository = MaintenanceExecutionRepository(db)
        self.placement_repository = EquipmentLocationRepository(db)
        self.location_repository = LocationRepository(db)

    # ------------------------------------------------------------------ lecture
    def summary(
        self,
        *,
        site_id: int | None = None,
        equipment_type_id: int | None = None,
        supplier_id: int | None = None,
        horizon_days: int | None = None,
        search: str | None = None,
    ) -> MaintenanceScheduleSummary:
        rows = self.rows(
            site_id=site_id,
            equipment_type_id=equipment_type_id,
            supplier_id=supplier_id,
            horizon_days=horizon_days,
            search=search,
        )
        equipment_ids = {row.equipment_id for row in rows}
        rules = {rule.id: rule for rule in self.rule_repository.list_all()}
        late_executions = 0
        for execution in self.execution_repository.list_all():
            if (
                execution.delay_days is None
                or execution.delay_days <= 0
                or execution.equipment_id not in equipment_ids
            ):
                continue
            rule = rules.get(execution.periodic_maintenance_id)
            if supplier_id is not None and (rule is None or rule.supplier_id != supplier_id):
                continue
            late_executions += 1

        return MaintenanceScheduleSummary(
            total=len(rows),
            overdue_count=sum(
                1 for row in rows if row.status in ("overdue", "hours_overdue")
            ),
            due_soon_count=sum(
                1
                for row in rows
                if row.status in ("due_today", "due_soon", "hours_due_soon")
            ),
            no_anchor_count=sum(1 for row in rows if row.status == "no_anchor"),
            late_execution_count=late_executions,
            hours_based_count=sum(1 for row in rows if row.is_hour_based),
            hours_waiting_count=sum(
                1 for row in rows if row.status == "hours_waiting"
            ),
            hours_no_reading_count=sum(
                1 for row in rows if row.status == "hours_no_reading"
            ),
            rows=rows,
        )

    def rows(
        self,
        *,
        site_id: int | None = None,
        equipment_type_id: int | None = None,
        supplier_id: int | None = None,
        horizon_days: int | None = None,
        search: str | None = None,
        equipment_id: int | None = None,
    ) -> list[MaintenanceScheduleRow]:
        reference_day = today()
        equipments = self._equipments(
            site_id=site_id,
            equipment_type_id=equipment_type_id,
            search=search,
            equipment_id=equipment_id,
        )
        rules_by_type: dict[int, list[PeriodicMaintenance]] = {}
        for rule in self.rule_repository.list_all(active_only=True):
            if supplier_id is not None and rule.supplier_id != supplier_id:
                continue
            rules_by_type.setdefault(rule.equipment_type_id, []).append(rule)

        first_placements = self.placement_repository.first_placement_dates()
        current_placements = {
            placement.equipment_id: placement
            for placement in self.placement_repository.open_placements()
        }
        last_executions: dict[tuple[int, int], MaintenanceExecution] = {}
        for execution in self.execution_repository.list_all():
            key = (execution.equipment_id, execution.periodic_maintenance_id)
            last_executions.setdefault(key, execution)

        rows: list[MaintenanceScheduleRow] = []
        for equipment in equipments:
            if not equipment.equipment_type_id:
                continue
            for rule in rules_by_type.get(equipment.equipment_type_id, []):
                row = self._build_row(
                    equipment,
                    rule,
                    reference_day,
                    first_placement_date=first_placements.get(equipment.id),
                    current_placement=current_placements.get(equipment.id),
                    last_execution=last_executions.get((equipment.id, rule.id)),
                )
                if horizon_days is not None:
                    if row.days_remaining is None:
                        rows.append(row)
                    elif row.days_remaining <= horizon_days:
                        rows.append(row)
                else:
                    rows.append(row)

        def sort_key(row: MaintenanceScheduleRow):
            if row.is_hour_based:
                return (
                    1,
                    row.hours_remaining is None,
                    -(row.hours_remaining or 0),
                    row.equipment_code,
                    row.operation_code,
                )
            return (
                0,
                row.due_date is None,
                row.due_date or date.max,
                row.equipment_code,
                row.operation_code,
            )

        rows.sort(key=sort_key)
        return rows

    def for_equipment(self, equipment: Equipment) -> list[MaintenanceScheduleRow]:
        return self.rows(equipment_id=equipment.id)

    # ------------------------------------------------------------------ interne
    def _equipments(
        self,
        *,
        site_id: int | None,
        equipment_type_id: int | None,
        search: str | None,
        equipment_id: int | None,
    ) -> list[Equipment]:
        conditions = [
            Equipment.is_active.is_(True),
            Equipment.equipment_type_id.is_not(None),
        ]
        if equipment_id is not None:
            conditions.append(Equipment.id == equipment_id)
        if site_id is not None:
            conditions.append(Equipment.site_id == site_id)
        if equipment_type_id is not None:
            conditions.append(Equipment.equipment_type_id == equipment_type_id)
        if search:
            pattern = f"%{search.strip()}%"
            conditions.append(
                or_(
                    Equipment.code.ilike(pattern),
                    Equipment.name.ilike(pattern),
                    Equipment.serial_number.ilike(pattern),
                )
            )
        stmt = select(Equipment).where(*conditions).order_by(Equipment.code)
        return list(self.db.scalars(stmt).all())

    def _build_row(
        self,
        equipment: Equipment,
        rule: PeriodicMaintenance,
        reference_day: date,
        *,
        first_placement_date: date | None,
        current_placement: EquipmentLocation | None,
        last_execution: MaintenanceExecution | None,
    ) -> MaintenanceScheduleRow:
        equipment_type = rule.equipment_type
        is_hour_based = rule.interval_unit == MaintenanceIntervalUnit.HOURS.value

        value = {
            "equipment_id": equipment.id,
            "equipment_code": equipment.code,
            "equipment_name": equipment.name,
            "site_id": equipment.site_id,
            "site_code": getattr(equipment, "site_code", None) or self._site_code(equipment.site_id),
            "site_name": getattr(equipment, "site_name", None) or self._site_name(equipment.site_id),
            "location_code": None,
            "location_name": None,
            "equipment_type_id": rule.equipment_type_id,
            "equipment_type_code": equipment_type.code if equipment_type else None,
            "equipment_type_name": equipment_type.name if equipment_type else None,
            "periodic_maintenance_id": rule.id,
            "operation_code": rule.code,
            "operation_label": rule.label,
            "periodicity_label": periodicity_label(rule.interval_value, rule.interval_unit),
            "maintenance_type_label": rule.maintenance_type_label,
            "tolerance_days": rule.tolerance_days,
            "estimated_duration_minutes": rule.estimated_duration_minutes,
            "supplier_id": rule.supplier_id,
            "supplier_name": rule.supplier.name if rule.supplier else None,
            "anchor_date": None,
            "previous_due_date": None,
            "next_due_date": None,
            "due_date": None,
            "days_remaining": None,
            "status": "no_anchor",
            "status_label": STATUS_LABELS["no_anchor"],
            "status_css": STATUS_CSS["no_anchor"],
            "last_performed_on": last_execution.performed_on if last_execution else None,
            "last_delay_days": last_execution.delay_days if last_execution else None,
            "last_delay_label": last_execution.delay_label if last_execution else None,
            "is_hour_based": is_hour_based,
            "current_operating_hours": equipment.operating_hours,
            "due_operating_hours": None,
            "hours_remaining": None,
            "last_performed_hours": last_execution.operating_hours if last_execution else None,
        }
        if current_placement is not None:
            location = self.location_repository.get(current_placement.location_id)
            value["location_code"] = location.code if location else None
            value["location_name"] = location.name if location else None

        if is_hour_based:
            current_hours = equipment.operating_hours
            if current_hours is None:
                value["status"] = "hours_no_reading"
                value["status_label"] = STATUS_LABELS["hours_no_reading"]
                value["status_css"] = STATUS_CSS["hours_no_reading"]
                return MaintenanceScheduleRow(**value)
            interval = rule.interval_value
            if last_execution and last_execution.operating_hours is not None:
                # Après une réalisation, le cycle suivant repart du relevé saisi.
                due_hours = last_execution.operating_hours + interval
            else:
                # Premier cycle : on part du relevé initial et on saute les seuils
                # déjà franchis (machine ancienne reprise dans le GMAO).
                baseline = equipment.initial_operating_hours or 0
                elapsed = max(current_hours - baseline, 0)
                reached = elapsed // interval
                if elapsed > 0 and elapsed % interval == 0:
                    due_hours = current_hours
                else:
                    due_hours = baseline + (reached + 1) * interval
            value["due_operating_hours"] = due_hours
            hours_remaining = due_hours - current_hours
            value["hours_remaining"] = hours_remaining
            if hours_remaining <= 0:
                value["status"] = "hours_overdue"
                value["status_label"] = STATUS_LABELS["hours_overdue"]
                value["status_css"] = STATUS_CSS["hours_overdue"]
            elif hours_remaining <= HOURS_WARNING_THRESHOLD:
                value["status"] = "hours_due_soon"
                value["status_label"] = STATUS_LABELS["hours_due_soon"]
                value["status_css"] = STATUS_CSS["hours_due_soon"]
            else:
                value["status"] = "hours_waiting"
                value["status_label"] = STATUS_LABELS["hours_waiting"]
                value["status_css"] = STATUS_CSS["hours_waiting"]
            return MaintenanceScheduleRow(**value)

        anchor = resolve_anchor_date(
            rule.anchor,
            fixed_date=rule.fixed_date,
            commissioning_date=equipment.commissioning_date,
            first_placement_date=first_placement_date,
        )
        value["anchor_date"] = anchor
        if anchor is None:
            return MaintenanceScheduleRow(**value)

        previous = previous_due_date(
            anchor,
            rule.interval_value,
            rule.interval_unit,
            reference_day,
            anchor_kind=rule.anchor,
        )
        following = next_due_date(
            anchor,
            rule.interval_value,
            rule.interval_unit,
            reference_day,
            anchor_kind=rule.anchor,
        )
        value["previous_due_date"] = previous
        value["next_due_date"] = following

        covered = (
            last_execution is not None
            and previous is not None
            and last_execution.theoretical_due_date is not None
            and last_execution.theoretical_due_date >= previous
        )
        if previous is not None and not covered:
            lateness = (reference_day - previous).days
            value["due_date"] = previous
            value["days_remaining"] = -lateness
            if lateness > rule.tolerance_days:
                value["status"] = "overdue"
                value["status_label"] = STATUS_LABELS["overdue"]
                value["status_css"] = STATUS_CSS["overdue"]
            else:
                value["status"] = "due_soon"
                value["status_label"] = "Dans la tolérance"
                value["status_css"] = STATUS_CSS["due_soon"]
        else:
            days_remaining = (following - reference_day).days
            value["due_date"] = following
            value["days_remaining"] = days_remaining
            if days_remaining == 0:
                value["status"] = "due_today"
                value["status_label"] = STATUS_LABELS["due_today"]
            elif days_remaining <= 30:
                value["status"] = "due_soon"
                value["status_label"] = STATUS_LABELS["due_soon"]
            else:
                value["status"] = "upcoming"
                value["status_label"] = STATUS_LABELS["upcoming"]
            value["status_css"] = STATUS_CSS[value["status"]]

        return MaintenanceScheduleRow(**value)

    def _site_code(self, site_id: int) -> str | None:
        site = self.db.get(Site, site_id)
        return site.code if site else None

    def _site_name(self, site_id: int) -> str | None:
        site = self.db.get(Site, site_id)
        return site.name if site else None
