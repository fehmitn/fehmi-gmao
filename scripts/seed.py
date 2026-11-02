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
from app.models.enums import (  # noqa: E402
    AuditAction,
    Criticality,
    EquipmentStatus,
    MaintenanceAnchor,
    MaintenanceIntervalUnit,
    MaintenanceType,
    MovementType,
)
from app.repositories.location_type import LocationTypeRepository  # noqa: E402
from app.repositories.user import UserRepository  # noqa: E402
from app.schemas.equipment import EquipmentCreate, PlacementCreate  # noqa: E402
from app.schemas.equipment_type import EquipmentTypeCreate  # noqa: E402
from app.schemas.location import LocationCreate  # noqa: E402
from app.schemas.maintenance_execution import MaintenanceExecutionCreate  # noqa: E402
from app.schemas.maintenance_supplier import MaintenanceSupplierCreate  # noqa: E402
from app.schemas.periodic_maintenance import PeriodicMaintenanceCreate  # noqa: E402
from app.schemas.site import SiteCreate  # noqa: E402
from app.services.clock import today  # noqa: E402
from app.services.equipment_service import EquipmentService  # noqa: E402
from app.services.equipment_type_service import EquipmentTypeService  # noqa: E402
from app.services.location_service import LocationService  # noqa: E402
from app.services.maintenance_execution_service import (  # noqa: E402
    MaintenanceExecutionService,
)
from app.services.maintenance_supplier_service import (  # noqa: E402
    MaintenanceSupplierService,
)
from app.services.periodic_maintenance_service import (  # noqa: E402
    PeriodicMaintenanceService,
)
from app.services.periodicity import reference_due_date  # noqa: E402
from app.services.placement_service import PlacementService  # noqa: E402
from app.services.site_service import SiteService  # noqa: E402

TODAY = today()


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
    equipments = {}

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
        operating_hours=None,
        initial_operating_hours=0,
    ):
        item = equipment_service.create(
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
                operating_hours=operating_hours,
                initial_operating_hours=initial_operating_hours,
            ),
            actor=admin,
        )
        equipments[code] = item
        return item

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
              derogation="Reprise d'inventaire de l'atelier mécanique (hors GMAO).",
              operating_hours=1995, initial_operating_hours=0)
    equipment("GRP-001", "Groupe électrogène de secours", "GRP-ELE", local_tgbt,
              criticality=Criticality.A, is_critical=True, cost=96000,
              commissioning=TODAY - timedelta(days=700),
              effective_from=TODAY - timedelta(days=700),
              derogation="Reprise d'inventaire : groupe de secours mis en service "
                        "avant l'informatisation de la maintenance.",
              operating_hours=412, initial_operating_hours=0)
    equipment("MOT-002", "Moteur pompe de secours", "MOT-AS", zone_pompes,
              criticality=Criticality.B, cost=5100)
    equipment("PMP-003", "Pompe de secours ligne 2", "PMP-CF", zone_pompes, cost=18500)

    # ------------------------------------------- fournisseurs de maintenance
    supplier_service = MaintenanceSupplierService(db)
    suppliers = {}
    for payload in [
        MaintenanceSupplierCreate(
            code="SUP-MECA",
            name="Mécanique Industrielle du Grand Casablanca",
            contact_name="Youssef Bennani",
            phone="+212 522 00 11 22",
            email="contact@meca-casa.example",
            specialty="Mécanique, hydraulique, graissage",
            notes="Prestataire historique des pompes et compresseurs.",
        ),
        MaintenanceSupplierCreate(
            code="SUP-ELEC",
            name="Électro-Services Tanger",
            contact_name="Salma El Idrissi",
            phone="+212 539 00 33 44",
            email="planning@electro-tanger.example",
            specialty="Électricité, automatisme, groupes électrogènes",
        ),
        MaintenanceSupplierCreate(
            code="SUP-REG",
            name="Bureau de Contrôle Réglementaire",
            contact_name="Hamid Alaoui",
            phone="+212 537 00 55 66",
            email="inspections@bcr.example",
            specialty="Contrôles réglementaires et inspections périodiques",
        ),
    ]:
        suppliers[payload.code] = supplier_service.create(payload, actor=admin)

    # ----------------------------------- contraintes périodiques par famille
    rule_service = PeriodicMaintenanceService(db)
    rules = {}

    def periodic(
        type_code,
        code,
        label,
        interval_value,
        interval_unit,
        *,
        maintenance_type=MaintenanceType.PREVENTIVE_SYSTEMATIC,
        anchor=MaintenanceAnchor.COMMISSIONING,
        fixed_date=None,
        supplier=None,
        tolerance_days=0,
        estimated_duration_minutes=None,
        sort_order=0,
        description=None,
    ):
        rules[(type_code, code)] = rule_service.create(
            types[type_code].id,
            PeriodicMaintenanceCreate(
                code=code,
                label=label,
                description=description,
                interval_value=interval_value,
                interval_unit=interval_unit,
                maintenance_type=maintenance_type,
                anchor=anchor,
                fixed_date=fixed_date,
                supplier_id=suppliers[supplier].id if supplier else None,
                tolerance_days=tolerance_days,
                estimated_duration_minutes=estimated_duration_minutes,
                sort_order=sort_order,
            ),
            actor=admin,
        )

    # Pompes centrifuges
    periodic(
        "PMP-CF", "GRAISSAGE", "Graissage des paliers et accouplement",
        3, MaintenanceIntervalUnit.MONTHS, supplier="SUP-MECA",
        tolerance_days=7, estimated_duration_minutes=45, sort_order=10,
        description="Graisser les deux paliers et contrôler l'accouplement.",
    )
    periodic(
        "PMP-CF", "ETANCHEITE", "Contrôle d'étanchéité et garniture mécanique",
        12, MaintenanceIntervalUnit.MONTHS,
        maintenance_type=MaintenanceType.PREVENTIVE_CONDITIONAL,
        supplier="SUP-MECA", estimated_duration_minutes=90, sort_order=20,
    )
    periodic(
        "PMP-CF", "INSPECTION-REG", "Inspection réglementaire des équipements sous pression",
        12, MaintenanceIntervalUnit.MONTHS,
        maintenance_type=MaintenanceType.REGULATORY,
        anchor=MaintenanceAnchor.FIXED_DATE,
        fixed_date=TODAY - timedelta(days=45),
        supplier="SUP-REG", estimated_duration_minutes=120, sort_order=30,
        description="Échéance fixe indépendante de la mise en service de la machine.",
    )

    # Moteurs asynchrones
    periodic(
        "MOT-AS", "CONTROLE-ISO", "Contrôle d'isolement et serrage des connexions",
        12, MaintenanceIntervalUnit.MONTHS,
        maintenance_type=MaintenanceType.INSPECTION,
        supplier="SUP-ELEC", tolerance_days=15,
        estimated_duration_minutes=60, sort_order=10,
    )
    periodic(
        "MOT-AS", "GRAISSAGE-ROULEMENTS", "Graissage des roulements",
        6, MaintenanceIntervalUnit.MONTHS, supplier="SUP-MECA",
        tolerance_days=10, estimated_duration_minutes=30, sort_order=20,
    )

    # Compresseurs
    periodic(
        "CMP-PN", "VIDANGE", "Vidange et remplacement du filtre à huile",
        6, MaintenanceIntervalUnit.MONTHS, supplier="SUP-MECA",
        tolerance_days=10, estimated_duration_minutes=120, sort_order=10,
    )
    periodic(
        "CMP-PN", "COURROIE", "Contrôle et tension de la courroie",
        3, MaintenanceIntervalUnit.MONTHS,
        maintenance_type=MaintenanceType.INSPECTION,
        supplier="SUP-MECA", tolerance_days=7,
        estimated_duration_minutes=30, sort_order=20,
    )
    periodic(
        "CMP-PN", "VIDANGE-HEURES", "Vidange selon les heures de fonctionnement",
        500, MaintenanceIntervalUnit.HOURS, supplier="SUP-MECA",
        estimated_duration_minutes=120, sort_order=30,
        description="Seuil calculé sur le compteur horaire : pas de date prévisible.",
    )

    # Groupes électrogènes
    periodic(
        "GRP-ELE", "ESSAI-SECOURS", "Essai mensuel de démarrage en charge",
        1, MaintenanceIntervalUnit.MONTHS,
        maintenance_type=MaintenanceType.REGULATORY,
        supplier="SUP-ELEC", tolerance_days=2,
        estimated_duration_minutes=30, sort_order=10,
    )
    periodic(
        "GRP-ELE", "VIDANGE", "Vidange moteur et contrôle des niveaux",
        12, MaintenanceIntervalUnit.MONTHS, supplier="SUP-MECA",
        tolerance_days=20, estimated_duration_minutes=180, sort_order=20,
    )
    periodic(
        "GRP-ELE", "ESSAI-HEURES", "Essai de charge selon les heures de marche",
        250, MaintenanceIntervalUnit.HOURS, supplier="SUP-ELEC",
        estimated_duration_minutes=45, sort_order=30,
        description="Contrôle déclenché à l'approche du seuil de 250 heures.",
    )

    # Convoyeurs : ancrage sur la première implantation
    periodic(
        "CNV-BD", "TENSION-BANDE", "Contrôle de tension et alignement de la bande",
        1, MaintenanceIntervalUnit.MONTHS,
        anchor=MaintenanceAnchor.FIRST_PLACEMENT,
        supplier="SUP-MECA", tolerance_days=5,
        estimated_duration_minutes=20, sort_order=10,
    )

    # ------------------------------------- réalisations d'OT (retards loggés)
    execution_service = MaintenanceExecutionService(db)

    def log_execution(equipment_code, type_code, rule_code, days_late, notes):
        equipment = equipments[equipment_code]
        rule = rules[(type_code, rule_code)]
        if rule.anchor == MaintenanceAnchor.FIXED_DATE.value:
            anchor = rule.fixed_date
        else:
            anchor = equipment.commissioning_date
        reference = reference_due_date(
            anchor,
            rule.interval_value,
            rule.interval_unit,
            TODAY - timedelta(days=2),
            anchor_kind=rule.anchor,
        )
        performed_on = reference + timedelta(days=days_late)
        if performed_on > TODAY:
            performed_on = TODAY
        execution_service.create(
            equipment,
            rule,
            MaintenanceExecutionCreate(
                periodic_maintenance_id=rule.id,
                performed_on=performed_on,
                notes=notes,
            ),
            actor=technicien or admin,
        )

    log_execution(
        "PMP-001", "PMP-CF", "GRAISSAGE", 12,
        "Graissage réalisé avec 12 jours de retard sur l'échéance théorique.",
    )
    log_execution(
        "CMP-001", "CMP-PN", "VIDANGE", 20,
        "Vidange faite en retard : attente d'une fenêtre d'arrêt de l'atelier.",
    )
    log_execution(
        "GRP-001", "GRP-ELE", "ESSAI-SECOURS", 3,
        "Essai mensuel décalé de 3 jours (astreinte indisponible).",
    )

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
    print(f"  {len(supplier_service.list())} fournisseurs de maintenance")
    print(f"  {len(rule_service.list_all())} contraintes périodiques")
    print("  3 réalisations d'OT (dont 3 en retard)")
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
