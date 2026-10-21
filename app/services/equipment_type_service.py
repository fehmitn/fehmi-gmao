"""Service des types / familles d'équipements."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import ConflictError, NotFoundError
from app.models.equipment import Equipment
from app.models.equipment_type import EquipmentType
from app.models.enums import AuditAction
from app.models.user import User
from app.repositories.equipment import EquipmentRepository
from app.repositories.equipment_type import EquipmentTypeRepository
from app.schemas.equipment_type import EquipmentTypeCreate, EquipmentTypeUpdate
from app.services.audit_service import AuditService


class EquipmentTypeService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = EquipmentTypeRepository(db)
        self.equipment_repository = EquipmentRepository(db)
        self.audit = AuditService(db)

    def list(self, active_only: bool = False) -> list[EquipmentType]:
        return self.repository.list_all(active_only=active_only)

    def categories(self) -> list[str]:
        return self.repository.categories()

    def get(self, type_id: int) -> EquipmentType:
        equipment_type = self.repository.get(type_id)
        if equipment_type is None:
            raise NotFoundError(f"Type d'équipement {type_id} introuvable.")
        return self.enrich(equipment_type)

    def create(
        self,
        payload: EquipmentTypeCreate,
        actor: User | None = None,
    ) -> EquipmentType:
        code = payload.code.strip()
        if self.repository.get_by_code(code):
            raise ConflictError(f"Un type d'équipement avec le code '{code}' existe déjà.")
        equipment_type = EquipmentType(
            code=code,
            name=payload.name.strip(),
            category=payload.category.strip(),
            manufacturer=payload.manufacturer,
            model=payload.model,
            description=payload.description,
            criticality=payload.criticality.value if payload.criticality else None,
            technical_specs=payload.technical_specs,
            is_active=payload.is_active,
        )
        equipment_type = self.repository.add(equipment_type)
        self.audit.record(
            AuditAction.CREATE,
            "equipment_type",
            equipment_type.id,
            actor=actor,
            payload={"code": equipment_type.code, "name": equipment_type.name},
        )
        return self.enrich(equipment_type)

    def update(
        self,
        equipment_type: EquipmentType,
        payload: EquipmentTypeUpdate,
        actor: User | None = None,
    ) -> EquipmentType:
        data = payload.model_dump(exclude_unset=True)
        if "code" in data and data["code"]:
            code = str(data["code"]).strip()
            existing = self.repository.get_by_code(code)
            if existing is not None and existing.id != equipment_type.id:
                raise ConflictError(
                    f"Un type d'équipement avec le code '{code}' existe déjà."
                )
            equipment_type.code = code
        if "name" in data and data["name"]:
            equipment_type.name = str(data["name"]).strip()
        if "category" in data and data["category"]:
            equipment_type.category = str(data["category"]).strip()
        for field in ("manufacturer", "model", "description"):
            if field in data:
                value = data[field]
                setattr(
                    equipment_type,
                    field,
                    value.strip() if isinstance(value, str) else value,
                )
        if "criticality" in data:
            equipment_type.criticality = (
                payload.criticality.value if payload.criticality else None
            )
        if "technical_specs" in data:
            equipment_type.technical_specs = data["technical_specs"]
        if "is_active" in data and data["is_active"] is not None:
            equipment_type.is_active = bool(data["is_active"])

        equipment_type = self.repository.save(equipment_type)
        self.audit.record(
            AuditAction.UPDATE,
            "equipment_type",
            equipment_type.id,
            actor=actor,
            payload={k: str(v) for k, v in data.items() if v is not None},
        )
        return self.enrich(equipment_type)

    def delete(self, equipment_type: EquipmentType, actor: User | None = None) -> None:
        stmt = select(func.count(Equipment.id)).where(
            Equipment.equipment_type_id == equipment_type.id
        )
        count = int(self.db.scalar(stmt) or 0)
        if count:
            raise ConflictError(
                f"Impossible de supprimer '{equipment_type.code}' : "
                f"{count} équipement(s) l'utilisent."
            )
        payload = {"code": equipment_type.code, "name": equipment_type.name}
        type_id = equipment_type.id
        self.repository.delete(equipment_type)
        self.audit.record(
            AuditAction.DELETE, "equipment_type", type_id, actor=actor, payload=payload
        )

    def enrich(self, equipment_type: EquipmentType) -> EquipmentType:
        stmt = select(func.count(Equipment.id)).where(
            Equipment.equipment_type_id == equipment_type.id
        )
        equipment_type.equipment_count = int(self.db.scalar(stmt) or 0)
        return equipment_type
