from __future__ import annotations

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin
from app.models.enums import UserRole


class User(IdMixin, TimestampMixin, Base):
    """Utilisateur applicatif (gestion des permissions façon WinMaint)."""

    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(150))
    role: Mapped[str] = mapped_column(String(30), default=UserRole.LECTURE.value, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)

    @property
    def has_password(self) -> bool:
        return bool(self.password_hash)

    @property
    def role_label(self) -> str:
        return {
            "admin": "Administrateur",
            "responsable": "Responsable maintenance",
            "technicien": "Technicien",
            "lecture": "Consultation",
        }.get(self.role, self.role)

    def __str__(self) -> str:
        return self.display_name
