from __future__ import annotations

from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.equipment_location import EquipmentLocation


class EquipmentLocationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, placement_id: int) -> EquipmentLocation | None:
        return self.db.get(EquipmentLocation, placement_id)

    def list_for_equipment(self, equipment_id: int) -> list[EquipmentLocation]:
        stmt = (
            select(EquipmentLocation)
            .where(EquipmentLocation.equipment_id == equipment_id)
            .order_by(EquipmentLocation.effective_from.desc(), EquipmentLocation.id.desc())
        )
        return list(self.db.scalars(stmt).all())

    def current(self, equipment_id: int) -> EquipmentLocation | None:
        stmt = select(EquipmentLocation).where(
            EquipmentLocation.equipment_id == equipment_id,
            EquipmentLocation.effective_to.is_(None),
        )
        return self.db.scalars(stmt).first()

    def at_date(self, equipment_id: int, day: date) -> EquipmentLocation | None:
        """Implantation effective au jour donné (cœur de la rétrodatation)."""
        stmt = select(EquipmentLocation).where(
            EquipmentLocation.equipment_id == equipment_id,
            EquipmentLocation.effective_from <= day,
            or_(
                EquipmentLocation.effective_to.is_(None),
                EquipmentLocation.effective_to >= day,
            ),
        )
        return self.db.scalars(stmt).first()

    def overlapping(
        self,
        equipment_id: int,
        start: date,
        end: date | None,
        exclude_id: int | None = None,
    ) -> list[EquipmentLocation]:
        stmt = select(EquipmentLocation).where(
            EquipmentLocation.equipment_id == equipment_id,
            EquipmentLocation.effective_from <= (end if end is not None else date.max),
            or_(
                EquipmentLocation.effective_to.is_(None),
                EquipmentLocation.effective_to >= start,
            ),
        )
        if exclude_id is not None:
            stmt = stmt.where(EquipmentLocation.id != exclude_id)
        return list(self.db.scalars(stmt).all())

    def add(self, placement: EquipmentLocation) -> EquipmentLocation:
        self.db.add(placement)
        self.db.commit()
        self.db.refresh(placement)
        return placement

    def save(self, placement: EquipmentLocation) -> EquipmentLocation:
        self.db.commit()
        self.db.refresh(placement)
        return placement

    def delete(self, placement: EquipmentLocation) -> None:
        self.db.delete(placement)
        self.db.commit()
