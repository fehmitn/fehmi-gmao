"""Maintenances périodiques rattachées aux familles d'équipements.

Cette migration ajoute :

* ``maintenance_suppliers``    <- fournisseurs / prestataires de maintenance
* ``periodic_maintenances``    <- contraintes périodiques d'une famille
* ``maintenance_executions``   <- réalisations d'OT et retard vs référentiel

L'échéancier n'est pas stocké : il est recalculé depuis l'ancrage de chaque
règle (mise en service, première implantation ou date fixe).

Revision ID: 0002_periodic_maintenance
Revises: 0001_baseline
Create Date: 2026-10-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_periodic_maintenance"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "maintenance_suppliers",
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("contact_name", sa.String(length=150), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("email", sa.String(length=200), nullable=True),
        sa.Column("specialty", sa.String(length=150), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("maintenance_suppliers", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_maintenance_suppliers_code"), ["code"], unique=True
        )
        batch_op.create_index(
            batch_op.f("ix_maintenance_suppliers_is_active"),
            ["is_active"],
            unique=False,
        )

    op.create_table(
        "periodic_maintenances",
        sa.Column("equipment_type_id", sa.Integer(), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("interval_value", sa.Integer(), nullable=False),
        sa.Column("interval_unit", sa.String(length=20), nullable=False),
        sa.Column("maintenance_type", sa.String(length=30), nullable=False),
        sa.Column("anchor", sa.String(length=20), nullable=False),
        sa.Column("fixed_date", sa.Date(), nullable=True),
        sa.Column("tolerance_days", sa.Integer(), nullable=False),
        sa.Column("estimated_duration_minutes", sa.Integer(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["equipment_type_id"], ["equipment_types.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["supplier_id"], ["maintenance_suppliers.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "equipment_type_id",
            "code",
            name="uq_periodic_maintenance_type_code",
        ),
    )
    with op.batch_alter_table("periodic_maintenances", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_periodic_maintenances_equipment_type_id"),
            ["equipment_type_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_periodic_maintenances_supplier_id"),
            ["supplier_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_periodic_maintenances_maintenance_type"),
            ["maintenance_type"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_periodic_maintenances_is_active"),
            ["is_active"],
            unique=False,
        )

    op.create_table(
        "maintenance_executions",
        sa.Column("equipment_id", sa.Integer(), nullable=False),
        sa.Column("periodic_maintenance_id", sa.Integer(), nullable=False),
        sa.Column("performed_on", sa.Date(), nullable=False),
        sa.Column("theoretical_due_date", sa.Date(), nullable=False),
        sa.Column("delay_days", sa.Integer(), nullable=False),
        sa.Column("performed_by_id", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.ForeignKeyConstraint(["equipment_id"], ["equipments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["periodic_maintenance_id"],
            ["periodic_maintenances.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["performed_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("maintenance_executions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_maintenance_executions_equipment_id"),
            ["equipment_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_maintenance_executions_periodic_maintenance_id"),
            ["periodic_maintenance_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_maintenance_executions_performed_on"),
            ["performed_on"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_maintenance_executions_delay_days"),
            ["delay_days"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_maintenance_executions_recorded_at"),
            ["recorded_at"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("maintenance_executions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_maintenance_executions_recorded_at"))
        batch_op.drop_index(batch_op.f("ix_maintenance_executions_delay_days"))
        batch_op.drop_index(batch_op.f("ix_maintenance_executions_performed_on"))
        batch_op.drop_index(
            batch_op.f("ix_maintenance_executions_periodic_maintenance_id")
        )
        batch_op.drop_index(batch_op.f("ix_maintenance_executions_equipment_id"))
    op.drop_table("maintenance_executions")

    with op.batch_alter_table("periodic_maintenances", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_periodic_maintenances_is_active"))
        batch_op.drop_index(batch_op.f("ix_periodic_maintenances_maintenance_type"))
        batch_op.drop_index(batch_op.f("ix_periodic_maintenances_supplier_id"))
        batch_op.drop_index(batch_op.f("ix_periodic_maintenances_equipment_type_id"))
    op.drop_table("periodic_maintenances")

    with op.batch_alter_table("maintenance_suppliers", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_maintenance_suppliers_is_active"))
        batch_op.drop_index(batch_op.f("ix_maintenance_suppliers_code"))
    op.drop_table("maintenance_suppliers")
