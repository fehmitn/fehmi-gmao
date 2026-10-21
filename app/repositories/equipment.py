from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.equipment import Equipment
from app.models.equipment_location import EquipmentLocation
from app.models.equipment_type import EquipmentType
from app.repositories.base import Page
from app.repositories.location import LocationRepository


class EquipmentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, equipment_id: int) -> Equipment | None:
        return self.db.get(Equipment, equipment_id)

    def get_by_code(self, code: str) -> Equipment | None:
        stmt = select(Equipment).where(Equipment.code == code)
        return self.db.scalars(stmt).first()

    def list(
        self,
        *,
        site_id: int | None = None,
        location_id: int | None = None,
        include_descendants: bool = True,
        equipment_type_id: int | None = None,
        status: str | None = None,
        criticality: str | None = None,
        category: str | None = None,
        search: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> Page[Equipment]:
        conditions = []
        needs_type_join = category is not None
        if site_id is not None:
            conditions.append(Equipment.site_id == site_id)
        if equipment_type_id is not None:
            conditions.append(Equipment.equipment_type_id == equipment_type_id)
        if status:
            conditions.append(Equipment.status == status)
        if criticality:
            conditions.append(Equipment.criticality == criticality)
        if category:
            conditions.append(EquipmentType.category == category)
        if search:
            pattern = f"%{search.strip()}%"
            conditions.append(
                or_(
                    Equipment.code.ilike(pattern),
                    Equipment.name.ilike(pattern),
                    Equipment.serial_number.ilike(pattern),
                    Equipment.manufacturer.ilike(pattern),
                )
            )
        if location_id is not None:
            location_ids = (
                LocationRepository(self.db).subtree_ids(location_id)
                if include_descendants
                else [location_id]
            )
            current_placement = select(EquipmentLocation.equipment_id).where(
                EquipmentLocation.location_id.in_(location_ids),
                EquipmentLocation.effective_to.is_(None),
            )
            conditions.append(Equipment.id.in_(current_placement))

        total_stmt = select(func.count(Equipment.id))
        stmt = select(Equipment)
        if needs_type_join:
            total_stmt = total_stmt.join(
                EquipmentType, Equipment.equipment_type_id == EquipmentType.id
            )
            stmt = stmt.join(EquipmentType, Equipment.equipment_type_id == EquipmentType.id)
        total = int(self.db.scalar(total_stmt.where(*conditions)) or 0)

        page = max(1, page)
        size = max(1, min(size, 200))
        stmt = (
            stmt.where(*conditions)
            .order_by(Equipment.code)
            .offset((page - 1) * size)
            .limit(size)
        )
        items = list(self.db.scalars(stmt).all())
        return Page(items=items, total=total, page=page, size=size)

    def count_by_site(self) -> dict[int, int]:
        stmt = select(Equipment.site_id, func.count(Equipment.id)).group_by(Equipment.site_id)
        return {site_id: int(count) for site_id, count in self.db.execute(stmt).all()}

    def count_by_status(self) -> dict[str, int]:
        stmt = select(Equipment.status, func.count(Equipment.id)).group_by(Equipment.status)
        return {status: int(count) for status, count in self.db.execute(stmt).all()}

    def add(self, equipment: Equipment) -> Equipment:
        self.db.add(equipment)
        self.db.commit()
        self.db.refresh(equipment)
        return equipment

    def save(self, equipment: Equipment) -> Equipment:
        self.db.commit()
        self.db.refresh(equipment)
        return equipment

    def delete(self, equipment: Equipment) -> None:
        self.db.delete(equipment)
        self.db.commit()
