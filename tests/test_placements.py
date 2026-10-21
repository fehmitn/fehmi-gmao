"""Historique d'implantation : déplacements, périodes, cohérence."""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.errors import ValidationError
from app.models.enums import MovementType
from app.schemas.equipment import EquipmentCreate, PlacementCreate
from app.services.equipment_service import EquipmentService
from app.services.placement_service import PlacementService
from tests.conftest import REFERENCE_DATE


def test_un_equipement_na_quune_seule_implantation_ouverte(db, equipment):
    service = PlacementService(db)

    courante = service.current(equipment.id)

    assert courante is not None
    assert courante.effective_to is None
    assert len(service.history(equipment.id)) == 1


def test_deplacement_ferme_la_periode_precedente(db, ancien_equipement, locations):
    service = PlacementService(db)

    service.move(
        ancien_equipement,
        PlacementCreate(
            location_id=locations["atelier"].id,
            effective_from=REFERENCE_DATE - timedelta(days=10),
            movement_type=MovementType.DEPLACEMENT,
            reason="Réorganisation",
            derogation_reason="Déplacement effectué mais non saisi à l'époque",
        ),
    )

    historique = service.history(ancien_equipement.id)
    assert len(historique) == 2
    ancienne = historique[1]
    nouvelle = historique[0]
    assert nouvelle.effective_to is None
    assert ancienne.effective_to == REFERENCE_DATE - timedelta(days=11)
    assert ancienne.effective_from <= ancienne.effective_to


def test_emplacement_at_date_repond_a_l_historique(db, ancien_equipement, locations):
    service = PlacementService(db)
    service.move(
        ancien_equipement,
        PlacementCreate(
            location_id=locations["atelier"].id,
            effective_from=REFERENCE_DATE - timedelta(days=10),
            derogation_reason="Déplacement effectué mais non saisi à l'époque",
        ),
    )

    avant = service.at_date(ancien_equipement.id, REFERENCE_DATE - timedelta(days=50))
    apres = service.at_date(ancien_equipement.id, REFERENCE_DATE - timedelta(days=2))

    assert avant.location_id == locations["zone"].id
    assert apres.location_id == locations["atelier"].id


def test_deplacement_antidate_met_a_jour_l_historique(db, ancien_equipement, locations):
    """Un déplacement saisi en retard repositionne aussi le passé."""
    service = PlacementService(db)
    service.move(
        ancien_equipement,
        PlacementCreate(
            location_id=locations["atelier"].id,
            effective_from=REFERENCE_DATE - timedelta(days=20),
            derogation_reason="Déplacement effectué mais non saisi",
        ),
    )

    historique = service.history(ancien_equipement.id)
    ancienne = historique[1]
    assert ancienne.effective_to == REFERENCE_DATE - timedelta(days=21)
    assert historique[0].entry_delay_days == 20
    assert historique[0].derogation_reason == "Déplacement effectué mais non saisi"


def test_un_deplacement_du_jour_est_possible(db, ancien_equipement, locations):
    """Déplacer un équipement à la date du jour ne demande pas de dérogation."""
    service = PlacementService(db)

    service.move(
        ancien_equipement,
        PlacementCreate(
            location_id=locations["atelier"].id,
            effective_from=REFERENCE_DATE,
        ),
    )

    courante = service.current(ancien_equipement.id)
    assert courante.location_id == locations["atelier"].id
    assert courante.entry_delay_days is None


def test_deplacement_refuse_si_la_date_precede_l_implantation(db, ancien_equipement, locations):
    service = PlacementService(db)

    with pytest.raises(ValidationError):
        service.move(
            ancien_equipement,
            PlacementCreate(
                location_id=locations["atelier"].id,
                effective_from=REFERENCE_DATE - timedelta(days=200),
                derogation_reason="Trop tard",
            ),
        )


def test_deplacement_refuse_si_l_emplacement_est_inchange(db, ancien_equipement):
    service = PlacementService(db)

    with pytest.raises(ValidationError):
        service.move(
            ancien_equipement,
            PlacementCreate(location_id=ancien_equipement.placements[0].location_id),
        )


def test_deplacement_vers_une_autre_usine_met_a_jour_l_usine(
    db, ancien_equipement, location_type, admin
):
    from app.schemas.location import LocationCreate
    from app.schemas.site import SiteCreate
    from app.services.location_service import LocationService
    from app.services.site_service import SiteService

    nouvelle_usine = SiteService(db).create(
        SiteCreate(code="USN-02", name="Usine secondaire"),
        actor=admin,
    )
    nouvel_emplacement = LocationService(db).create(
        LocationCreate(
            site_id=nouvelle_usine.id,
            location_type_id=location_type.id,
            code="BAT-77",
            name="Bâtiment secondaire",
        )
    )

    PlacementService(db).move(
        ancien_equipement,
        PlacementCreate(
            location_id=nouvel_emplacement.id,
            effective_from=REFERENCE_DATE - timedelta(days=5),
            derogation_reason="Transfert vers l'autre usine",
        ),
    )

    db.refresh(ancien_equipement)
    assert ancien_equipement.site_id == nouvelle_usine.id


def test_installation_avec_date_passee_exige_une_derogation(db, locations):
    service = EquipmentService(db)

    with pytest.raises(Exception) as exc:
        service.create(
            EquipmentCreate(
                code="PMP-BACK",
                name="Pompe rétroactive",
                location_id=locations["zone"].id,
                effective_from=REFERENCE_DATE - timedelta(days=30),
            )
        )

    assert "motif de dérogation" in str(exc.value)


def test_installation_avec_date_passee_et_derogation(db, locations):
    service = EquipmentService(db)

    cree = service.create(
        EquipmentCreate(
            code="PMP-BACK",
            name="Pompe rétroactive justifiée",
            location_id=locations["zone"].id,
            effective_from=REFERENCE_DATE - timedelta(days=30),
            derogation_reason="Reprise d'inventaire papier",
        )
    )

    implantation = service.placement_service.current(cree.id)
    assert implantation.entry_delay_days == 30
    assert implantation.derogation_reason == "Reprise d'inventaire papier"


def test_un_equipement_sans_implantation_peut_etre_implante(
    db, equipement_non_implante, locations
):
    """Cas des équipements hérités de la v0.1 : le déplacement ouvre la
    première période d'implantation."""
    service = PlacementService(db)

    assert service.current(equipement_non_implante.id) is None

    implantation = service.move(
        equipement_non_implante,
        PlacementCreate(
            location_id=locations["zone"].id,
            effective_from=REFERENCE_DATE,
            reason="Emplacement réel retrouvé lors de l'inventaire",
        ),
    )

    assert implantation.movement_type == "installation"
    assert implantation.effective_to is None
    assert service.current(equipement_non_implante.id) is implantation


def test_implantation_antidatee_sur_un_equipement_sans_implantation(
    db, equipement_non_implante, locations
):
    service = PlacementService(db)

    with pytest.raises(Exception) as exc:
        service.move(
            equipement_non_implante,
            PlacementCreate(
                location_id=locations["zone"].id,
                effective_from=REFERENCE_DATE - timedelta(days=45),
            ),
        )

    assert "motif de dérogation" in str(exc.value)


def test_implantation_antidatee_justifiee_sur_un_equipement_sans_implantation(
    db, equipement_non_implante, locations
):
    service = PlacementService(db)

    implantation = service.move(
        equipement_non_implante,
        PlacementCreate(
            location_id=locations["zone"].id,
            effective_from=REFERENCE_DATE - timedelta(days=45),
            derogation_reason="Machine déjà sur site lors de l'inventaire",
        ),
    )

    assert implantation.entry_delay_days == 45
    assert implantation.derogation_reason == "Machine déjà sur site lors de l'inventaire"
