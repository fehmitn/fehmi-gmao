from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.maintenance_tool import (
    MaintenanceTool,
    ToolCalibration,
    ToolUsage,
)


class MaintenanceToolRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, tool_id: int) -> MaintenanceTool | None:
        return self.db.get(MaintenanceTool, tool_id)

    def get_by_code(self, code: str) -> MaintenanceTool | None:
        return self.db.scalars(
            select(MaintenanceTool).where(MaintenanceTool.code == code)
        ).first()

    def list(
        self,
        *,
        search: str | None = None,
        status: str | None = None,
        category: str | None = None,
        active_only: bool = False,
    ) -> list[MaintenanceTool]:
        stmt = select(MaintenanceTool).order_by(MaintenanceTool.code)
        if active_only:
            stmt = stmt.where(MaintenanceTool.is_active.is_(True))
        if status:
            stmt = stmt.where(MaintenanceTool.status == status)
        if category:
            stmt = stmt.where(MaintenanceTool.category == category)
        if search:
            pattern = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    MaintenanceTool.code.ilike(pattern),
                    MaintenanceTool.name.ilike(pattern),
                    MaintenanceTool.category.ilike(pattern),
                    MaintenanceTool.serial_number.ilike(pattern),
                    MaintenanceTool.manufacturer.ilike(pattern),
                )
            )
        return list(self.db.scalars(stmt).all())

    def categories(self) -> list[str]:
        stmt = (
            select(MaintenanceTool.category)
            .where(MaintenanceTool.category.is_not(None))
            .distinct()
            .order_by(MaintenanceTool.category)
        )
        return [value for value in self.db.scalars(stmt).all() if value]

    def add(self, tool: MaintenanceTool) -> MaintenanceTool:
        self.db.add(tool)
        self.db.commit()
        self.db.refresh(tool)
        return tool

    def save(self, tool: MaintenanceTool) -> MaintenanceTool:
        self.db.add(tool)
        self.db.commit()
        self.db.refresh(tool)
        return tool

    def delete(self, tool: MaintenanceTool) -> None:
        self.db.delete(tool)
        self.db.commit()

    def list_calibrations(self, tool_id: int) -> list[ToolCalibration]:
        stmt = (
            select(ToolCalibration)
            .where(ToolCalibration.tool_id == tool_id)
            .order_by(ToolCalibration.calibrated_on.desc(), ToolCalibration.id.desc())
        )
        return list(self.db.scalars(stmt).all())

    def add_calibration(self, calibration: ToolCalibration) -> ToolCalibration:
        self.db.add(calibration)
        self.db.commit()
        self.db.refresh(calibration)
        return calibration

    def calibration_count(self, tool_id: int) -> int:
        stmt = select(ToolCalibration.id).where(ToolCalibration.tool_id == tool_id)
        return len(list(self.db.scalars(stmt).all()))

    def list_usages(self, tool_id: int) -> list[ToolUsage]:
        stmt = (
            select(ToolUsage)
            .where(ToolUsage.tool_id == tool_id)
            .order_by(ToolUsage.started_on.desc(), ToolUsage.id.desc())
        )
        return list(self.db.scalars(stmt).all())

    def get_usage(self, tool_id: int, usage_id: int) -> ToolUsage | None:
        return self.db.scalars(
            select(ToolUsage).where(
                ToolUsage.id == usage_id,
                ToolUsage.tool_id == tool_id,
            )
        ).first()

    def add_usage(self, usage: ToolUsage) -> ToolUsage:
        self.db.add(usage)
        self.db.commit()
        self.db.refresh(usage)
        return usage

    def save_usage(self, usage: ToolUsage) -> ToolUsage:
        self.db.add(usage)
        self.db.commit()
        self.db.refresh(usage)
        return usage

    def usage_count(self, tool_id: int) -> int:
        stmt = select(ToolUsage.id).where(ToolUsage.tool_id == tool_id)
        return len(list(self.db.scalars(stmt).all()))
