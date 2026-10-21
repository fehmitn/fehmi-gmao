"""Mixins SQLAlchemy partagés par tous les modèles."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

__all__ = ["Base", "IdMixin", "TimestampMixin"]


class IdMixin:
    """Clé primaire auto-incrémentée commune à toutes les tables."""

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)


class TimestampMixin:
    """Horodatage de création / mise à jour."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
