"""Service du référentiel des fournisseurs de maintenance."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.errors import ConflictError, NotFoundError
from app.models.enums import AuditAction
from app.models.maintenance_supplier import MaintenanceSupplier
from app.models.user import User
from app.repositories.maintenance_supplier import MaintenanceSupplierRepository
from app.schemas.maintenance_supplier import (
    MaintenanceSupplierCreate,
    MaintenanceSupplierUpdate,
)
from app.services.audit_service import AuditService


class MaintenanceSupplierService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = MaintenanceSupplierRepository(db)
        self.audit = AuditService(db)

    def list(self, active_only: bool = False) -> list[MaintenanceSupplier]:
        usage = self.repository.usage_counts()
        suppliers = self.repository.list_all(active_only=active_only)
        for supplier in suppliers:
            supplier.periodic_maintenance_count = usage.get(supplier.id, 0)
        return suppliers

    def get(self, supplier_id: int) -> MaintenanceSupplier:
        supplier = self.repository.get(supplier_id)
        if supplier is None:
            raise NotFoundError(f"Fournisseur {supplier_id} introuvable.")
        return self.enrich(supplier)

    def create(
        self,
        payload: MaintenanceSupplierCreate,
        actor: User | None = None,
    ) -> MaintenanceSupplier:
        code = payload.code.strip()
        if self.repository.get_by_code(code):
            raise ConflictError(f"Un fournisseur avec le code '{code}' existe déjà.")
        supplier = MaintenanceSupplier(
            code=code,
            name=payload.name.strip(),
            contact_name=payload.contact_name,
            phone=payload.phone,
            email=payload.email,
            specialty=payload.specialty,
            notes=payload.notes,
            is_active=payload.is_active,
        )
        supplier = self.repository.add(supplier)
        self.audit.record(
            AuditAction.CREATE,
            "maintenance_supplier",
            supplier.id,
            actor=actor,
            payload={"code": supplier.code, "name": supplier.name},
        )
        return self.enrich(supplier)

    def update(
        self,
        supplier: MaintenanceSupplier,
        payload: MaintenanceSupplierUpdate,
        actor: User | None = None,
    ) -> MaintenanceSupplier:
        data = payload.model_dump(exclude_unset=True)
        if "code" in data and data["code"]:
            code = str(data["code"]).strip()
            existing = self.repository.get_by_code(code)
            if existing is not None and existing.id != supplier.id:
                raise ConflictError(f"Un fournisseur avec le code '{code}' existe déjà.")
            supplier.code = code
        if "name" in data and data["name"]:
            supplier.name = str(data["name"]).strip()
        for field in ("contact_name", "phone", "email", "specialty", "notes"):
            if field in data:
                value = data[field]
                setattr(
                    supplier,
                    field,
                    value.strip() if isinstance(value, str) else value,
                )
        if "is_active" in data and data["is_active"] is not None:
            supplier.is_active = bool(data["is_active"])

        supplier = self.repository.save(supplier)
        self.audit.record(
            AuditAction.UPDATE,
            "maintenance_supplier",
            supplier.id,
            actor=actor,
            payload={k: str(v) for k, v in data.items() if v is not None},
        )
        return self.enrich(supplier)

    def delete(self, supplier: MaintenanceSupplier, actor: User | None = None) -> None:
        count = self.repository.usage_counts().get(supplier.id, 0)
        if count:
            raise ConflictError(
                f"Impossible de supprimer le fournisseur '{supplier.code}' : "
                f"{count} maintenance(s) périodique(s) y sont rattachées."
            )
        payload = {"code": supplier.code, "name": supplier.name}
        supplier_id = supplier.id
        self.repository.delete(supplier)
        self.audit.record(
            AuditAction.DELETE,
            "maintenance_supplier",
            supplier_id,
            actor=actor,
            payload=payload,
        )

    def enrich(self, supplier: MaintenanceSupplier) -> MaintenanceSupplier:
        supplier.periodic_maintenance_count = self.repository.usage_counts().get(
            supplier.id, 0
        )
        return supplier
