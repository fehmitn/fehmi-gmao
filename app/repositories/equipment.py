from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.equipment import Equipment


class EquipmentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_code(self, code: str) -> Equipment | None:
        stmt = select(Equipment).where(Equipment.code == code)
        return self.db.scalars(stmt).first()

    def add(self, equipment: Equipment) -> Equipment:
        self.db.add(equipment)
        self.db.commit()
        self.db.refresh(equipment)
        return equipment
