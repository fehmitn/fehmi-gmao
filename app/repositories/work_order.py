from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.enums import WorkOrderStatus
from app.models.equipment import Equipment
from app.models.work_order import WorkOrder


OPEN_STATUSES = (
    WorkOrderStatus.OPEN.value,
    WorkOrderStatus.ASSIGNED.value,
    WorkOrderStatus.IN_PROGRESS.value,
)


class WorkOrderRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, work_order_id: int) -> WorkOrder | None:
        return self.db.get(WorkOrder, work_order_id)

    def get_by_code(self, code: str) -> WorkOrder | None:
        return self.db.scalars(select(WorkOrder).where(WorkOrder.code == code)).first()

    def list(
        self,
        *,
        status: str | None = None,
        assigned_to_id: int | None = None,
        search: str | None = None,
        open_only: bool = False,
        corrective: bool | None = None,
    ) -> list[WorkOrder]:
        conditions = []
        if corrective is not None:
            conditions.append(WorkOrder.is_corrective.is_(corrective))
        if status:
            conditions.append(WorkOrder.status == status)
        elif open_only:
            conditions.append(WorkOrder.status.in_(OPEN_STATUSES))
        if assigned_to_id is not None:
            conditions.append(WorkOrder.assigned_to_id == assigned_to_id)
        if search:
            pattern = f"%{search.strip()}%"
            conditions.append(
                or_(
                    WorkOrder.code.ilike(pattern),
                    WorkOrder.description.ilike(pattern),
                    WorkOrder.equipment.has(Equipment.code.ilike(pattern)),
                    WorkOrder.equipment.has(Equipment.name.ilike(pattern)),
                )
            )
        stmt = select(WorkOrder)
        if conditions:
            stmt = stmt.where(*conditions)
        stmt = stmt.order_by(
            WorkOrder.status,
            WorkOrder.due_date.is_(None),
            WorkOrder.due_operating_hours.is_(None),
            WorkOrder.due_date,
            WorkOrder.due_operating_hours,
            WorkOrder.code,
        )
        return list(self.db.scalars(stmt).all())

    def list_open_for(self, equipment_id: int, periodic_maintenance_id: int | None) -> list[WorkOrder]:
        stmt = select(WorkOrder).where(
            WorkOrder.equipment_id == equipment_id,
            WorkOrder.status.in_(OPEN_STATUSES),
        )
        if periodic_maintenance_id is None:
            stmt = stmt.where(WorkOrder.periodic_maintenance_id.is_(None))
        else:
            stmt = stmt.where(WorkOrder.periodic_maintenance_id == periodic_maintenance_id)
        return list(self.db.scalars(stmt).all())

    def open_counts_by_user(self) -> dict[int, int]:
        stmt = (
            select(WorkOrder.assigned_to_id, WorkOrder.id)
            .where(WorkOrder.status.in_(OPEN_STATUSES))
            .where(WorkOrder.assigned_to_id.is_not(None))
        )
        counts: dict[int, int] = {}
        for user_id, _ in self.db.execute(stmt).all():
            counts[user_id] = counts.get(user_id, 0) + 1
        return counts

    def add(self, work_order: WorkOrder) -> WorkOrder:
        self.db.add(work_order)
        self.db.commit()
        self.db.refresh(work_order)
        return work_order

    def save(self, work_order: WorkOrder) -> WorkOrder:
        self.db.add(work_order)
        self.db.commit()
        self.db.refresh(work_order)
        return work_order

    def next_number(self) -> int:
        """Prochain numéro séquentiel, sans trouer la numérotation."""
        last = self.db.scalars(
            select(WorkOrder.id).order_by(WorkOrder.id.desc()).limit(1)
        ).first()
        return (last or 0) + 1
