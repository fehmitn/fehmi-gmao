from __future__ import annotations

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TimestampMixin


class LocationType(IdMixin, TimestampMixin, Base):
    """Type d'emplacement (bâtiment, atelier, zone, ligne...).

    Permet de filtrer et de rapporter par niveau physique sans figer
    l'arborescence dans le code.
    """

    __tablename__ = "location_types"

    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(300), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    locations: Mapped[list["Location"]] = relationship(back_populates="location_type")

    def __str__(self) -> str:
        return self.label
