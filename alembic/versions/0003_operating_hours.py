"""Périodicité en heures de fonctionnement.

Ajoute le compteur horaire des équipements et le relevé figé sur les
réalisations. Les échéances en heures ne sont pas des dates : l'échéancier
compare le compteur courant au seuil et laisse la ligne ouverte tant que le
seuil n'est pas atteint.

Revision ID: 0003_operating_hours
Revises: 0002_periodic_maintenance
Create Date: 2026-10-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_operating_hours"
down_revision: str | None = "0002_periodic_maintenance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("equipments", schema=None) as batch_op:
        batch_op.add_column(sa.Column("operating_hours", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "initial_operating_hours",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )

    with op.batch_alter_table("maintenance_executions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("operating_hours", sa.Integer(), nullable=True))
        batch_op.alter_column(
            "theoretical_due_date",
            existing_type=sa.Date(),
            nullable=True,
        )
        batch_op.alter_column(
            "delay_days",
            existing_type=sa.Integer(),
            nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("maintenance_executions", schema=None) as batch_op:
        batch_op.alter_column(
            "delay_days",
            existing_type=sa.Integer(),
            nullable=False,
        )
        batch_op.alter_column(
            "theoretical_due_date",
            existing_type=sa.Date(),
            nullable=False,
        )
        batch_op.drop_column("operating_hours")

    with op.batch_alter_table("equipments", schema=None) as batch_op:
        batch_op.drop_column("initial_operating_hours")
        batch_op.drop_column("operating_hours")
