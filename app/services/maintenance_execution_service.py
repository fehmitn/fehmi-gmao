"""Service de saisie des réalisations d'ordres de travail."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.errors import FutureDateNotAllowed, NotFoundError, ValidationError
from app.models.enums import AuditAction, MaintenanceIntervalUnit
from app.models.equipment import Equipment
from app.models.maintenance_execution import MaintenanceExecution
from app.models.periodic_maintenance import PeriodicMaintenance
from app.models.user import User
from app.repositories.equipment import EquipmentRepository
from app.repositories.equipment_location import EquipmentLocationRepository
from app.repositories.maintenance_execution import MaintenanceExecutionRepository
from app.repositories.maintenance_supplier import MaintenanceSupplierRepository
from app.repositories.periodic_maintenance import PeriodicMaintenanceRepository
from app.repositories.user import UserRepository
from app.schemas.maintenance_execution import (
    MaintenanceExecutionCreate,
    MaintenanceExecutionRead,
)
from app.services.audit_service import AuditService
from app.services.clock import today
from app.services.periodicity import reference_due_date, resolve_anchor_date


class MaintenanceExecutionService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = MaintenanceExecutionRepository(db)
        self.equipment_repository = EquipmentRepository(db)
        self.rule_repository = PeriodicMaintenanceRepository(db)
        self.placement_repository = EquipmentLocationRepository(db)
        self.supplier_repository = MaintenanceSupplierRepository(db)
        self.user_repository = UserRepository(db)
        self.audit = AuditService(db)

    def list_for_equipment(self, equipment_id: int) -> list[MaintenanceExecution]:
        executions = self.repository.list_by_equipment(equipment_id)
        return [self.enrich(execution) for execution in executions]

    def list_for_rule(self, maintenance_id: int) -> list[MaintenanceExecution]:
        executions = self.repository.list_by_rule(maintenance_id)
        return [self.enrich(execution) for execution in executions]

    def create(
        self,
        equipment: Equipment,
        rule: PeriodicMaintenance,
        payload: MaintenanceExecutionCreate,
        actor: User | None = None,
    ) -> MaintenanceExecution:
        if not rule.is_active:
            raise ValidationError(
                f"La maintenance '{rule.code}' est inactive : aucune réalisation "
                "ne peut être enregistrée."
            )
        if equipment.equipment_type_id != rule.equipment_type_id:
            raise ValidationError(
                f"La maintenance '{rule.code}' n'appartient pas à la famille de "
                f"l'équipement {equipment.code}."
            )

        is_hour_based = rule.interval_unit == MaintenanceIntervalUnit.HOURS.value

        if is_hour_based:
            performed_on = payload.performed_on or today()
            if performed_on > today():
                raise FutureDateNotAllowed(performed_on.isoformat())
            hours = payload.operating_hours if payload.operating_hours is not None else equipment.operating_hours
            if hours is None:
                raise ValidationError(
                    "Un relevé du compteur horaire est requis pour une maintenance en heures de fonctionnement."
                )
            if hours < 0:
                raise ValidationError("Le relevé horaire doit être positif.")

            performed_by_id = payload.performed_by_id
            if performed_by_id is not None and self.user_repository.get(performed_by_id) is None:
                raise NotFoundError(f"Utilisateur {performed_by_id} introuvable.")
            if performed_by_id is None and actor is not None:
                performed_by_id = actor.id

            execution = MaintenanceExecution(
                equipment_id=equipment.id,
                periodic_maintenance_id=rule.id,
                performed_on=performed_on,
                theoretical_due_date=None,
                delay_days=None,
                performed_by_id=performed_by_id,
                notes=payload.notes,
                operating_hours=hours,
            )
            execution = self.repository.add(execution)
            if equipment.operating_hours is None or hours > equipment.operating_hours:
                equipment.operating_hours = hours
                self.db.add(equipment)
            self.audit.record(
                AuditAction.EXECUTE,
                "maintenance_execution",
                execution.id,
                actor=actor,
                payload={
                    "equipment": equipment.code,
                    "maintenance": rule.code,
                    "performed_on": performed_on.isoformat(),
                    "operating_hours": str(hours),
                },
            )
            self._close_open_work_orders(equipment, rule, performed_on, actor)
            return self.enrich(execution)

        if payload.performed_on is None:
            raise ValueError("La date de réalisation est obligatoire.")
        if payload.performed_on > today():
            raise FutureDateNotAllowed(payload.performed_on.isoformat())

        anchor = self._anchor_for(equipment, rule)
        if anchor is None:
            raise ValidationError(
                f"Impossible de calculer l'échéance de '{rule.code}' : l'équipement "
                f"{equipment.code} n'a ni date de mise en service ni implantation."
            )
        reference = reference_due_date(
            anchor,
            rule.interval_value,
            rule.interval_unit,
            payload.performed_on,
            anchor_kind=rule.anchor,
        )
        delay_days = (payload.performed_on - reference).days

        performed_by_id = payload.performed_by_id
        if performed_by_id is not None and self.user_repository.get(performed_by_id) is None:
            raise NotFoundError(f"Utilisateur {performed_by_id} introuvable.")
        if performed_by_id is None and actor is not None:
            performed_by_id = actor.id

        execution = MaintenanceExecution(
            equipment_id=equipment.id,
            periodic_maintenance_id=rule.id,
            performed_on=payload.performed_on,
            theoretical_due_date=reference,
            delay_days=delay_days,
            performed_by_id=performed_by_id,
            notes=payload.notes,
            operating_hours=payload.operating_hours,
        )
        if payload.operating_hours is not None:
            if equipment.operating_hours is None or payload.operating_hours > equipment.operating_hours:
                equipment.operating_hours = payload.operating_hours
                self.db.add(equipment)
        execution = self.repository.add(execution)
        self.audit.record(
            AuditAction.EXECUTE,
            "maintenance_execution",
            execution.id,
            actor=actor,
            payload={
                "equipment": equipment.code,
                "maintenance": rule.code,
                "performed_on": payload.performed_on.isoformat(),
                "theoretical_due_date": reference.isoformat(),
                "delay_days": str(delay_days),
            },
        )
        self._close_open_work_orders(
            equipment, rule, payload.performed_on, actor
        )
        return self.enrich(execution)

    def _close_open_work_orders(
        self,
        equipment: Equipment,
        rule: PeriodicMaintenance,
        performed_on: date,
        actor: User | None,
    ) -> None:
        """Une réalisation clôture automatiquement l'OT ouvert correspondant."""
        from app.services.work_order_service import WorkOrderService

        WorkOrderService(self.db).close_for_execution(
            equipment.id, rule.id, performed_on, actor=actor
        )

    def _anchor_for(
        self, equipment: Equipment, rule: PeriodicMaintenance
    ) -> date | None:
        placements = self.placement_repository.list_for_equipment(equipment.id)
        first_placement = (
            min(placement.effective_from for placement in placements)
            if placements
            else None
        )
        return resolve_anchor_date(
            rule.anchor,
            fixed_date=rule.fixed_date,
            commissioning_date=equipment.commissioning_date,
            first_placement_date=first_placement,
        )

    def enrich(self, execution: MaintenanceExecution) -> MaintenanceExecution:
        equipment = self.equipment_repository.get(execution.equipment_id)
        execution.equipment_code = equipment.code if equipment else None
        execution.equipment_name = equipment.name if equipment else None

        rule = self.rule_repository.get(execution.periodic_maintenance_id)
        execution.maintenance_code = rule.code if rule else None
        execution.maintenance_label = rule.label if rule else None
        supplier = (
            self.supplier_repository.get(rule.supplier_id)
            if rule is not None and rule.supplier_id
            else None
        )
        execution.supplier_name = supplier.name if supplier else None

        performed_by = (
            self.user_repository.get(execution.performed_by_id)
            if execution.performed_by_id
            else None
        )
        execution.performed_by_name = (
            performed_by.display_name if performed_by else None
        )
        return execution


def to_read(execution: MaintenanceExecution) -> MaintenanceExecutionRead:
    """Convertit une réalisation enrichie en contrat API."""
    return MaintenanceExecutionRead.model_validate(execution)
