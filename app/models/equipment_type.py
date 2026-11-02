from __future__ import annotations

from sqlalchemy import Boolean, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TimestampMixin
from app.models.enums import Criticality


class EquipmentType(IdMixin, TimestampMixin, Base):
    """Un type / famille d'équipements.

    Équivalent des « modelli di apparecchiature » de Wincat : un modèle
    pré-rempli (constructeur, modèle, criticité, caractéristiques techniques)
    qui évite de ressaisir les mêmes informations pour chaque exemplaire.
    """

    __tablename__ = "equipment_types"

    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(100), index=True)
    manufacturer: Mapped[str | None] = mapped_column(String(150), nullable=True)
    model: Mapped[str | None] = mapped_column(String(150), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    criticality: Mapped[str | None] = mapped_column(String(1), nullable=True)
    technical_specs: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    equipments: Mapped[list["Equipment"]] = relationship(back_populates="equipment_type")
    periodic_maintenances: Mapped[list["PeriodicMaintenance"]] = relationship(
        back_populates="equipment_type",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"

    @property
    def default_criticality(self) -> Criticality | None:
        if not self.criticality:
            return None
        try:
            return Criticality(self.criticality)
        except ValueError:
            return None
