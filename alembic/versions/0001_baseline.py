"""Schéma initial de la GMAO (usines, emplacements, équipements, audit).

Cette migration met en place le modèle WinMaint transposé :

* ``sites``            <- fiche Clienti / sede
* ``locations``        <- arborescence des emplacements par usine
* ``equipment_types``  <- modèles d'appareils (pré-remplissage)
* ``equipments``       <- articles installés
* ``equipment_locations`` <- historique d'implantation
* ``audit_logs``       <- journal d'audit (traçabilité, dérogations)

Elle absorbe également l'ancienne table ``equipments`` (version 0.1, où
l'emplacement était une simple chaîne) en conservant ses lignes.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-21
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


LOCATION_TYPES = [
    ("BAT", "Bâtiment", "Bâtiment ou halle industrielle", 10),
    ("ATL", "Atelier", "Atelier ou zone de production", 20),
    ("ZON", "Zone", "Zone géographique d'un atelier", 30),
    ("LIG", "Ligne", "Ligne de production", 40),
    ("SAL", "Salle", "Salle technique (local électrique, local pompage...)", 50),
    ("POS", "Poste", "Poste de travail ou machine", 60),
    ("EXT", "Extérieur", "Emplacement extérieur (cuve, Château d'eau...)", 70),
]

USERS = [
    ("admin", "Administrateur", "admin"),
    ("responsable", "Responsable maintenance", "responsable"),
    ("technicien", "Technicien", "technicien"),
    ("lecture", "Consultation", "lecture"),
]


def _to_datetime(value) -> datetime | None:
    """Convertit une date SQLite (chaîne) en datetime, ou None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text_value = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text_value, fmt)
        except ValueError:
            continue
    return None


def _has_legacy_equipments() -> bool:
    """Détecte la table ``equipments`` de la version 0.1 (colonne texte)."""
    inspector = sa.inspect(op.get_bind())
    if "equipments" not in inspector.get_table_names():
        return False
    columns = {column["name"] for column in inspector.get_columns("equipments")}
    return "location" in columns


def upgrade() -> None:
    legacy = _has_legacy_equipments()
    if legacy:
        op.rename_table("equipments", "equipments_legacy")
        # SQLite conserve les index lors d'un renommage : on les libère pour
        # pouvoir recréer la nouvelle table « equipments » avec les mêmes noms.
        inspector = sa.inspect(op.get_bind())
        for index in inspector.get_indexes("equipments_legacy"):
            op.drop_index(index["name"], table_name="equipments_legacy")

    op.create_table(
        "equipment_types",
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("manufacturer", sa.String(length=150), nullable=True),
        sa.Column("model", sa.String(length=150), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("criticality", sa.String(length=1), nullable=True),
        sa.Column("technical_specs", sa.JSON(), nullable=True),
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
    with op.batch_alter_table("equipment_types", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_equipment_types_category"), ["category"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_equipment_types_code"), ["code"], unique=True)
        batch_op.create_index(
            batch_op.f("ix_equipment_types_is_active"), ["is_active"], unique=False
        )

    op.create_table(
        "location_types",
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=300), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("location_types", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_location_types_code"), ["code"], unique=True)

    op.create_table(
        "sites",
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("address", sa.String(length=300), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column("timezone", sa.String(length=50), nullable=True),
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
    with op.batch_alter_table("sites", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_sites_code"), ["code"], unique=True)
        batch_op.create_index(batch_op.f("ix_sites_is_active"), ["is_active"], unique=False)

    op.create_table(
        "users",
        sa.Column("username", sa.String(length=50), nullable=False),
        sa.Column("display_name", sa.String(length=150), nullable=False),
        sa.Column("role", sa.String(length=30), nullable=False),
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
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_users_role"), ["role"], unique=False)
        batch_op.create_index(batch_op.f("ix_users_username"), ["username"], unique=True)

    op.create_table(
        "audit_logs",
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("actor_label", sa.String(length=150), nullable=False),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("audit_logs", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_audit_logs_action"), ["action"], unique=False)
        batch_op.create_index(batch_op.f("ix_audit_logs_actor_id"), ["actor_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_audit_logs_entity_id"), ["entity_id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_audit_logs_entity_type"), ["entity_type"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_audit_logs_occurred_at"), ["occurred_at"], unique=False
        )

    op.create_table(
        "equipments",
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("equipment_type_id", sa.Integer(), nullable=True),
        sa.Column("site_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("criticality", sa.String(length=1), nullable=True),
        sa.Column("manufacturer", sa.String(length=150), nullable=True),
        sa.Column("model", sa.String(length=150), nullable=True),
        sa.Column("serial_number", sa.String(length=100), nullable=True),
        sa.Column("purchase_date", sa.Date(), nullable=True),
        sa.Column("commissioning_date", sa.Date(), nullable=True),
        sa.Column("acquisition_cost", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("warranty_end_date", sa.Date(), nullable=True),
        sa.Column("is_critical", sa.Boolean(), nullable=False),
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
            ["equipment_type_id"], ["equipment_types.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("equipments", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_equipments_code"), ["code"], unique=True)
        batch_op.create_index(
            batch_op.f("ix_equipments_criticality"), ["criticality"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_equipments_equipment_type_id"), ["equipment_type_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_equipments_is_active"), ["is_active"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_equipments_site_id"), ["site_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_equipments_status"), ["status"], unique=False)

    op.create_table(
        "locations",
        sa.Column("site_id", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("location_type_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
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
            ["location_type_id"], ["location_types.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["parent_id"], ["locations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("site_id", "code", name="uq_location_site_code"),
    )
    with op.batch_alter_table("locations", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_locations_is_active"), ["is_active"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_locations_location_type_id"), ["location_type_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_locations_parent_id"), ["parent_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_locations_site_id"), ["site_id"], unique=False)

    op.create_table(
        "equipment_locations",
        sa.Column("equipment_id", sa.Integer(), nullable=False),
        sa.Column("location_id", sa.Integer(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("movement_type", sa.String(length=30), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("entry_delay_days", sa.Integer(), nullable=True),
        sa.Column("derogation_reason", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
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
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["equipment_id"], ["equipments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("equipment_locations", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_equipment_locations_effective_from"),
            ["effective_from"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_equipment_locations_effective_to"), ["effective_to"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_equipment_locations_entry_delay_days"),
            ["entry_delay_days"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_equipment_locations_equipment_id"), ["equipment_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_equipment_locations_location_id"), ["location_id"], unique=False
        )
        batch_op.create_index(
            "uq_equipment_open_placement",
            ["equipment_id"],
            unique=True,
            sqlite_where=sa.text("effective_to IS NULL"),
        )

    # ------------------------------------------------ données de référence
    connection = op.get_bind()
    location_types = sa.table(
        "location_types",
        sa.column("code", sa.String),
        sa.column("label", sa.String),
        sa.column("description", sa.String),
        sa.column("sort_order", sa.Integer),
        sa.column("is_active", sa.Boolean),
    )
    connection.execute(
        location_types.insert(),
        [
            {
                "code": code,
                "label": label,
                "description": description,
                "sort_order": order,
                "is_active": True,
            }
            for code, label, description, order in LOCATION_TYPES
        ],
    )

    users = sa.table(
        "users",
        sa.column("username", sa.String),
        sa.column("display_name", sa.String),
        sa.column("role", sa.String),
        sa.column("is_active", sa.Boolean),
    )
    connection.execute(
        users.insert(),
        [
            {
                "username": username,
                "display_name": display_name,
                "role": role,
                "is_active": True,
            }
            for username, display_name, role in USERS
        ],
    )

    # ------------------------------- reprise des données de la version 0.1
    if legacy:
        _migrate_legacy_equipments(connection)


def _migrate_legacy_equipments(connection) -> None:
    """Reprend les équipements de la version 0.1 (emplacement en texte)."""
    sites = sa.table(
        "sites",
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("is_active", sa.Boolean),
    )
    connection.execute(
        sites.insert(),
        [
            {
                "code": "USINE-HIST",
                "name": "Usine historique (données 0.1)",
                "description": "Conteneur des équipements hérités de la version 0.1.",
                "is_active": True,
            }
        ],
    )
    site_id = connection.execute(
        sa.text("SELECT id FROM sites WHERE code = 'USINE-HIST'")
    ).scalar_one()

    location_types = sa.table("location_types", sa.column("code", sa.String))
    batiment_id = connection.execute(
        sa.text("SELECT id FROM location_types WHERE code = 'BAT'")
    ).scalar_one()

    locations = sa.table(
        "locations",
        sa.column("site_id", sa.Integer),
        sa.column("parent_id", sa.Integer),
        sa.column("location_type_id", sa.Integer),
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("is_active", sa.Boolean),
    )
    connection.execute(
        locations.insert(),
        [
            {
                "site_id": site_id,
                "parent_id": None,
                "location_type_id": batiment_id,
                "code": "NA-001",
                "name": "Non affecté",
                "description": "Équipements hérités dont l'emplacement n'est pas encore saisi.",
                "is_active": True,
            }
        ],
    )
    location_id = connection.execute(
        sa.text("SELECT id FROM locations WHERE code = 'NA-001'")
    ).scalar_one()

    rows = connection.execute(
        sa.text(
            "SELECT code, name, description, category, location, manufacturer, "
            "serial_number, status, created_at, updated_at FROM equipments_legacy"
        )
    ).fetchall()

    equipments = sa.table(
        "equipments",
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("equipment_type_id", sa.Integer),
        sa.column("site_id", sa.Integer),
        sa.column("status", sa.String),
        sa.column("criticality", sa.String),
        sa.column("manufacturer", sa.String),
        sa.column("model", sa.String),
        sa.column("serial_number", sa.String),
        sa.column("purchase_date", sa.Date),
        sa.column("commissioning_date", sa.Date),
        sa.column("acquisition_cost", sa.Numeric),
        sa.column("warranty_end_date", sa.Date),
        sa.column("is_critical", sa.Boolean),
        sa.column("is_active", sa.Boolean),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )
    for row in rows:
        heritage = (
            f"Hérité de la version 0.1 — catégorie : {row.category or 'n.c.'} ; "
            f"emplacement d'origine : {row.location or 'n.c.'}"
        )
        values = {
            "code": row.code,
            "name": row.name,
            "description": row.description or heritage,
            "equipment_type_id": None,
            "site_id": site_id,
            "status": row.status or "operational",
            "criticality": None,
            "manufacturer": row.manufacturer,
            "model": None,
            "serial_number": row.serial_number,
            "purchase_date": None,
            "commissioning_date": None,
            "acquisition_cost": None,
            "warranty_end_date": None,
            "is_critical": False,
            "is_active": True,
        }
        created_at = _to_datetime(row.created_at)
        updated_at = _to_datetime(row.updated_at)
        if created_at is not None:
            values["created_at"] = created_at
        if updated_at is not None:
            values["updated_at"] = updated_at
        connection.execute(equipments.insert(), [values])

    connection.execute(sa.text("DROP TABLE equipments_legacy"))


def downgrade() -> None:
    with op.batch_alter_table("equipment_locations", schema=None) as batch_op:
        batch_op.drop_index(
            "uq_equipment_open_placement", sqlite_where=sa.text("effective_to IS NULL")
        )
        batch_op.drop_index(batch_op.f("ix_equipment_locations_location_id"))
        batch_op.drop_index(batch_op.f("ix_equipment_locations_equipment_id"))
        batch_op.drop_index(batch_op.f("ix_equipment_locations_entry_delay_days"))
        batch_op.drop_index(batch_op.f("ix_equipment_locations_effective_to"))
        batch_op.drop_index(batch_op.f("ix_equipment_locations_effective_from"))

    op.drop_table("equipment_locations")

    with op.batch_alter_table("locations", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_locations_site_id"))
        batch_op.drop_index(batch_op.f("ix_locations_parent_id"))
        batch_op.drop_index(batch_op.f("ix_locations_location_type_id"))
        batch_op.drop_index(batch_op.f("ix_locations_is_active"))
    op.drop_table("locations")

    with op.batch_alter_table("equipments", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_equipments_status"))
        batch_op.drop_index(batch_op.f("ix_equipments_site_id"))
        batch_op.drop_index(batch_op.f("ix_equipments_is_active"))
        batch_op.drop_index(batch_op.f("ix_equipments_equipment_type_id"))
        batch_op.drop_index(batch_op.f("ix_equipments_criticality"))
        batch_op.drop_index(batch_op.f("ix_equipments_code"))
    op.drop_table("equipments")

    with op.batch_alter_table("audit_logs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_audit_logs_occurred_at"))
        batch_op.drop_index(batch_op.f("ix_audit_logs_entity_type"))
        batch_op.drop_index(batch_op.f("ix_audit_logs_entity_id"))
        batch_op.drop_index(batch_op.f("ix_audit_logs_actor_id"))
        batch_op.drop_index(batch_op.f("ix_audit_logs_action"))
    op.drop_table("audit_logs")

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_users_username"))
        batch_op.drop_index(batch_op.f("ix_users_role"))
    op.drop_table("users")

    with op.batch_alter_table("sites", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_sites_is_active"))
        batch_op.drop_index(batch_op.f("ix_sites_code"))
    op.drop_table("sites")

    with op.batch_alter_table("location_types", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_location_types_code"))
    op.drop_table("location_types")

    with op.batch_alter_table("equipment_types", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_equipment_types_is_active"))
        batch_op.drop_index(batch_op.f("ix_equipment_types_code"))
        batch_op.drop_index(batch_op.f("ix_equipment_types_category"))
    op.drop_table("equipment_types")
