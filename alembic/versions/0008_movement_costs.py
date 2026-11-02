"""Coût unitaire figé sur les mouvements de stock.

Ajoute ``stock_movements.unit_cost`` afin de conserver le prix unitaire de la
pièce au moment du mouvement. Le coût d'une sortie reste ainsi exact même si
la fiche de la pièce est revalorisée plus tard.

Les mouvements existants sont initialisés avec le coût unitaire courant de
leur pièce ; les mouvements futurs capturent la valeur au moment de la saisie.

Revision ID: 0008_movement_costs
Revises: 0007_work_order_timestamps
Create Date: 2026-11-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_movement_costs"
down_revision: str | None = "0007_work_order_timestamps"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("stock_movements", schema=None) as batch_op:
        batch_op.add_column(sa.Column("unit_cost", sa.Numeric(precision=12, scale=2), nullable=True))

    op.execute(
        """
        UPDATE stock_movements
        SET unit_cost = (
            SELECT spare_parts.unit_cost
            FROM spare_parts
            WHERE spare_parts.id = stock_movements.spare_part_id
        )
        WHERE unit_cost IS NULL
        """
    )


def downgrade() -> None:
    with op.batch_alter_table("stock_movements", schema=None) as batch_op:
        batch_op.drop_column("unit_cost")
