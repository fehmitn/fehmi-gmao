"""Corrige les horodatages de ``work_orders``.

La migration ``0004_work_orders_users_auth`` a créé les colonnes
``created_at`` et ``updated_at`` en ``NOT NULL`` **sans** valeur par défaut,
alors que le modèle ``TimestampMixin`` s'appuie sur ``server_default=func.now()``.
Sur une base migrée (et non créée par ``create_all``), toute insertion d'ordre
de travail échouait donc sur ``NOT NULL constraint failed: work_orders.created_at``.

Cette migration réaligne le schéma sur les modèles en rétablissant la valeur
par défaut ``CURRENT_TIMESTAMP`` sur les deux colonnes.

Revision ID: 0007_work_order_timestamps
Revises: 0006_corrective_maintenance
Create Date: 2026-11-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_work_order_timestamps"
down_revision: str | None = "0006_corrective_maintenance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("work_orders", schema=None) as batch_op:
        batch_op.alter_column(
            "created_at",
            existing_type=sa.DateTime(),
            nullable=False,
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
        )
        batch_op.alter_column(
            "updated_at",
            existing_type=sa.DateTime(),
            nullable=False,
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
        )


def downgrade() -> None:
    with op.batch_alter_table("work_orders", schema=None) as batch_op:
        batch_op.alter_column(
            "created_at",
            existing_type=sa.DateTime(),
            nullable=False,
            server_default=None,
        )
        batch_op.alter_column(
            "updated_at",
            existing_type=sa.DateTime(),
            nullable=False,
            server_default=None,
        )
