from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.equipment_type import EquipmentType


class EquipmentTypeRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, type_id: int) -> EquipmentType | None:
        return self.db.get(EquipmentType, type_id)

    def get_by_code(self, code: str) -> EquipmentType | None:
        stmt = select(EquipmentType).where(EquipmentType.code == code)
        return self.db.scalars(stmt).first()

    def list_all(self, active_only: bool = False) -> list[EquipmentType]:
        stmt = select(EquipmentType).order_by(EquipmentType.category, EquipmentType.name)
        if active_only:
            stmt = stmt.where(EquipmentType.is_active.is_(True))
        return list(self.db.scalars(stmt).all())

    def categories(self) -> list[str]:
        stmt = select(EquipmentType.category).distinct().order_by(EquipmentType.category)
        return list(self.db.scalars(stmt).all())

    def add(self, equipment_type: EquipmentType) -> EquipmentType:
        self.db.add(equipment_type)
        self.db.commit()
        self.db.refresh(equipment_type)
        return equipment_type

    def save(self, equipment_type: EquipmentType) -> EquipmentType:
        self.db.commit()
        self.db.refresh(equipment_type)
        return equipment_type

    def delete(self, equipment_type: EquipmentType) -> None:
        self.db.delete(equipment_type)
        self.db.commit()
