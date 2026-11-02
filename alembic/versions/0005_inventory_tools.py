"""Inventaire des pièces de rechange et équipements de maintenance.

Ajoute :
  * le catalogue des pièces de rechange et leurs mouvements de stock
    append-only (entrée, sortie, inventaire) ;
  * les fiches d'utilisation des équipements de maintenance (outils et
    moyens de contrôle), le registre des étalonnages périodiques et les
    prêts liés aux ordres de travail.

Revision ID: 0005_inventory_tools
Revises: 0004_work_orders_users_auth
Create Date: 2026-10-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_inventory_tools"
down_revision: str | None = "0004_work_orders_users_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "spare_parts",
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("unit", sa.String(length=30), nullable=False),
        sa.Column("manufacturer", sa.String(length=150), nullable=True),
        sa.Column("manufacturer_reference", sa.String(length=100), nullable=True),
        sa.Column("supplier_id", sa.Integer(), nullable=True),
        sa.Column("site_id", sa.Integer(), nullable=True),
        sa.Column("storage_location", sa.String(length=150), nullable=True),
        sa.Column("quantity", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("min_quantity", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("max_quantity", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("unit_cost", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
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
            ["site_id"], ["sites.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["supplier_id"], ["maintenance_suppliers.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("spare_parts", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_spare_parts_category"), ["category"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_spare_parts_code"), ["code"], unique=True
        )
        batch_op.create_index(
            batch_op.f("ix_spare_parts_is_active"), ["is_active"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_spare_parts_site_id"), ["site_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_spare_parts_supplier_id"),
            ["supplier_id"],
            unique=False,
        )

    op.create_table(
        "stock_movements",
        sa.Column("spare_part_id", sa.Integer(), nullable=False),
        sa.Column("movement_type", sa.String(length=20), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column(
            "quantity_delta", sa.Numeric(precision=12, scale=2), nullable=False
        ),
        sa.Column(
            "resulting_quantity", sa.Numeric(precision=12, scale=2), nullable=False
        ),
        sa.Column("movement_date", sa.Date(), nullable=False),
        sa.Column("reference", sa.String(length=100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("work_order_id", sa.Integer(), nullable=True),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["spare_part_id"], ["spare_parts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["work_order_id"], ["work_orders.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("stock_movements", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_stock_movements_actor_id"), ["actor_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_stock_movements_movement_date"),
            ["movement_date"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_stock_movements_movement_type"),
            ["movement_type"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_stock_movements_spare_part_id"),
            ["spare_part_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_stock_movements_work_order_id"),
            ["work_order_id"],
            unique=False,
        )

    op.create_table(
        "maintenance_tools",
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("manufacturer", sa.String(length=150), nullable=True),
        sa.Column("model", sa.String(length=150), nullable=True),
        sa.Column("serial_number", sa.String(length=100), nullable=True),
        sa.Column("site_id", sa.Integer(), nullable=True),
        sa.Column("storage_location", sa.String(length=150), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("requires_calibration", sa.Boolean(), nullable=False),
        sa.Column("calibration_interval_value", sa.Integer(), nullable=True),
        sa.Column("calibration_interval_unit", sa.String(length=20), nullable=False),
        sa.Column("last_calibration_date", sa.Date(), nullable=True),
        sa.Column("next_calibration_date", sa.Date(), nullable=True),
        sa.Column("calibration_provider_id", sa.Integer(), nullable=True),
        sa.Column("legal_reference", sa.Text(), nullable=True),
        sa.Column("purchase_date", sa.Date(), nullable=True),
        sa.Column("commissioning_date", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
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
            ["calibration_provider_id"],
            ["maintenance_suppliers.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["site_id"], ["sites.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("maintenance_tools", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_maintenance_tools_calibration_provider_id"),
            ["calibration_provider_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_maintenance_tools_category"), ["category"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_maintenance_tools_code"), ["code"], unique=True
        )
        batch_op.create_index(
            batch_op.f("ix_maintenance_tools_is_active"),
            ["is_active"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_maintenance_tools_next_calibration_date"),
            ["next_calibration_date"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_maintenance_tools_site_id"), ["site_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_maintenance_tools_status"), ["status"], unique=False
        )

    op.create_table(
        "tool_calibrations",
        sa.Column("tool_id", sa.Integer(), nullable=False),
        sa.Column("calibrated_on", sa.Date(), nullable=False),
        sa.Column("next_due_date", sa.Date(), nullable=True),
        sa.Column("provider_id", sa.Integer(), nullable=True),
        sa.Column("certificate_number", sa.String(length=100), nullable=True),
        sa.Column("result", sa.String(length=20), nullable=False),
        sa.Column("cost", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["provider_id"], ["maintenance_suppliers.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["tool_id"], ["maintenance_tools.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("tool_calibrations", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_tool_calibrations_calibrated_on"),
            ["calibrated_on"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_tool_calibrations_next_due_date"),
            ["next_due_date"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_tool_calibrations_provider_id"),
            ["provider_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_tool_calibrations_result"), ["result"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_tool_calibrations_tool_id"), ["tool_id"], unique=False
        )

    op.create_table(
        "tool_usages",
        sa.Column("tool_id", sa.Integer(), nullable=False),
        sa.Column("work_order_id", sa.Integer(), nullable=True),
        sa.Column("used_by_id", sa.Integer(), nullable=True),
        sa.Column("started_on", sa.Date(), nullable=False),
        sa.Column("ended_on", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("return_notes", sa.Text(), nullable=True),
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
            ["tool_id"], ["maintenance_tools.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["used_by_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["work_order_id"], ["work_orders.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("tool_usages", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_tool_usages_ended_on"), ["ended_on"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_tool_usages_started_on"), ["started_on"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_tool_usages_tool_id"), ["tool_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_tool_usages_used_by_id"), ["used_by_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_tool_usages_work_order_id"),
            ["work_order_id"],
            unique=False,
        )

    # Index manquant dans la migration 0004 (déjà présent dans le modèle).
    with op.batch_alter_table("work_orders", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_work_orders_created_by_id"),
            ["created_by_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("work_orders", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_work_orders_created_by_id"))

    with op.batch_alter_table("tool_usages", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_tool_usages_work_order_id"))
        batch_op.drop_index(batch_op.f("ix_tool_usages_used_by_id"))
        batch_op.drop_index(batch_op.f("ix_tool_usages_tool_id"))
        batch_op.drop_index(batch_op.f("ix_tool_usages_started_on"))
        batch_op.drop_index(batch_op.f("ix_tool_usages_ended_on"))
    op.drop_table("tool_usages")

    with op.batch_alter_table("tool_calibrations", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_tool_calibrations_tool_id"))
        batch_op.drop_index(batch_op.f("ix_tool_calibrations_result"))
        batch_op.drop_index(batch_op.f("ix_tool_calibrations_provider_id"))
        batch_op.drop_index(batch_op.f("ix_tool_calibrations_next_due_date"))
        batch_op.drop_index(batch_op.f("ix_tool_calibrations_calibrated_on"))
    op.drop_table("tool_calibrations")

    with op.batch_alter_table("maintenance_tools", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_maintenance_tools_status"))
        batch_op.drop_index(batch_op.f("ix_maintenance_tools_site_id"))
        batch_op.drop_index(batch_op.f("ix_maintenance_tools_next_calibration_date"))
        batch_op.drop_index(batch_op.f("ix_maintenance_tools_is_active"))
        batch_op.drop_index(batch_op.f("ix_maintenance_tools_code"))
        batch_op.drop_index(batch_op.f("ix_maintenance_tools_category"))
        batch_op.drop_index(
            batch_op.f("ix_maintenance_tools_calibration_provider_id")
        )
    op.drop_table("maintenance_tools")

    with op.batch_alter_table("stock_movements", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_stock_movements_work_order_id"))
        batch_op.drop_index(batch_op.f("ix_stock_movements_spare_part_id"))
        batch_op.drop_index(batch_op.f("ix_stock_movements_movement_type"))
        batch_op.drop_index(batch_op.f("ix_stock_movements_movement_date"))
        batch_op.drop_index(batch_op.f("ix_stock_movements_actor_id"))
    op.drop_table("stock_movements")

    with op.batch_alter_table("spare_parts", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_spare_parts_supplier_id"))
        batch_op.drop_index(batch_op.f("ix_spare_parts_site_id"))
        batch_op.drop_index(batch_op.f("ix_spare_parts_is_active"))
        batch_op.drop_index(batch_op.f("ix_spare_parts_code"))
        batch_op.drop_index(batch_op.f("ix_spare_parts_category"))
    op.drop_table("spare_parts")
