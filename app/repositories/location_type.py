from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.location_type import LocationType


class LocationTypeRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, type_id: int) -> LocationType | None:
        return self.db.get(LocationType, type_id)

    def get_by_code(self, code: str) -> LocationType | None:
        stmt = select(LocationType).where(LocationType.code == code)
        return self.db.scalars(stmt).first()

    def list_all(self, active_only: bool = False) -> list[LocationType]:
        stmt = select(LocationType).order_by(LocationType.sort_order, LocationType.label)
        if active_only:
            stmt = stmt.where(LocationType.is_active.is_(True))
        return list(self.db.scalars(stmt).all())

    def add(self, location_type: LocationType) -> LocationType:
        self.db.add(location_type)
        self.db.commit()
        self.db.refresh(location_type)
        return location_type

    def save(self, location_type: LocationType) -> LocationType:
        self.db.commit()
        self.db.refresh(location_type)
        return location_type

    def delete(self, location_type: LocationType) -> None:
        self.db.delete(location_type)
        self.db.commit()
