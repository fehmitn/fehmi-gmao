"""Inventaire des équipements : unicité, pré-remplissage, filtres."""

from __future__ import annotations

import pytest

from app.errors import ConflictError, FutureDateNotAllowed
from app.models.enums import EquipmentStatus
from app.schemas.equipment import EquipmentCreate, EquipmentUpdate
from app.services.equipment_service import EquipmentService
from app.services.equipment_type_service import EquipmentTypeService
from app.schemas.equipment_type import EquipmentTypeCreate
from tests.conftest import REFERENCE_DATE


def test_le_code_est_unique(db, equipment, locations, equipment_type, admin):
    service = EquipmentService(db)

    with pytest.raises(ConflictError):
        service.create(
            EquipmentCreate(
                code="PMP-001",
                name="Doublon",
                location_id=locations["zone"].id,
                equipment_type_id=equipment_type.id,
            ),
            actor=admin,
        )


def test_un_equipement_est_cree_avec_son_implantation(db, equipment, locations):
    service = EquipmentService(db)

    historique = service.placement_service.history(equipment.id)

    assert len(historique) == 1
    assert historique[0].location_id == locations["zone"].id
    assert historique[0].movement_type == "installation"
    assert historique[0].effective_from == REFERENCE_DATE


def test_le_type_pre_remplit_constructeur_modele_et_criticite(
    db, locations, equipment_type, admin
):
    service = EquipmentService(db)

    cree = service.create(
        EquipmentCreate(
            code="PMP-002",
            name="Pompe pré-remplie",
            location_id=locations["zone"].id,
            equipment_type_id=equipment_type.id,
        ),
        actor=admin,
    )

    assert cree.manufacturer == "Grundfos"
    assert cree.model == "CR 15-6"
    assert cree.criticality == "B"


def test_une_mise_en_service_dans_le_futur_est_refusee(db, locations, equipment_type, admin):
    service = EquipmentService(db)

    with pytest.raises(FutureDateNotAllowed):
        service.create(
            EquipmentCreate(
                code="PMP-003",
                name="Pompe future",
                location_id=locations["zone"].id,
                equipment_type_id=equipment_type.id,
                commissioning_date=REFERENCE_DATE.replace(year=REFERENCE_DATE.year + 1),
            ),
            actor=admin,
        )


def test_le_code_ne_peut_pas_etre_duplique_a_la_modification(db, equipment, locations, admin):
    service = EquipmentService(db)
    autre = service.create(
        EquipmentCreate(
            code="PMP-002",
            name="Autre pompe",
            location_id=locations["zone"].id,
        ),
        actor=admin,
    )

    with pytest.raises(ConflictError):
        service.update(autre, EquipmentUpdate(code="PMP-001"), actor=admin)


def test_modification_du_statut(db, equipment, admin):
    service = EquipmentService(db)

    mis_a_jour = service.update(
        equipment, EquipmentUpdate(status=EquipmentStatus.MAINTENANCE), actor=admin
    )

    assert mis_a_jour.status == "maintenance"


def test_filtre_par_categorie_de_type(db, equipment, locations, equipment_type, admin):
    service = EquipmentService(db)
    autre_type = EquipmentTypeService(db).create(
        EquipmentTypeCreate(code="MOT-AS", name="Moteur", category="Moteurs"),
        actor=admin,
    )
    service.create(
        EquipmentCreate(
            code="MOT-001",
            name="Moteur",
            location_id=locations["atelier"].id,
            equipment_type_id=autre_type.id,
        ),
        actor=admin,
    )

    pompes = service.list(category="Pompes")
    moteurs = service.list(category="Moteurs")

    assert [item.code for item in pompes.items] == ["PMP-001"]
    assert [item.code for item in moteurs.items] == ["MOT-001"]


def test_filtre_par_sous_arbre_d_emplacement(db, equipment, locations):
    service = EquipmentService(db)

    depuis_atelier = service.list(location_id=locations["atelier"].id)
    depuis_batiment = service.list(location_id=locations["batiment"].id)
    hors_arbre = service.list(location_id=locations["nord"].id)

    assert [item.code for item in depuis_atelier.items] == ["PMP-001"]
    assert [item.code for item in depuis_batiment.items] == ["PMP-001"]
    assert hors_arbre.items == []


def test_filtre_par_sous_arbre_sans_descendance(db, equipment, locations):
    service = EquipmentService(db)

    depuis_batiment = service.list(
        location_id=locations["batiment"].id, include_descendants=False
    )

    assert depuis_batiment.items == []


def test_recherche_texte(db, equipment):
    service = EquipmentService(db)

    resultat = service.list(search="pompe")

    assert [item.code for item in resultat.items] == ["PMP-001"]


def test_l_equipement_est_enrichi_avec_son_emplacement_courant(db, equipment, locations):
    service = EquipmentService(db)

    lu = service.get(equipment.id)

    assert lu.current_location_code == "ZON-01"
    assert lu.current_location_path == "BAT-01 / ATL-01 / ZON-01"
    assert lu.site_code == "USN-01"
