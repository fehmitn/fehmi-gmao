"""Jeu de données de démonstration.

Usage :
    python scripts/seed.py            # ajoute les données manquantes
    python scripts/seed.py --reset    # repart d'une base vide

Le jeu met volontairement en scène la fonctionnalité centrale du projet :
une saisie **antidatée** (implantation rétrospective) qui exige un motif de
dérogation, et un déplacement lui aussi saisi en retard.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import Session  # noqa: E402

from app.database import Base, SessionLocal, engine, init_db  # noqa: E402
from app.models.enums import AuditAction, Criticality, EquipmentStatus, MovementType  # noqa: E402
from app.repositories.location_type import LocationTypeRepository  # noqa: E402
from app.repositories.user import UserRepository  # noqa: E402
from app.schemas.equipment import EquipmentCreate, PlacementCreate  # noqa: E402
from app.schemas.equipment_type import EquipmentTypeCreate  # noqa: E402
from app.schemas.location import LocationCreate  # noqa: E402
from app.schemas.site import SiteCreate  # noqa: E402
from app.services.equipment_service import EquipmentService  # noqa: E402
from app.services.equipment_type_service import EquipmentTypeService  # noqa: E402
from app.services.location_service import LocationService  # noqa: E402
from app.services.placement_service import PlacementService  # noqa: E402
from app.services.site_service import SiteService  # noqa: E402

TODAY = date.today()


def seed(db: Session) -> None:
    site_service = SiteService(db)
    location_service = LocationService(db)
    type_service = EquipmentTypeService(db)
    equipment_service = EquipmentService(db)
    placement_service = PlacementService(db)

    users = {user.username: user for user in UserRepository(db).list_active()}
    admin = users.get("admin")
    technicien = users.get("technicien")

    location_types = {
        item.code: item for item in LocationTypeRepository(db).list_all()
    }

    if site_service.repository.get_by_code("USN-01"):
        print("Le jeu de démonstration est déjà présent : seed ignoré (utilisez --reset).")
        return

    # ------------------------------------------------------------- usines
    casa = site_service.create(
        SiteCreate(
            code="USN-01",
            name="Usine de Casablanca — Sidi Bernoussi",
            description="Site principal : production de beverages.",
            address="Zone industrielle Sidi Bernoussi, lot 42",
            city="Casablanca",
            country="Maroc",
            timezone="Africa/Casablanca",
        ),
        actor=admin,
    )
    tanger = site_service.create(
        SiteCreate(
            code="USN-02",
            name="Usine de Tanger — Melloussa",
            description="Site secondaire : conditionnement.",
            city="Tanger",
            country="Maroc",
            timezone="Africa/Tangier",
        ),
        actor=admin,
    )

    # -------------------------------------------------------- emplacements
    bat_a = location_service.create(
        LocationCreate(
            site_id=casa.id,
            location_type_id=location_types["BAT"].id,
            code="BAT-01",
            name="Bâtiment A — Production",
            description="Halle principale, 4 000 m².",
        ),
        actor=admin,
    )
    atelier_mec = location_service.create(
        LocationCreate(
            site_id=casa.id,
            parent_id=bat_a.id,
            location_type_id=location_types["ATL"].id,
            code="ATL-01",
            name="Atelier mécanique",
        ),
        actor=admin,
    )
    zone_pompes = location_service.create(
        LocationCreate(
            site_id=casa.id,
            parent_id=atelier_mec.id,
            location_type_id=location_types["ZON"].id,
            code="ZON-01",
            name="Zone des pompes et utilités",
        ),
        actor=admin,
    )
    ligne_cond = location_service.create(
        LocationCreate(
            site_id=casa.id,
            parent_id=bat_a.id,
            location_type_id=location_types["LIG"].id,
            code="LIG-01",
            name="Ligne de conditionnement n°1",
        ),
        actor=admin,
    )
    bat_b = location_service.create(
        LocationCreate(
            site_id=tanger.id,
            location_type_id=location_types["BAT"].id,
            code="BAT-02",
            name="Bâtiment B — Conditionnement",
        ),
        actor=admin,
    )
    atelier_elec = location_service.create(
        LocationCreate(
            site_id=tanger.id,
            parent_id=bat_b.id,
            location_type_id=location_types["ATL"].id,
            code="ATL-02",
            name="Atelier électricité",
        ),
        actor=admin,
    )
    local_tgbt = location_service.create(
        LocationCreate(
            site_id=tanger.id,
            parent_id=atelier_elec.id,
            location_type_id=location_types["SAL"].id,
            code="SAL-01",
            name="Local TGBT",
            description="Tableau général basse tension.",
        ),
        actor=admin,
    )

    # --------------------------------------------------- types d'équipements
    types = {}
    for payload in [
        EquipmentTypeCreate(
            code="PMP-CF",
            name="Pompe centrifuge",
            category="Pompes",
            manufacturer="Grundfos",
            model="CR 15-6",
            description="Pompe centrifuge à axe horizontal.",
            criticality=Criticality.B,
            technical_specs={"débit_m3h": 16, "pression_bar": 8, "puissance_kw": 2.2},
        ),
        EquipmentTypeCreate(
            code="MOT-AS",
            name="Moteur asynchrone triphasé",
            category="Moteurs",
            manufacturer="Siemens",
            model="1LE1 5.5 kW",
            criticality=Criticality.A,
            technical_specs={"puissance_kw": 5.5, "vitesse_rpm": 1450},
        ),
        EquipmentTypeCreate(
            code="CMP-PN",
            name="Compresseur à piston",
            category="Compresseurs",
            manufacturer="Atlas Copco",
            model="GA 11",
            criticality=Criticality.A,
        ),
        EquipmentTypeCreate(
            code="GRP-ELE",
            name="Groupe électrogène",
            category="Énergie",
            manufacturer="Caterpillar",
            model="C18 ACERT",
            criticality=Criticality.A,
        ),
        EquipmentTypeCreate(
            code="CNV-BD",
            name="Convoyeur à bande",
            category="Convoyage",
            manufacturer="Interroll",
            model="1500 mm",
            criticality=Criticality.C,
        ),
    ]:
        types[payload.code] = type_service.create(payload, actor=admin)

    # ------------------------------------------------------------ équipements
    def equipment(
        code,
        name,
        type_code,
        location,
        criticality=Criticality.B,
        status=EquipmentStatus.OPERATIONAL,
        commissioning=None,
        effective_from=None,
        derogation=None,
        cost=None,
        is_critical=False,
    ):
        return equipment_service.create(
            EquipmentCreate(
                code=code,
                name=name,
                equipment_type_id=types[type_code].id,
                location_id=location.id,
                status=status,
                criticality=criticality,
                commissioning_date=commissioning,
                effective_from=effective_from,
                derogation_reason=derogation,
                acquisition_cost=cost,
                is_critical=is_critical,
            ),
            actor=admin,
        )

    # Implantation en temps réel (cas nominal)
    equipment("PMP-001", "Pompe d'alimentation ligne 1", "PMP-CF", zone_pompes,
              cost=18500, commissioning=TODAY - timedelta(days=900))
    equipment("PMP-002", "Pompe de transfert ligne 1", "PMP-CF", zone_pompes,
              status=EquipmentStatus.MAINTENANCE, cost=18500)

    # Implantation ANTIDATÉE : la machine existait avant le GMAO.
    # -> le moteur de rétrodatation exige un motif de dérogation.
    equipment("MOT-001", "Moteur convoyeur L1", "MOT-AS", ligne_cond,
              criticality=Criticality.A, is_critical=True, cost=9200,
              commissioning=TODAY - timedelta(days=1200),
              effective_from=TODAY - timedelta(days=1200),
              derogation="Machine acquise lors du transfert de l'ancienne ligne ; "
                        "reprise de l'inventaire papier de l'atelier.")
    equipment("CNV-001", "Convoyeur de liaison L1→L2", "CNV-BD", ligne_cond,
              criticality=Criticality.C, cost=6400,
              commissioning=TODAY - timedelta(days=400),
              effective_from=TODAY - timedelta(days=400),
              derogation="Reprise d'inventaire : convoyeur déplacé depuis l'atelier "
                        "de maintenance vers la ligne de conditionnement.")

    equipment("CMP-001", "Compresseur d'atelier", "CMP-PN", atelier_mec,
              criticality=Criticality.A, is_critical=True, cost=42000,
              commissioning=TODAY - timedelta(days=2000),
              effective_from=TODAY - timedelta(days=2000),
              derogation="Reprise d'inventaire de l'atelier mécanique (hors GMAO).")
    equipment("GRP-001", "Groupe électrogène de secours", "GRP-ELE", local_tgbt,
              criticality=Criticality.A, is_critical=True, cost=96000,
              commissioning=TODAY - timedelta(days=700),
              effective_from=TODAY - timedelta(days=700),
              derogation="Reprise d'inventaire : groupe de secours mis en service "
                        "avant l'informatisation de la maintenance.")
    equipment("MOT-002", "Moteur pompe de secours", "MOT-AS", zone_pompes,
              criticality=Criticality.B, cost=5100)
    equipment("PMP-003", "Pompe de secours ligne 2", "PMP-CF", zone_pompes, cost=18500)

    # ------------------------------------------------------ déplacements
    # Déplacement saisi en retard : la date d'effet est antérieure à aujourd'hui.
    motor = equipment_service.get(
        equipment_service.list(search="MOT-001").items[0].id
    )
    placement_service.move(
        motor,
        PlacementCreate(
            location_id=atelier_mec.id,
            effective_from=TODAY - timedelta(days=30),
            movement_type=MovementType.DEPLACEMENT,
            reason="Reprise de la ligne de conditionnement : moteur démonté pour "
                   "confection et rangé en atelier mécanique.",
            derogation_reason="Déplacement effectué il y a un mois, non saisi à "
                              "l'époque (backlog de saisie).",
        ),
        actor=technicien,
    )

    compresseur = equipment_service.get(
        equipment_service.list(search="CMP-001").items[0].id
    )
    placement_service.move(
        compresseur,
        PlacementCreate(
            location_id=zone_pompes.id,
            effective_from=TODAY,
            movement_type=MovementType.TRANSFERT,
            reason="Transfert vers la zone des utilités pour maintenance corrective.",
        ),
        actor=technicien,
    )

    print("Jeu de démonstration inséré :")
    print(f"  {len(site_service.list())} usines")
    print(f"  {len(location_service.list_all())} emplacements")
    print(f"  {len(type_service.list())} types d'équipements")
    print(f"  {equipment_service.list(size=200).total} équipements")
    print("  2 déplacements (dont 1 saisi en retard)")


def main() -> None:
    reset = "--reset" in sys.argv
    if reset:
        print("Réinitialisation de la base…")
        Base.metadata.drop_all(bind=engine)
    init_db()

    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
