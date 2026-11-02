from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.spare_part import SparePart, StockMovement
from app.models.spare_part_interchange import SparePartInterchange


class SparePartRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, spare_part_id: int) -> SparePart | None:
        return self.db.get(SparePart, spare_part_id)

    def get_by_code(self, code: str) -> SparePart | None:
        return self.db.scalars(
            select(SparePart).where(SparePart.code == code)
        ).first()

    def list(
        self,
        *,
        search: str | None = None,
        category: str | None = None,
        low_stock_only: bool = False,
        active_only: bool = False,
    ) -> list[SparePart]:
        stmt = select(SparePart).order_by(SparePart.code)
        if active_only:
            stmt = stmt.where(SparePart.is_active.is_(True))
        if category:
            stmt = stmt.where(SparePart.category == category)
        if low_stock_only:
            stmt = stmt.where(
                SparePart.is_active.is_(True),
                SparePart.quantity <= SparePart.min_quantity,
            )
        if search:
            pattern = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    SparePart.code.ilike(pattern),
                    SparePart.name.ilike(pattern),
                    SparePart.category.ilike(pattern),
                    SparePart.manufacturer.ilike(pattern),
                    SparePart.manufacturer_reference.ilike(pattern),
                )
            )
        return list(self.db.scalars(stmt).all())

    def categories(self) -> list[str]:
        stmt = (
            select(SparePart.category)
            .where(SparePart.category.is_not(None))
            .distinct()
            .order_by(SparePart.category)
        )
        return [value for value in self.db.scalars(stmt).all() if value]

    def low_stock_count(self) -> int:
        return int(
            self.db.scalar(
                select(func.count(SparePart.id)).where(
                    SparePart.is_active.is_(True),
                    SparePart.quantity <= SparePart.min_quantity,
                )
            )
            or 0
        )

    def out_of_stock_count(self) -> int:
        return int(
            self.db.scalar(
                select(func.count(SparePart.id)).where(
                    SparePart.is_active.is_(True),
                    SparePart.quantity <= 0,
                )
            )
            or 0
        )

    def total_value(self) -> Decimal:
        value = self.db.scalar(
            select(
                func.coalesce(func.sum(SparePart.quantity * SparePart.unit_cost), 0)
            ).where(SparePart.is_active.is_(True))
        )
        return Decimal(value or 0)

    def movement_counts(self) -> dict[int, int]:
        stmt = select(
            StockMovement.spare_part_id, func.count(StockMovement.id)
        ).group_by(StockMovement.spare_part_id)
        return {
            int(spare_part_id): int(count)
            for spare_part_id, count in self.db.execute(stmt).all()
        }

    def list_movements(
        self, spare_part_id: int, limit: int | None = None
    ) -> list[StockMovement]:
        stmt = (
            select(StockMovement)
            .where(StockMovement.spare_part_id == spare_part_id)
            .order_by(StockMovement.movement_date.desc(), StockMovement.id.desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.db.scalars(stmt).all())

    def add(self, spare_part: SparePart) -> SparePart:
        self.db.add(spare_part)
        self.db.commit()
        self.db.refresh(spare_part)
        return spare_part

    def save(self, spare_part: SparePart) -> SparePart:
        self.db.add(spare_part)
        self.db.commit()
        self.db.refresh(spare_part)
        return spare_part

    def add_movement(self, movement: StockMovement) -> StockMovement:
        self.db.add(movement)
        self.db.commit()
        self.db.refresh(movement)
        return movement

    def delete(self, spare_part: SparePart) -> None:
        self.db.delete(spare_part)
        self.db.commit()

    # ------------------------------------------------------------- compatibilités
    def list_interchanges(self, spare_part_id: int) -> list[SparePartInterchange]:
        """Relations où cette pièce remplace une autre."""
        stmt = (
            select(SparePartInterchange)
            .where(SparePartInterchange.part_id == spare_part_id)
            .order_by(SparePartInterchange.id)
        )
        return list(self.db.scalars(stmt).all())

    def list_replacements(self, spare_part_id: int) -> list[SparePartInterchange]:
        """Relations où cette pièce peut être remplacée par une autre."""
        stmt = (
            select(SparePartInterchange)
            .where(SparePartInterchange.replaces_id == spare_part_id)
            .order_by(SparePartInterchange.id)
        )
        return list(self.db.scalars(stmt).all())

    def get_interchange(
        self, interchange_id: int
    ) -> SparePartInterchange | None:
        return self.db.get(SparePartInterchange, interchange_id)

    def find_interchange(
        self, part_id: int, replaces_id: int
    ) -> SparePartInterchange | None:
        stmt = select(SparePartInterchange).where(
            SparePartInterchange.part_id == part_id,
            SparePartInterchange.replaces_id == replaces_id,
        )
        return self.db.scalars(stmt).first()

    def add_interchange(
        self, interchange: SparePartInterchange
    ) -> SparePartInterchange:
        self.db.add(interchange)
        self.db.commit()
        self.db.refresh(interchange)
        return interchange

    def delete_interchange(self, interchange: SparePartInterchange) -> None:
        self.db.delete(interchange)
        self.db.commit()
