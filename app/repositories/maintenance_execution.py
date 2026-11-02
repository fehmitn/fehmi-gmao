from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.maintenance_execution import MaintenanceExecution


class MaintenanceExecutionRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, execution_id: int) -> MaintenanceExecution | None:
        return self.db.get(MaintenanceExecution, execution_id)

    def list_by_equipment(self, equipment_id: int) -> list[MaintenanceExecution]:
        stmt = (
            select(MaintenanceExecution)
            .where(MaintenanceExecution.equipment_id == equipment_id)
            .order_by(
                MaintenanceExecution.performed_on.desc(),
                MaintenanceExecution.id.desc(),
            )
        )
        return list(self.db.scalars(stmt).all())

    def list_by_rule(self, maintenance_id: int) -> list[MaintenanceExecution]:
        stmt = (
            select(MaintenanceExecution)
            .where(MaintenanceExecution.periodic_maintenance_id == maintenance_id)
            .order_by(
                MaintenanceExecution.performed_on.desc(),
                MaintenanceExecution.id.desc(),
            )
        )
        return list(self.db.scalars(stmt).all())

    def list_all(self) -> list[MaintenanceExecution]:
        stmt = select(MaintenanceExecution).order_by(
            MaintenanceExecution.performed_on.desc(),
            MaintenanceExecution.id.desc(),
        )
        return list(self.db.scalars(stmt).all())

    def add(self, execution: MaintenanceExecution) -> MaintenanceExecution:
        self.db.add(execution)
        self.db.commit()
        self.db.refresh(execution)
        return execution
