"""Service des maintenances périodiques portées par les familles d'équipements."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.errors import ConflictError, NotFoundError, ValidationError
from app.models.enums import AuditAction, MaintenanceAnchor, MaintenanceIntervalUnit, MaintenanceType
from app.models.equipment_type import EquipmentType
from app.models.periodic_maintenance import PeriodicMaintenance
from app.models.user import User
from app.repositories.equipment_type import EquipmentTypeRepository
from app.repositories.maintenance_supplier import MaintenanceSupplierRepository
from app.repositories.periodic_maintenance import PeriodicMaintenanceRepository
from app.schemas.periodic_maintenance import (
    PeriodicMaintenanceCreate,
    PeriodicMaintenanceRead,
    PeriodicMaintenanceUpdate,
)
from app.services.audit_service import AuditService
from app.services.periodicity import periodicity_label


class PeriodicMaintenanceService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = PeriodicMaintenanceRepository(db)
        self.type_repository = EquipmentTypeRepository(db)
        self.supplier_repository = MaintenanceSupplierRepository(db)
        self.audit = AuditService(db)

    def list_for_type(self, equipment_type_id: int) -> list[PeriodicMaintenance]:
        self._get_type(equipment_type_id)
        counts = self.repository.execution_counts()
        items = self.repository.list_by_type(equipment_type_id)
        for item in items:
            self.enrich(item, execution_count=counts.get(item.id, 0))
        return items

    def list_all(self, active_only: bool = False) -> list[PeriodicMaintenance]:
        counts = self.repository.execution_counts()
        items = self.repository.list_all(active_only=active_only)
        for item in items:
            self.enrich(item, execution_count=counts.get(item.id, 0))
        return items

    def get(self, maintenance_id: int) -> PeriodicMaintenance:
        maintenance = self.repository.get(maintenance_id)
        if maintenance is None:
            raise NotFoundError(f"Maintenance périodique {maintenance_id} introuvable.")
        return self.enrich(maintenance)

    def create(
        self,
        equipment_type: EquipmentType | int,
        payload: PeriodicMaintenanceCreate,
        actor: User | None = None,
    ) -> PeriodicMaintenance:
        equipment_type = self._get_type(
            equipment_type.id if isinstance(equipment_type, EquipmentType) else equipment_type
        )
        code = payload.code.strip()
        if self.repository.get_by_type_and_code(equipment_type.id, code):
            raise ConflictError(
                f"Une maintenance '{code}' existe déjà pour la famille "
                f"'{equipment_type.code}'."
            )
        self._check_supplier(payload.supplier_id)
        unit = MaintenanceIntervalUnit(payload.interval_unit)
        anchor = MaintenanceAnchor(payload.anchor)
        if unit is MaintenanceIntervalUnit.HOURS:
            # Une périodicité en heures se mesure sur le compteur, pas sur une
            # date : l'ancrage est toujours la mise en service.
            anchor = MaintenanceAnchor.COMMISSIONING
            validation_error = None
        else:
            validation_error = self._validate_anchor(anchor, payload.fixed_date)
        if validation_error:
            raise ValidationError(validation_error)
        maintenance = PeriodicMaintenance(
            equipment_type_id=equipment_type.id,
            supplier_id=payload.supplier_id,
            code=code,
            label=payload.label.strip(),
            description=payload.description,
            interval_value=payload.interval_value,
            interval_unit=unit.value,
            maintenance_type=MaintenanceType(payload.maintenance_type).value,
            anchor=anchor.value if unit is not MaintenanceIntervalUnit.HOURS else MaintenanceAnchor.COMMISSIONING.value,
            fixed_date=payload.fixed_date if anchor is MaintenanceAnchor.FIXED_DATE and unit is not MaintenanceIntervalUnit.HOURS else None,
            tolerance_days=payload.tolerance_days,
            estimated_duration_minutes=payload.estimated_duration_minutes,
            sort_order=payload.sort_order,
            is_active=payload.is_active,
        )
        maintenance = self.repository.add(maintenance)
        self.audit.record(
            AuditAction.CREATE,
            "periodic_maintenance",
            maintenance.id,
            actor=actor,
            payload={
                "equipment_type": equipment_type.code,
                "code": maintenance.code,
                "label": maintenance.label,
                "interval": periodicity_label(
                    maintenance.interval_value, maintenance.interval_unit
                ),
            },
        )
        return self.enrich(maintenance)

    def update(
        self,
        maintenance: PeriodicMaintenance,
        payload: PeriodicMaintenanceUpdate,
        actor: User | None = None,
    ) -> PeriodicMaintenance:
        data = payload.model_dump(exclude_unset=True)
        if "code" in data and data["code"]:
            code = str(data["code"]).strip()
            existing = self.repository.get_by_type_and_code(
                maintenance.equipment_type_id, code
            )
            if existing is not None and existing.id != maintenance.id:
                raise ConflictError(
                    f"Une maintenance '{code}' existe déjà pour cette famille."
                )
            maintenance.code = code
        if "label" in data and data["label"]:
            maintenance.label = str(data["label"]).strip()
        if "description" in data:
            value = data["description"]
            maintenance.description = value.strip() if isinstance(value, str) else value
        if "interval_value" in data and data["interval_value"] is not None:
            maintenance.interval_value = int(data["interval_value"])
        if "interval_unit" in data and data["interval_unit"] is not None:
            maintenance.interval_unit = MaintenanceIntervalUnit(
                data["interval_unit"]
            ).value
        if "maintenance_type" in data and data["maintenance_type"] is not None:
            maintenance.maintenance_type = MaintenanceType(
                data["maintenance_type"]
            ).value
        if "anchor" in data and data["anchor"] is not None:
            maintenance.anchor = MaintenanceAnchor(data["anchor"]).value
        if "fixed_date" in data:
            maintenance.fixed_date = data["fixed_date"]
        if "supplier_id" in data:
            self._check_supplier(data["supplier_id"])
            maintenance.supplier_id = data["supplier_id"]
        if "tolerance_days" in data and data["tolerance_days"] is not None:
            maintenance.tolerance_days = int(data["tolerance_days"])
        if "estimated_duration_minutes" in data:
            maintenance.estimated_duration_minutes = data["estimated_duration_minutes"]
        if "sort_order" in data and data["sort_order"] is not None:
            maintenance.sort_order = int(data["sort_order"])
        if "is_active" in data and data["is_active"] is not None:
            maintenance.is_active = bool(data["is_active"])

        unit = MaintenanceIntervalUnit(maintenance.interval_unit)
        if unit is MaintenanceIntervalUnit.HOURS:
            maintenance.anchor = MaintenanceAnchor.COMMISSIONING.value
            maintenance.fixed_date = None
            validation_error = None
        else:
            if maintenance.anchor != MaintenanceAnchor.FIXED_DATE.value:
                maintenance.fixed_date = None
            validation_error = self._validate_anchor(
                MaintenanceAnchor(maintenance.anchor), maintenance.fixed_date
            )
        if validation_error:
            raise ValidationError(validation_error)

        maintenance = self.repository.save(maintenance)
        self.audit.record(
            AuditAction.UPDATE,
            "periodic_maintenance",
            maintenance.id,
            actor=actor,
            payload={k: str(v) for k, v in data.items() if v is not None},
        )
        return self.enrich(maintenance)

    def delete(
        self, maintenance: PeriodicMaintenance, actor: User | None = None
    ) -> None:
        execution_count = self.repository.count_executions(maintenance.id)
        if execution_count:
            raise ConflictError(
                f"Impossible de supprimer '{maintenance.code}' : "
                f"{execution_count} réalisation(s) d'ordre de travail y sont rattachées."
            )
        payload = {"code": maintenance.code, "label": maintenance.label}
        maintenance_id = maintenance.id
        self.repository.delete(maintenance)
        self.audit.record(
            AuditAction.DELETE,
            "periodic_maintenance",
            maintenance_id,
            actor=actor,
            payload=payload,
        )

    def enrich(
        self,
        maintenance: PeriodicMaintenance,
        *,
        execution_count: int | None = None,
    ) -> PeriodicMaintenance:
        equipment_type = self.type_repository.get(maintenance.equipment_type_id)
        maintenance.equipment_type_code = equipment_type.code if equipment_type else None
        maintenance.equipment_type_name = equipment_type.name if equipment_type else None

        supplier = (
            self.supplier_repository.get(maintenance.supplier_id)
            if maintenance.supplier_id
            else None
        )
        maintenance.supplier_code = supplier.code if supplier else None
        maintenance.supplier_name = supplier.name if supplier else None

        maintenance.periodicity_label = periodicity_label(
            maintenance.interval_value, maintenance.interval_unit
        )
        maintenance.execution_count = (
            execution_count
            if execution_count is not None
            else self.repository.count_executions(maintenance.id)
        )
        return maintenance

    def _get_type(self, equipment_type_id: int) -> EquipmentType:
        equipment_type = self.type_repository.get(equipment_type_id)
        if equipment_type is None:
            raise NotFoundError(f"Type d'équipement {equipment_type_id} introuvable.")
        return equipment_type

    def _check_supplier(self, supplier_id: int | None) -> None:
        if supplier_id is None:
            return
        if self.supplier_repository.get(supplier_id) is None:
            raise NotFoundError(f"Fournisseur {supplier_id} introuvable.")

    @staticmethod
    def _validate_anchor(
        anchor: MaintenanceAnchor, fixed_date
    ) -> str | None:
        if anchor is MaintenanceAnchor.FIXED_DATE and fixed_date is None:
            return (
                "Une date fixe est obligatoire lorsque l'ancrage est "
                "« Date fixe (première échéance) »."
            )
        return None


def to_read(maintenance: PeriodicMaintenance) -> PeriodicMaintenanceRead:
    """Convertit une règle enrichie en contrat API."""
    return PeriodicMaintenanceRead.model_validate(maintenance)
