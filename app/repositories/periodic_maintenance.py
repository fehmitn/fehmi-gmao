from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.maintenance_execution import MaintenanceExecution
from app.models.periodic_maintenance import PeriodicMaintenance


class PeriodicMaintenanceRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, maintenance_id: int) -> PeriodicMaintenance | None:
        return self.db.get(PeriodicMaintenance, maintenance_id)

    def get_by_type_and_code(
        self, equipment_type_id: int, code: str
    ) -> PeriodicMaintenance | None:
        stmt = select(PeriodicMaintenance).where(
            PeriodicMaintenance.equipment_type_id == equipment_type_id,
            PeriodicMaintenance.code == code,
        )
        return self.db.scalars(stmt).first()

    def list_by_type(
        self, equipment_type_id: int, active_only: bool = False
    ) -> list[PeriodicMaintenance]:
        stmt = (
            select(PeriodicMaintenance)
            .where(PeriodicMaintenance.equipment_type_id == equipment_type_id)
            .order_by(
                PeriodicMaintenance.sort_order,
                PeriodicMaintenance.code,
            )
        )
        if active_only:
            stmt = stmt.where(PeriodicMaintenance.is_active.is_(True))
        return list(self.db.scalars(stmt).all())

    def list_all(self, active_only: bool = False) -> list[PeriodicMaintenance]:
        stmt = select(PeriodicMaintenance).order_by(
            PeriodicMaintenance.equipment_type_id,
            PeriodicMaintenance.sort_order,
            PeriodicMaintenance.code,
        )
        if active_only:
            stmt = stmt.where(PeriodicMaintenance.is_active.is_(True))
        return list(self.db.scalars(stmt).all())

    def count_executions(self, maintenance_id: int) -> int:
        stmt = select(func.count(MaintenanceExecution.id)).where(
            MaintenanceExecution.periodic_maintenance_id == maintenance_id
        )
        return int(self.db.scalar(stmt) or 0)

    def execution_counts(self) -> dict[int, int]:
        stmt = select(
            MaintenanceExecution.periodic_maintenance_id,
            func.count(MaintenanceExecution.id),
        ).group_by(MaintenanceExecution.periodic_maintenance_id)
        return {
            int(maintenance_id): int(count)
            for maintenance_id, count in self.db.execute(stmt).all()
        }

    def add(self, maintenance: PeriodicMaintenance) -> PeriodicMaintenance:
        self.db.add(maintenance)
        self.db.commit()
        self.db.refresh(maintenance)
        return maintenance

    def save(self, maintenance: PeriodicMaintenance) -> PeriodicMaintenance:
        self.db.commit()
        self.db.refresh(maintenance)
        return maintenance

    def delete(self, maintenance: PeriodicMaintenance) -> None:
        self.db.delete(maintenance)
        self.db.commit()
