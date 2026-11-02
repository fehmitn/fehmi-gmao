from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import InterventionPartStatus
from app.models.intervention_part import InterventionPart


class InterventionPartRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, work_order_id: int, part_id: int) -> InterventionPart | None:
        stmt = select(InterventionPart).where(
            InterventionPart.id == part_id,
            InterventionPart.work_order_id == work_order_id,
        )
        return self.db.scalars(stmt).first()

    def list_for(self, work_order_id: int) -> list[InterventionPart]:
        stmt = (
            select(InterventionPart)
            .where(InterventionPart.work_order_id == work_order_id)
            .order_by(InterventionPart.id)
        )
        return list(self.db.scalars(stmt).all())

    def find_pending(
        self, work_order_id: int, spare_part_id: int
    ) -> InterventionPart | None:
        stmt = select(InterventionPart).where(
            InterventionPart.work_order_id == work_order_id,
            InterventionPart.spare_part_id == spare_part_id,
            InterventionPart.status == InterventionPartStatus.REQUESTED.value,
        )
        return self.db.scalars(stmt).first()

    def add(self, item: InterventionPart) -> InterventionPart:
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def save(self, item: InterventionPart) -> InterventionPart:
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item
