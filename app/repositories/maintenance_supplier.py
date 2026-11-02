from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.maintenance_supplier import MaintenanceSupplier
from app.models.periodic_maintenance import PeriodicMaintenance


class MaintenanceSupplierRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, supplier_id: int) -> MaintenanceSupplier | None:
        return self.db.get(MaintenanceSupplier, supplier_id)

    def get_by_code(self, code: str) -> MaintenanceSupplier | None:
        stmt = select(MaintenanceSupplier).where(MaintenanceSupplier.code == code)
        return self.db.scalars(stmt).first()

    def list_all(self, active_only: bool = False) -> list[MaintenanceSupplier]:
        stmt = select(MaintenanceSupplier).order_by(MaintenanceSupplier.name)
        if active_only:
            stmt = stmt.where(MaintenanceSupplier.is_active.is_(True))
        return list(self.db.scalars(stmt).all())

    def usage_counts(self) -> dict[int, int]:
        stmt = (
            select(
                PeriodicMaintenance.supplier_id,
                func.count(PeriodicMaintenance.id),
            )
            .where(PeriodicMaintenance.supplier_id.is_not(None))
            .group_by(PeriodicMaintenance.supplier_id)
        )
        return {
            int(supplier_id): int(count)
            for supplier_id, count in self.db.execute(stmt).all()
            if supplier_id is not None
        }

    def add(self, supplier: MaintenanceSupplier) -> MaintenanceSupplier:
        self.db.add(supplier)
        self.db.commit()
        self.db.refresh(supplier)
        return supplier

    def save(self, supplier: MaintenanceSupplier) -> MaintenanceSupplier:
        self.db.commit()
        self.db.refresh(supplier)
        return supplier

    def delete(self, supplier: MaintenanceSupplier) -> None:
        self.db.delete(supplier)
        self.db.commit()
