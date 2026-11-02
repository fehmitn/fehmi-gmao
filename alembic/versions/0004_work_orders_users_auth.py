"""Ordres de travail + authentification utilisateurs.

Ajoute la table des ordres de travail ouverts (OT) avec affectation aux
techniciens, et permet le mot de passe utilisateur.

Revision ID: 0004_work_orders_users_auth
Revises: 0003_operating_hours
Create Date: 2026-10-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_work_orders_users_auth"
down_revision: str | None = "0003_operating_hours"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("password_hash", sa.String(length=255), nullable=True))

    op.create_table(
        "work_orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=30), nullable=False),
        sa.Column("equipment_id", sa.Integer(), nullable=False),
        sa.Column("periodic_maintenance_id", sa.Integer(), nullable=True),
        sa.Column("assigned_to_id", sa.Integer(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("priority", sa.String(length=20), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("due_operating_hours", sa.Integer(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("started_at", sa.Date(), nullable=True),
        sa.Column("completed_at", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assigned_to_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["equipment_id"], ["equipments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["periodic_maintenance_id"], ["periodic_maintenances.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("work_orders", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_work_orders_assigned_to_id"), ["assigned_to_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_work_orders_code"), ["code"], unique=True)
        batch_op.create_index(batch_op.f("ix_work_orders_equipment_id"), ["equipment_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_work_orders_periodic_maintenance_id"), ["periodic_maintenance_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_work_orders_status"), ["status"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("work_orders", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_work_orders_status"))
        batch_op.drop_index(batch_op.f("ix_work_orders_periodic_maintenance_id"))
        batch_op.drop_index(batch_op.f("ix_work_orders_equipment_id"))
        batch_op.drop_index(batch_op.f("ix_work_orders_code"))
        batch_op.drop_index(batch_op.f("ix_work_orders_assigned_to_id"))

    op.drop_table("work_orders")

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("password_hash")
