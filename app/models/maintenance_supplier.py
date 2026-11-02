from __future__ import annotations

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TimestampMixin


class MaintenanceSupplier(IdMixin, TimestampMixin, Base):
    """Fournisseur / prestataire de maintenance.

    Référentiel partagé : une même entreprise peut intervenir sur plusieurs
    familles d'équipements et plusieurs opérations périodiques. Le fournisseur
    est rattaché à l'opération (et non à l'équipement) pour éviter de ressaisir
    la même information sur chaque machine.
    """

    __tablename__ = "maintenance_suppliers"

    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    contact_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    specialty: Mapped[str | None] = mapped_column(String(150), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    periodic_maintenances: Mapped[list["PeriodicMaintenance"]] = relationship(
        back_populates="supplier",
        passive_deletes=True,
    )

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"
