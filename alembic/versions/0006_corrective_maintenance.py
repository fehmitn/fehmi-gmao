"""Maintenance corrective : demandes d'intervention et pièces consommées.

Ajoute :
  * les champs de suivi d'une intervention corrective sur ``work_orders``
    (nature corrective, heures précises de début et de fin, compte rendu) ;
  * la table ``intervention_parts`` qui trace les pièces demandées puis
    utilisées, avec le lien vers le mouvement de stock généré.

Les interventions correctives réutilisent la numérotation des OT
(``OT-<année>-<séquence>``) et restent distinctes des OT préventifs grâce au
drapeau ``is_corrective``.

Revision ID: 0006_corrective_maintenance
Revises: 0005_inventory_tools
Create Date: 2026-11-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_corrective_maintenance"
down_revision: str | None = "0005_inventory_tools"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("work_orders", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_corrective",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch_op.add_column(
            sa.Column("intervention_started_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("intervention_ended_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(sa.Column("work_done", sa.Text(), nullable=True))
        batch_op.create_index(
            batch_op.f("ix_work_orders_is_corrective"), ["is_corrective"], unique=False
        )

    op.create_table(
        "intervention_parts",
        sa.Column("work_order_id", sa.Integer(), nullable=False),
        sa.Column("spare_part_id", sa.Integer(), nullable=False),
        sa.Column("requested_quantity", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("used_quantity", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("requested_by_id", sa.Integer(), nullable=True),
        sa.Column("used_by_id", sa.Integer(), nullable=True),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.ForeignKeyConstraint(
            ["requested_by_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["used_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["spare_part_id"], ["spare_parts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["work_order_id"], ["work_orders.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("intervention_parts", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_intervention_parts_requested_by_id"),
            ["requested_by_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_intervention_parts_requested_at"),
            ["requested_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_intervention_parts_spare_part_id"),
            ["spare_part_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_intervention_parts_status"), ["status"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_intervention_parts_used_by_id"),
            ["used_by_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_intervention_parts_work_order_id"),
            ["work_order_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("intervention_parts", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_intervention_parts_work_order_id"))
        batch_op.drop_index(batch_op.f("ix_intervention_parts_used_by_id"))
        batch_op.drop_index(batch_op.f("ix_intervention_parts_status"))
        batch_op.drop_index(batch_op.f("ix_intervention_parts_spare_part_id"))
        batch_op.drop_index(batch_op.f("ix_intervention_parts_requested_at"))
        batch_op.drop_index(batch_op.f("ix_intervention_parts_requested_by_id"))

    op.drop_table("intervention_parts")

    with op.batch_alter_table("work_orders", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_work_orders_is_corrective"))
        batch_op.drop_column("work_done")
        batch_op.drop_column("intervention_ended_at")
        batch_op.drop_column("intervention_started_at")
        batch_op.drop_column("is_corrective")
