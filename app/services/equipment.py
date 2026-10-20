from sqlalchemy.orm import Session

from app.models.equipment import Equipment
from app.repositories.equipment import EquipmentRepository
from app.schemas.equipment import EquipmentCreate


class EquipmentAlreadyExistsError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Un équipement avec le code '{code}' existe déjà.")


class EquipmentService:
    def __init__(self, db: Session) -> None:
        self.repository = EquipmentRepository(db)

    def create_equipment(self, payload: EquipmentCreate) -> Equipment:
        if self.repository.get_by_code(payload.code):
            raise EquipmentAlreadyExistsError(payload.code)

        equipment = Equipment(
            code=payload.code.strip(),
            name=payload.name.strip(),
            description=payload.description,
            category=payload.category.strip(),
            location=payload.location.strip(),
            manufacturer=payload.manufacturer,
            serial_number=payload.serial_number,
            status=payload.status.value,
        )
        return self.repository.add(equipment)
