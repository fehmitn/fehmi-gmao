from __future__ import annotations

from decimal import Decimal

from sqlalchemy import ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TimestampMixin


class SparePartInterchange(IdMixin, TimestampMixin, Base):
    """Compatibilité orientée entre deux pièces de rechange.

    ``part_id`` est la pièce qui **remplace** ``replaces_id``. La relation est
    volontairement directionnelle : si A remplace B, B ne remplace pas A pour
    autant. La comparaison de prix est indicative, elle ne bloque pas la
    création du lien.
    """

    __tablename__ = "spare_part_interchanges"
    __table_args__ = (
        UniqueConstraint(
            "part_id", "replaces_id", name="uq_spare_part_interchange_pair"
        ),
    )

    part_id: Mapped[int] = mapped_column(
        ForeignKey("spare_parts.id", ondelete="RESTRICT"), index=True
    )
    replaces_id: Mapped[int] = mapped_column(
        ForeignKey("spare_parts.id", ondelete="RESTRICT"), index=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    part = relationship("SparePart", foreign_keys=[part_id], lazy="joined")
    replaces = relationship("SparePart", foreign_keys=[replaces_id], lazy="joined")

    @property
    def part_code(self) -> str | None:
        return self.part.code if self.part else None

    @property
    def replaces_code(self) -> str | None:
        return self.replaces.code if self.replaces else None

    @property
    def is_cheaper(self) -> bool:
        """Vrai lorsque la pièce de remplacement coûte moins cher."""
        if not self.part or not self.replaces:
            return False
        if self.part.unit_cost is None or self.replaces.unit_cost is None:
            return False
        return self.part.unit_cost < self.replaces.unit_cost

    @property
    def price_difference(self) -> Decimal | None:
        if not self.part or not self.replaces:
            return None
        if self.part.unit_cost is None or self.replaces.unit_cost is None:
            return None
        return self.part.unit_cost - self.replaces.unit_cost

    @property
    def price_label(self) -> str:
        if self.part is None or self.part.unit_cost is None:
            return "—"
        amount = f"{self.part.unit_cost:,.2f}".replace(",", " ").replace(".", ",")
        return f"{amount} €"

    def __str__(self) -> str:
        return f"{self.part_code} remplace {self.replaces_code}"
