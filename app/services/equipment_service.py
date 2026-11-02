"""Service des équipements (saisie et consultation de l'inventaire)."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.errors import ConflictError, FutureDateNotAllowed, NotFoundError
from app.models.equipment import Equipment
from app.models.enums import AuditAction
from app.models.user import User
from app.repositories.base import Page
from app.repositories.equipment import EquipmentRepository
from app.repositories.equipment_type import EquipmentTypeRepository
from app.repositories.location import LocationRepository
from app.repositories.site import SiteRepository
from app.schemas.equipment import EquipmentCreate, EquipmentUpdate
from app.services.audit_service import AuditService
from app.services.backdating import BackdatingPolicy
from app.services.clock import today
from app.services.placement_service import PlacementService


class EquipmentService:
    def __init__(self, db: Session, policy: BackdatingPolicy | None = None) -> None:
        self.db = db
        self.repository = EquipmentRepository(db)
        self.type_repository = EquipmentTypeRepository(db)
        self.location_repository = LocationRepository(db)
        self.site_repository = SiteRepository(db)
        self.placement_service = PlacementService(db, policy=policy)
        self.audit = AuditService(db)
        self.policy = policy or BackdatingPolicy()

    # ------------------------------------------------------------------ lecture
    def list(self, **filters) -> Page[Equipment]:
        page = self.repository.list(**filters)
        for equipment in page.items:
            self.enrich(equipment)
        return page

    def get(self, equipment_id: int) -> Equipment:
        equipment = self.repository.get(equipment_id)
        if equipment is None:
            raise NotFoundError(f"Équipement {equipment_id} introuvable.")
        return self.enrich(equipment)

    def enrich(self, equipment: Equipment) -> Equipment:
        """Ajoute les informations dérivées (usine, type, emplacement courant)."""
        site = self.site_repository.get(equipment.site_id)
        equipment.site_code = site.code if site else None
        equipment.site_name = site.name if site else None

        equipment_type = (
            self.type_repository.get(equipment.equipment_type_id)
            if equipment.equipment_type_id
            else None
        )
        equipment.equipment_type_code = equipment_type.code if equipment_type else None
        equipment.equipment_type_name = equipment_type.name if equipment_type else None

        current = self.placement_service.current(equipment.id)
        if current is not None:
            location = self.location_repository.get(current.location_id)
            equipment.current_location_id = current.location_id
            equipment.current_location_code = location.code if location else None
            equipment.current_location_name = location.name if location else None
            equipment.current_location_path = self.location_repository.path(current.location_id)
            equipment.installation_date = current.effective_from
        return equipment

    # ------------------------------------------------------------------ écriture
    def create(self, payload: EquipmentCreate, actor: User | None = None) -> Equipment:
        code = payload.code.strip()
        if self.repository.get_by_code(code):
            raise ConflictError(f"Un équipement avec le code '{code}' existe déjà.")

        location = self.location_repository.get(payload.location_id)
        if location is None:
            raise NotFoundError(f"Emplacement {payload.location_id} introuvable.")

        equipment_type = None
        if payload.equipment_type_id is not None:
            equipment_type = self.type_repository.get(payload.equipment_type_id)
            if equipment_type is None:
                raise NotFoundError(
                    f"Type d'équipement {payload.equipment_type_id} introuvable."
                )

        if payload.commissioning_date and payload.commissioning_date > today():
            raise FutureDateNotAllowed(payload.commissioning_date.isoformat())

        # Pré-remplissage depuis le type (équivalent des « modèles » Wincat).
        manufacturer = payload.manufacturer or (
            equipment_type.manufacturer if equipment_type else None
        )
        model = payload.model or (equipment_type.model if equipment_type else None)
        criticality = payload.criticality or (
            equipment_type.criticality if equipment_type else None
        )

        equipment = Equipment(
            code=code,
            name=payload.name.strip(),
            description=payload.description,
            equipment_type_id=payload.equipment_type_id,
            site_id=location.site_id,
            status=payload.status.value,
            criticality=criticality,
            manufacturer=manufacturer,
            model=model,
            serial_number=payload.serial_number,
            purchase_date=payload.purchase_date,
            commissioning_date=payload.commissioning_date,
            acquisition_cost=(
                Decimal(payload.acquisition_cost)
                if payload.acquisition_cost is not None
                else None
            ),
            warranty_end_date=payload.warranty_end_date,
            is_critical=payload.is_critical,
            operating_hours=payload.operating_hours,
            initial_operating_hours=payload.initial_operating_hours or 0,
        )
        self.db.add(equipment)
        self.db.flush()

        self.placement_service.install(
            equipment,
            location,
            effective_from=payload.effective_from,
            reason="Implantation initiale",
            derogation_reason=payload.derogation_reason,
            actor=actor,
        )
        equipment = self.repository.save(equipment)

        self.audit.record(
            AuditAction.CREATE,
            "equipment",
            equipment.id,
            actor=actor,
            payload={
                "code": equipment.code,
                "name": equipment.name,
                "location": self.location_repository.path(location.id),
                "site_id": str(equipment.site_id),
            },
        )
        return self.enrich(equipment)

    def update(
        self,
        equipment: Equipment,
        payload: EquipmentUpdate,
        actor: User | None = None,
    ) -> Equipment:
        data = payload.model_dump(exclude_unset=True)
        if "code" in data and data["code"]:
            code = str(data["code"]).strip()
            existing = self.repository.get_by_code(code)
            if existing is not None and existing.id != equipment.id:
                raise ConflictError(f"Un équipement avec le code '{code}' existe déjà.")
            equipment.code = code
        if "name" in data and data["name"]:
            equipment.name = str(data["name"]).strip()
        if "description" in data:
            value = data["description"]
            equipment.description = value.strip() if isinstance(value, str) else value
        if "equipment_type_id" in data:
            if data["equipment_type_id"] is not None and (
                self.type_repository.get(data["equipment_type_id"]) is None
            ):
                raise NotFoundError(
                    f"Type d'équipement {data['equipment_type_id']} introuvable."
                )
            equipment.equipment_type_id = data["equipment_type_id"]
        if "status" in data and data["status"] is not None:
            equipment.status = payload.status.value if payload.status else equipment.status
        if "criticality" in data:
            equipment.criticality = (
                payload.criticality.value if payload.criticality else None
            )
        for field in ("manufacturer", "model", "serial_number"):
            if field in data:
                value = data[field]
                setattr(equipment, field, value.strip() if isinstance(value, str) else value)
        for field in ("purchase_date", "commissioning_date", "warranty_end_date"):
            if field in data:
                setattr(equipment, field, data[field])
        if "acquisition_cost" in data:
            value = data["acquisition_cost"]
            equipment.acquisition_cost = (
                Decimal(value) if value is not None else None
            )
        if "is_critical" in data and data["is_critical"] is not None:
            equipment.is_critical = bool(data["is_critical"])
        if "is_active" in data and data["is_active"] is not None:
            equipment.is_active = bool(data["is_active"])
        if "operating_hours" in data:
            equipment.operating_hours = data["operating_hours"]
        if "initial_operating_hours" in data and data["initial_operating_hours"] is not None:
            equipment.initial_operating_hours = int(data["initial_operating_hours"])

        equipment = self.repository.save(equipment)
        self.audit.record(
            AuditAction.UPDATE,
            "equipment",
            equipment.id,
            actor=actor,
            payload={k: str(v) for k, v in data.items() if v is not None},
        )
        return self.enrich(equipment)

    def delete(self, equipment: Equipment, actor: User | None = None) -> None:
        payload = {"code": equipment.code, "name": equipment.name}
        equipment_id = equipment.id
        self.repository.delete(equipment)
        self.audit.record(
            AuditAction.DELETE, "equipment", equipment_id, actor=actor, payload=payload
        )
