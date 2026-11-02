"""Service des ordres de travail (OT) ouverts."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.errors import ConflictError, NotFoundError, ValidationError
from app.models.enums import AuditAction, WorkOrderPriority, WorkOrderStatus
from app.models.equipment import Equipment
from app.models.user import User
from app.models.work_order import WorkOrder
from app.repositories.user import UserRepository
from app.repositories.work_order import WorkOrderRepository
from app.schemas.work_order import WorkOrderAssignment, WorkOrderCreate, WorkOrderStatusUpdate
from app.services.audit_service import AuditService
from app.services.clock import today
from app.services.maintenance_schedule_service import MaintenanceScheduleService

GENERATABLE_STATUSES = {
    "overdue",
    "due_today",
    "due_soon",
    "hours_due_soon",
    "hours_overdue",
}


class WorkOrderService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = WorkOrderRepository(db)
        self.user_repository = UserRepository(db)
        self.schedule_service = MaintenanceScheduleService(db)
        self.audit = AuditService(db)

    # ------------------------------------------------------------------ lecture
    def list(
        self,
        *,
        status: str | None = None,
        assigned_to_id: int | None = None,
        search: str | None = None,
        open_only: bool = False,
        corrective: bool | None = None,
    ) -> list[WorkOrder]:
        return self.repository.list(
            status=status,
            assigned_to_id=assigned_to_id,
            search=search,
            open_only=open_only,
            corrective=corrective,
        )

    def get(self, work_order_id: int) -> WorkOrder:
        work_order = self.repository.get(work_order_id)
        if work_order is None:
            raise NotFoundError(f"Ordre de travail {work_order_id} introuvable.")
        return work_order

    # ----------------------------------------------------------------- écriture
    def create(
        self,
        payload: WorkOrderCreate,
        actor: User | None = None,
    ) -> WorkOrder:
        if payload.assigned_to_id is not None:
            self._check_assignee(payload.assigned_to_id)
        sequence = self.repository.next_number()
        code = f"OT-{today().year}-{sequence:04d}"
        while self.repository.get_by_code(code):
            sequence += 1
            code = f"OT-{today().year}-{sequence:04d}"
        status = (
            WorkOrderStatus.ASSIGNED.value
            if payload.assigned_to_id is not None
            else WorkOrderStatus.OPEN.value
        )
        work_order = WorkOrder(
            code=code,
            equipment_id=payload.equipment_id,
            periodic_maintenance_id=payload.periodic_maintenance_id,
            assigned_to_id=payload.assigned_to_id,
            created_by_id=actor.id if actor else None,
            status=status,
            priority=payload.priority.value,
            due_date=payload.due_date,
            due_operating_hours=payload.due_operating_hours,
            description=payload.description,
            notes=payload.notes,
        )
        work_order = self.repository.add(work_order)
        self.audit.record(
            AuditAction.CREATE,
            "work_order",
            work_order.id,
            actor=actor,
            payload={"code": work_order.code, "equipment_id": work_order.equipment_id},
        )
        return work_order

    def generate_from_schedule(
        self,
        *,
        assigned_to_id: int | None = None,
        actor: User | None = None,
    ) -> tuple[list[WorkOrder], int]:
        """Crée un OT pour chaque échéance à traiter, sans doublon ouvert."""
        if assigned_to_id is not None:
            self._check_assignee(assigned_to_id)

        created: list[WorkOrder] = []
        skipped = 0
        for row in self.schedule_service.rows():
            if row.status not in GENERATABLE_STATUSES:
                continue
            existing = self.repository.list_open_for(
                row.equipment_id, row.periodic_maintenance_id
            )
            if existing:
                skipped += 1
                continue
            priority = WorkOrderPriority.NORMAL
            if row.status in {"overdue", "hours_overdue"}:
                priority = WorkOrderPriority.HIGH
            equipment = self.db.get(Equipment, row.equipment_id)
            if equipment is not None and equipment.is_critical:
                priority = WorkOrderPriority.URGENT
            payload = WorkOrderCreate(
                equipment_id=row.equipment_id,
                periodic_maintenance_id=row.periodic_maintenance_id,
                assigned_to_id=assigned_to_id,
                priority=priority,
                due_date=row.due_date,
                due_operating_hours=row.due_operating_hours,
                description=row.operation_label,
            )
            created.append(self.create(payload, actor=actor))
            skipped += 0

        return created, skipped

    def assign(
        self,
        work_order: WorkOrder,
        payload: WorkOrderAssignment,
        actor: User | None = None,
    ) -> WorkOrder:
        if work_order.is_corrective:
            raise ValidationError(
                "Cette demande est une intervention corrective : utilisez sa fiche "
                "d'intervention pour l'affectation."
            )
        if payload.assigned_to_id is not None:
            self._check_assignee(payload.assigned_to_id)
        work_order.assigned_to_id = payload.assigned_to_id
        if work_order.status in (
            WorkOrderStatus.OPEN.value,
            WorkOrderStatus.ASSIGNED.value,
        ):
            work_order.status = (
                WorkOrderStatus.ASSIGNED.value
                if payload.assigned_to_id is not None
                else WorkOrderStatus.OPEN.value
            )
        work_order = self.repository.save(work_order)
        self.audit.record(
            AuditAction.UPDATE,
            "work_order",
            work_order.id,
            actor=actor,
            payload={
                "code": work_order.code,
                "assigned_to_id": str(work_order.assigned_to_id),
            },
        )
        return work_order

    def take(
        self,
        work_order: WorkOrder,
        actor: User,
    ) -> WorkOrder:
        if work_order.is_corrective:
            raise ValidationError(
                "Cette intervention corrective doit être affectée par le "
                "responsable de maintenance."
            )
        if work_order.status in (
            WorkOrderStatus.DONE.value,
            WorkOrderStatus.CANCELLED.value,
        ):
            raise ConflictError("Cet OT est clôturé : il ne peut plus être pris en charge.")
        if work_order.assigned_to_id not in (None, actor.id):
            raise ConflictError("Cet OT est déjà affecté à un autre technicien.")
        return self.assign(
            work_order, WorkOrderAssignment(assigned_to_id=actor.id), actor=actor
        )

    def update_status(
        self,
        work_order: WorkOrder,
        payload: WorkOrderStatusUpdate,
        actor: User | None = None,
    ) -> WorkOrder:
        if work_order.is_corrective:
            raise ValidationError(
                "Cette intervention corrective se pilote depuis sa fiche "
                "d'intervention (démarrage, compte rendu, clôture)."
            )
        new_status = payload.status
        if new_status in (WorkOrderStatus.OPEN, WorkOrderStatus.ASSIGNED):
            work_order.started_at = None
        if new_status is WorkOrderStatus.IN_PROGRESS:
            work_order.started_at = work_order.started_at or today()
        if new_status in (WorkOrderStatus.DONE, WorkOrderStatus.CANCELLED):
            work_order.completed_at = today()
        if new_status is WorkOrderStatus.DONE and work_order.assigned_to_id is None and actor:
            work_order.assigned_to_id = actor.id
        work_order.status = new_status.value
        work_order = self.repository.save(work_order)
        self.audit.record(
            AuditAction.UPDATE,
            "work_order",
            work_order.id,
            actor=actor,
            payload={"code": work_order.code, "status": new_status.value},
        )
        return work_order

    def close_for_execution(
        self,
        equipment_id: int,
        periodic_maintenance_id: int,
        performed_on: date,
        actor: User | None = None,
    ) -> int:
        """Clôture les OT ouverts correspondant à une réalisation enregistrée."""
        closed = 0
        for work_order in self.repository.list_open_for(
            equipment_id, periodic_maintenance_id
        ):
            work_order.status = WorkOrderStatus.DONE.value
            work_order.completed_at = performed_on
            self.repository.save(work_order)
            self.audit.record(
                AuditAction.UPDATE,
                "work_order",
                work_order.id,
                actor=actor,
                payload={"code": work_order.code, "status": "done", "via": "execution"},
            )
            closed += 1
        return closed

    # ------------------------------------------------------------------ interne
    def _check_assignee(self, user_id: int) -> None:
        user = self.user_repository.get(user_id)
        if user is None:
            raise NotFoundError(f"Utilisateur {user_id} introuvable.")
        if not user.is_active:
            raise ValidationError("Un OT ne peut pas être affecté à un utilisateur inactif.")
