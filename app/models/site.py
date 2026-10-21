from __future__ import annotations

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TimestampMixin


class Site(IdMixin, TimestampMixin, Base):
    """Une usine / un site industriel.

    Rôle WinMaint : la fiche Clienti avec ses « sedi ». Dans une GMAO
    industrielle multi-sites, une usine peut contenir plusieurs ateliers.
    """

    __tablename__ = "sites"

    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    locations: Mapped[list["Location"]] = relationship(
        back_populates="site",
        passive_deletes=True,
    )
    equipments: Mapped[list["Equipment"]] = relationship(
        back_populates="site",
        passive_deletes=True,
    )

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"
