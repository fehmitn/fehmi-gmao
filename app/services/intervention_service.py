"""Service de maintenance corrective.

Une demande d'intervention peut être créée par tout utilisateur connecté.
Le responsable de maintenance l'affecte à un technicien, qui saisit ensuite
l'heure de début, l'heure de fin et le compte rendu. Les pièces de rechange
sont d'abord demandées, puis consommées : la sortie de stock n'est créée
qu'au moment de l'utilisation et reste rattachée à l'OT.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.errors import (
    AuthenticationRequiredError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from app.models.enums import (
    AuditAction,
    EquipmentStatus,
    InterventionPartStatus,
    StockMovementType,
    UserRole,
    WorkOrderStatus,
)
from app.models.equipment import Equipment
from app.models.intervention_part import InterventionPart
from app.models.spare_part import SparePart
from app.models.user import User
from app.models.work_order import WorkOrder
from app.repositories.intervention_part import InterventionPartRepository
from app.repositories.user import UserRepository
from app.repositories.work_order import WorkOrderRepository
from app.schemas.intervention import (
    InterventionCancel,
    InterventionFinish,
    InterventionPartCreate,
    InterventionPartUse,
    InterventionRequestCreate,
    InterventionStart,
)
from app.schemas.spare_part import StockMovementCreate
from app.services.audit_service import AuditService
from app.services.clock import now, today
from app.services.spare_part_service import SparePartService

MANAGER_ROLES = {UserRole.RESPONSABLE.value, UserRole.ADMIN.value}
ASSIGNABLE_ROLES = {
    UserRole.TECHNICIEN.value,
    UserRole.RESPONSABLE.value,
    UserRole.ADMIN.value,
}


class InterventionService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = WorkOrderRepository(db)
        self.part_repository = InterventionPartRepository(db)
        self.user_repository = UserRepository(db)
        self.stock_service = SparePartService(db)
        self.audit = AuditService(db)

    # ------------------------------------------------------------------ lecture
    def list(
        self,
        *,
        status: str | None = None,
        assigned_to_id: int | None = None,
        search: str | None = None,
        open_only: bool = False,
    ) -> list[WorkOrder]:
        return self.repository.list(
            status=status,
            assigned_to_id=assigned_to_id,
            search=search,
            open_only=open_only,
            corrective=True,
        )

    def get(self, intervention_id: int) -> WorkOrder:
        work_order = self.repository.get(intervention_id)
        if work_order is None or not work_order.is_corrective:
            raise NotFoundError(f"Intervention {intervention_id} introuvable.")
        return work_order

    def parts(self, intervention_id: int) -> list[InterventionPart]:
        return self.part_repository.list_for(intervention_id)

    def get_part(self, work_order: WorkOrder, part_id: int) -> InterventionPart:
        item = self.part_repository.get(work_order.id, part_id)
        if item is None:
            raise NotFoundError(
                f"Pièce {part_id} introuvable pour l'intervention {work_order.code}."
            )
        return item

    def summary(self) -> dict[str, int]:
        requests = self.list()
        counts = {
            "total": len(requests),
            "open": 0,
            "unassigned": 0,
            "assigned": 0,
            "in_progress": 0,
            "done": 0,
            "cancelled": 0,
        }
        for work_order in requests:
            if work_order.status in counts:
                counts[work_order.status] += 1
            if (
                work_order.status == WorkOrderStatus.OPEN.value
                and work_order.assigned_to_id is None
            ):
                counts["unassigned"] += 1
        return counts

    # ----------------------------------------------------------------- écriture
    def create_request(
        self,
        payload: InterventionRequestCreate,
        actor: User | None = None,
    ) -> WorkOrder:
        actor = self._require_actor(actor)
        equipment = self.db.get(Equipment, payload.equipment_id)
        if equipment is None:
            raise NotFoundError(f"Équipement {payload.equipment_id} introuvable.")
        if not equipment.is_active or equipment.status in (
            EquipmentStatus.RETIRED.value,
            EquipmentStatus.SCRAPPED.value,
        ):
            raise ValidationError(
                "Une demande d'intervention ne peut pas viser un équipement "
                "inactif, réformé ou mis au rebut."
            )
        description = payload.description.strip()
        if not description:
            raise ValidationError("Le symptôme ou la nature de la panne est obligatoire.")

        work_order = WorkOrder(
            code=self._next_code(),
            equipment_id=payload.equipment_id,
            periodic_maintenance_id=None,
            assigned_to_id=None,
            created_by_id=actor.id,
            status=WorkOrderStatus.OPEN.value,
            priority=payload.priority.value,
            due_date=payload.due_date,
            description=description,
            notes=payload.notes,
            is_corrective=True,
        )
        work_order = self.repository.add(work_order)
        self.audit.record(
            AuditAction.CREATE,
            "work_order",
            work_order.id,
            actor=actor,
            payload={
                "code": work_order.code,
                "kind": "corrective",
                "equipment_id": str(work_order.equipment_id),
                "priority": work_order.priority,
            },
        )
        return work_order

    def assign(
        self,
        work_order: WorkOrder,
        assigned_to_id: int | None,
        actor: User | None = None,
    ) -> WorkOrder:
        actor = self._require_manager(actor)
        self._check_not_closed(work_order)
        if work_order.status == WorkOrderStatus.IN_PROGRESS.value:
            raise ConflictError(
                "L'intervention est déjà en cours : l'affectation ne peut plus changer."
            )
        if assigned_to_id is not None:
            self._check_assignee(assigned_to_id)
        work_order.assigned_to_id = assigned_to_id
        work_order.status = (
            WorkOrderStatus.ASSIGNED.value
            if assigned_to_id is not None
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
                "kind": "corrective",
                "assigned_to_id": str(work_order.assigned_to_id or ""),
            },
        )
        return work_order

    def start(
        self,
        work_order: WorkOrder,
        payload: InterventionStart,
        actor: User | None = None,
    ) -> WorkOrder:
        actor = self._can_intervene(work_order, actor)
        if work_order.status not in (
            WorkOrderStatus.OPEN.value,
            WorkOrderStatus.ASSIGNED.value,
        ):
            raise ConflictError(
                "Seule une intervention ouverte ou affectée peut être démarrée."
            )
        if work_order.intervention_started_at is not None:
            raise ConflictError("L'intervention a déjà été démarrée.")

        started_at = payload.started_at or now()
        if work_order.assigned_to_id is None:
            work_order.assigned_to_id = actor.id
        work_order.intervention_started_at = started_at
        work_order.started_at = started_at.date()
        work_order.status = WorkOrderStatus.IN_PROGRESS.value
        work_order.notes = _append_notes(work_order.notes, payload.notes)
        work_order = self.repository.save(work_order)
        self.audit.record(
            AuditAction.UPDATE,
            "work_order",
            work_order.id,
            actor=actor,
            payload={
                "code": work_order.code,
                "status": WorkOrderStatus.IN_PROGRESS.value,
                "started_at": started_at.isoformat(timespec="minutes"),
            },
        )
        return work_order

    def finish(
        self,
        work_order: WorkOrder,
        payload: InterventionFinish,
        actor: User | None = None,
    ) -> WorkOrder:
        actor = self._can_intervene(work_order, actor)
        if work_order.status != WorkOrderStatus.IN_PROGRESS.value:
            raise ConflictError(
                "L'intervention doit être en cours avant d'enregistrer sa clôture."
            )
        work_done = (payload.work_done or "").strip()
        if not work_done:
            raise ValidationError("Le compte rendu de l'intervention est obligatoire.")
        ended_at = payload.ended_at or now()
        if (
            work_order.intervention_started_at is not None
            and ended_at < work_order.intervention_started_at
        ):
            raise ValidationError(
                "L'heure de fin ne peut pas précéder l'heure de début de l'intervention."
            )

        work_order.intervention_ended_at = ended_at
        work_order.completed_at = ended_at.date()
        work_order.work_done = work_done
        work_order.status = WorkOrderStatus.DONE.value
        work_order.notes = _append_notes(work_order.notes, payload.notes)
        work_order = self.repository.save(work_order)
        self.audit.record(
            AuditAction.UPDATE,
            "work_order",
            work_order.id,
            actor=actor,
            payload={
                "code": work_order.code,
                "status": WorkOrderStatus.DONE.value,
                "ended_at": ended_at.isoformat(timespec="minutes"),
                "duration_minutes": str(work_order.intervention_duration_minutes or 0),
            },
        )
        return work_order

    def cancel(
        self,
        work_order: WorkOrder,
        payload: InterventionCancel,
        actor: User | None = None,
    ) -> WorkOrder:
        actor = self._require_actor(actor)
        if work_order.status in (
            WorkOrderStatus.DONE.value,
            WorkOrderStatus.CANCELLED.value,
        ):
            raise ConflictError("Cette intervention est déjà clôturée.")
        if actor.role not in MANAGER_ROLES and work_order.created_by_id != actor.id:
            raise PermissionDeniedError(
                "Seul le demandeur ou le responsable de maintenance peut annuler "
                "cette demande."
            )
        if any(
            item.status == InterventionPartStatus.USED.value
            for item in work_order.intervention_parts
        ):
            raise ConflictError(
                "Des pièces ont déjà été consommées : l'intervention ne peut plus "
                "être annulée."
            )
        for item in work_order.intervention_parts:
            if item.status == InterventionPartStatus.REQUESTED.value:
                item.status = InterventionPartStatus.CANCELLED.value
        work_order.status = WorkOrderStatus.CANCELLED.value
        work_order.completed_at = today()
        work_order.notes = _append_notes(
            work_order.notes,
            f"Annulation : {payload.reason}" if payload.reason else "Annulation",
        )
        work_order = self.repository.save(work_order)
        self.audit.record(
            AuditAction.UPDATE,
            "work_order",
            work_order.id,
            actor=actor,
            payload={"code": work_order.code, "status": WorkOrderStatus.CANCELLED.value},
        )
        return work_order

    # ---------------------------------------------------------- pièces détachées
    def request_part(
        self,
        work_order: WorkOrder,
        payload: InterventionPartCreate,
        actor: User | None = None,
    ) -> InterventionPart:
        actor = self._can_intervene(work_order, actor)
        self._check_not_closed(work_order)
        spare_part = self.db.get(SparePart, payload.spare_part_id)
        if spare_part is None:
            raise NotFoundError(f"Pièce de rechange {payload.spare_part_id} introuvable.")
        if not spare_part.is_active:
            raise ValidationError(
                f"La pièce '{spare_part.code}' est inactive : elle ne peut pas être demandée."
            )
        if payload.quantity <= 0:
            raise ValidationError("La quantité demandée doit être positive.")
        existing = self.part_repository.find_pending(work_order.id, spare_part.id)
        if existing is not None:
            raise ConflictError(
                f"Une demande de pièce '{spare_part.code}' est déjà en attente "
                "pour cette intervention."
            )

        item = InterventionPart(
            work_order_id=work_order.id,
            spare_part_id=spare_part.id,
            requested_quantity=payload.quantity,
            status=InterventionPartStatus.REQUESTED.value,
            notes=payload.notes,
            requested_by_id=actor.id,
            requested_at=now(),
        )
        item = self.part_repository.add(item)
        self.audit.record(
            AuditAction.CREATE,
            "intervention_part",
            item.id,
            actor=actor,
            payload={
                "work_order": work_order.code,
                "spare_part": spare_part.code,
                "quantity": str(payload.quantity),
            },
        )
        return item

    def use_part(
        self,
        work_order: WorkOrder,
        item: InterventionPart,
        payload: InterventionPartUse,
        actor: User | None = None,
    ) -> InterventionPart:
        actor = self._can_intervene(work_order, actor)
        if item.work_order_id != work_order.id:
            raise NotFoundError("Cette pièce n'appartient pas à l'intervention.")
        if work_order.status != WorkOrderStatus.IN_PROGRESS.value:
            raise ConflictError(
                "Les pièces ne peuvent être consommées que pendant une intervention "
                "en cours."
            )
        if item.status != InterventionPartStatus.REQUESTED.value:
            raise ConflictError(
                f"La pièce '{item.spare_part_code}' n'est plus en attente "
                f"(statut : {item.status_label})."
            )
        quantity = payload.quantity or item.requested_quantity
        if quantity > item.requested_quantity:
            raise ValidationError(
                "La quantité utilisée ne peut pas dépasser la quantité demandée."
            )

        consumed_part = item.spare_part
        if payload.replacement_part_id not in (None, 0, item.spare_part_id):
            candidate = self.db.get(SparePart, payload.replacement_part_id)
            if candidate is None:
                raise NotFoundError(
                    f"Pièce de rechange {payload.replacement_part_id} introuvable."
                )
            if not candidate.is_active:
                raise ValidationError(
                    f"La pièce '{candidate.code}' est inactive : elle ne peut pas "
                    "être consommée."
                )
            if not self.stock_service.is_compatible_replacement(
                candidate, item.spare_part
            ):
                raise ValidationError(
                    f"La pièce '{candidate.code}' n'est pas déclarée compatible "
                    f"avec '{item.spare_part_code}'."
                )
            consumed_part = candidate

        substituted = consumed_part.id != item.spare_part_id
        note = f"Pièce demandée : {item.spare_part_code} ({work_order.code})"
        if substituted:
            note += f" — remplacée par {consumed_part.code}"
        movement = self.stock_service.record_movement(
            consumed_part,
            StockMovementCreate(
                movement_type=StockMovementType.EXIT,
                quantity=quantity,
                reference=f"Intervention {work_order.code}",
                notes=_append_notes(note, payload.notes),
                work_order_id=work_order.id,
            ),
            actor=actor,
        )
        item.used_quantity = quantity
        item.used_at = now()
        item.used_by_id = actor.id
        item.used_spare_part_id = consumed_part.id
        item.status = InterventionPartStatus.USED.value
        item = self.part_repository.save(item)
        self.audit.record(
            AuditAction.UPDATE,
            "intervention_part",
            item.id,
            actor=actor,
            payload={
                "work_order": work_order.code,
                "requested_spare_part": item.spare_part_code or "",
                "consumed_spare_part": consumed_part.code,
                "quantity": str(quantity),
                "stock_movement_id": str(movement.id),
            },
        )
        return item

    def cancel_part(
        self,
        work_order: WorkOrder,
        item: InterventionPart,
        actor: User | None = None,
    ) -> InterventionPart:
        actor = self._can_intervene(work_order, actor)
        if item.work_order_id != work_order.id:
            raise NotFoundError("Cette pièce n'appartient pas à l'intervention.")
        if item.status != InterventionPartStatus.REQUESTED.value:
            raise ConflictError(
                f"La pièce '{item.spare_part_code}' n'est plus en attente "
                f"(statut : {item.status_label})."
            )
        item.status = InterventionPartStatus.CANCELLED.value
        item = self.part_repository.save(item)
        self.audit.record(
            AuditAction.UPDATE,
            "intervention_part",
            item.id,
            actor=actor,
            payload={"work_order": work_order.code, "status": "cancelled"},
        )
        return item

    # ------------------------------------------------------------------ interne
    def _next_code(self) -> str:
        sequence = self.repository.next_number()
        code = f"OT-{today().year}-{sequence:04d}"
        while self.repository.get_by_code(code):
            sequence += 1
            code = f"OT-{today().year}-{sequence:04d}"
        return code

    def _require_actor(self, actor: User | None) -> User:
        if actor is None:
            raise AuthenticationRequiredError("Connexion requise pour cette action.")
        return actor

    def _require_manager(self, actor: User | None) -> User:
        actor = self._require_actor(actor)
        if actor.role not in MANAGER_ROLES:
            raise PermissionDeniedError(
                "Action réservée au responsable de maintenance ou à un administrateur."
            )
        return actor

    def _can_intervene(self, work_order: WorkOrder, actor: User | None) -> User:
        actor = self._require_actor(actor)
        if actor.role in MANAGER_ROLES:
            return actor
        if work_order.assigned_to_id != actor.id:
            raise PermissionDeniedError(
                "Cette intervention n'est pas affectée à votre compte."
            )
        return actor

    def _check_assignee(self, user_id: int) -> None:
        user = self.user_repository.get(user_id)
        if user is None:
            raise NotFoundError(f"Utilisateur {user_id} introuvable.")
        if not user.is_active:
            raise ValidationError("Un technicien inactif ne peut pas être affecté.")
        if user.role not in ASSIGNABLE_ROLES:
            raise ValidationError(
                "Une intervention ne peut être affectée qu'à un technicien, "
                "un responsable ou un administrateur."
            )

    def _check_not_closed(self, work_order: WorkOrder) -> None:
        if work_order.status in (
            WorkOrderStatus.DONE.value,
            WorkOrderStatus.CANCELLED.value,
        ):
            raise ConflictError("Cette intervention est clôturée.")


def _append_notes(existing: str | None, addition: str | None) -> str | None:
    addition = (addition or "").strip()
    if not addition:
        return existing
    if not existing:
        return addition
    return f"{existing}\n{addition}"
