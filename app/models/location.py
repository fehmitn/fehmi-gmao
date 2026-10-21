from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TimestampMixin


class Location(IdMixin, TimestampMixin, Base):
    """Un emplacement physique dans une usine (arbre hiérarchique).

    L'arbre est stocké en liste d'adjacence (parent_id) et les sous-arbres
    sont calculés par CTE récursive (voir LocationRepository.subtree_ids).
    """

    __tablename__ = "locations"
    __table_args__ = (
        UniqueConstraint("site_id", "code", name="uq_location_site_code"),
    )

    site_id: Mapped[int] = mapped_column(
        ForeignKey("sites.id", ondelete="CASCADE"),
        index=True,
    )
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("locations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    location_type_id: Mapped[int] = mapped_column(
        ForeignKey("location_types.id", ondelete="RESTRICT"),
        index=True,
    )
    code: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    site: Mapped["Site"] = relationship(back_populates="locations")
    location_type: Mapped["LocationType"] = relationship(back_populates="locations")
    parent: Mapped["Location | None"] = relationship(
        back_populates="children",
        remote_side="Location.id",
    )
    children: Mapped[list["Location"]] = relationship(
        back_populates="parent",
        passive_deletes=True,
    )

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"
