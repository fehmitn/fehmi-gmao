"""Pièces de rechange compatibles et pièce réellement consommée.

Ajoute :

* ``spare_part_interchanges`` : relation **orientée** « la pièce A peut
  remplacer la pièce B ». L'inverse n'est pas créé automatiquement ;
* ``intervention_parts.used_spare_part_id`` : pièce réellement sortie du stock
  lorsqu'un technicien choisit une pièce compatible (éventuellement moins
  chère) à la place de la pièce demandée.

Revision ID: 0009_spare_part_interchanges
Revises: 0008_movement_costs
Create Date: 2026-11-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_spare_part_interchanges"
down_revision: str | None = "0008_movement_costs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "spare_part_interchanges",
        sa.Column("part_id", sa.Integer(), nullable=False),
        sa.Column("replaces_id", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
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
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.ForeignKeyConstraint(
            ["part_id"], ["spare_parts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["replaces_id"], ["spare_parts.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "part_id", "replaces_id", name="uq_spare_part_interchange_pair"
        ),
    )
    with op.batch_alter_table("spare_part_interchanges", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_spare_part_interchanges_part_id"),
            ["part_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_spare_part_interchanges_replaces_id"),
            ["replaces_id"],
            unique=False,
        )

    with op.batch_alter_table("intervention_parts", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("used_spare_part_id", sa.Integer(), nullable=True)
        )
        batch_op.create_index(
            batch_op.f("ix_intervention_parts_used_spare_part_id"),
            ["used_spare_part_id"],
            unique=False,
        )
        batch_op.create_foreign_key(
            "fk_intervention_parts_used_spare_part_id",
            "spare_parts",
            ["used_spare_part_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("intervention_parts", schema=None) as batch_op:
        batch_op.drop_constraint(
            "fk_intervention_parts_used_spare_part_id", type_="foreignkey"
        )
        batch_op.drop_index(
            batch_op.f("ix_intervention_parts_used_spare_part_id")
        )
        batch_op.drop_column("used_spare_part_id")

    with op.batch_alter_table("spare_part_interchanges", schema=None) as batch_op:
        batch_op.drop_index(
            batch_op.f("ix_spare_part_interchanges_replaces_id")
        )
        batch_op.drop_index(batch_op.f("ix_spare_part_interchanges_part_id"))
    op.drop_table("spare_part_interchanges")
