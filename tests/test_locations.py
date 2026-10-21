"""Emplacements : arborescence, unicité par usine, absence de cycle."""

from __future__ import annotations

import pytest

from app.errors import ConflictError, ValidationError
from app.schemas.location import LocationCreate
from app.services.location_service import LocationService


def test_chemin_et_profondeur(db, locations):
    service = LocationService(db)

    zone = service.enrich(service.get(locations["zone"].id))

    assert zone.path == "BAT-01 / ATL-01 / ZON-01"
    assert zone.depth == 3
    assert zone.parent_id == locations["atelier"].id


def test_le_code_est_unique_par_usine_mais_pas_entre_usines(
    db, locations, site, location_type, admin
):
    from app.schemas.site import SiteCreate
    from app.services.site_service import SiteService

    service = LocationService(db)
    autre_site = SiteService(db).create(
        SiteCreate(code="USN-02", name="Autre usine"), actor=admin
    )

    with pytest.raises(ConflictError):
        service.create(
            LocationCreate(
                site_id=site.id,
                location_type_id=location_type.id,
                code="ZON-01",
                name="Doublon",
            )
        )

    # Le même code dans une autre usine est accepté.
    cree = service.create(
        LocationCreate(
            site_id=autre_site.id,
            location_type_id=location_type.id,
            code="ZON-01",
            name="Zone homonyme",
        )
    )
    assert cree.code == "ZON-01"


def test_un_parent_doit_appartenir_a_la_meme_usine(db, locations, site, location_type, admin):
    from app.schemas.site import SiteCreate
    from app.services.site_service import SiteService

    autre_site = SiteService(db).create(
        SiteCreate(code="USN-03", name="Autre usine"), actor=admin
    )
    emplacement_etranger = LocationService(db).create(
        LocationCreate(
            site_id=autre_site.id,
            location_type_id=location_type.id,
            code="BAT-90",
            name="Bâtiment étranger",
        )
    )

    with pytest.raises(ValidationError):
        LocationService(db).create(
            LocationCreate(
                site_id=site.id,
                parent_id=emplacement_etranger.id,
                location_type_id=location_type.id,
                code="ATL-90",
                name="Enfant invalide",
            )
        )


def test_un_cycle_est_refuse(db, locations):
    service = LocationService(db)

    with pytest.raises(ValidationError):
        service.move(locations["batiment"], locations["zone"].id)


def test_un_emplacement_ne_peut_pas_etre_son_propre_parent(db, locations):
    service = LocationService(db)

    with pytest.raises(ValidationError):
        service.move(locations["atelier"], locations["atelier"].id)


def test_suppression_refusee_si_des_equipements_sont_implantes(db, locations, equipment):
    service = LocationService(db)

    with pytest.raises(ConflictError):
        service.delete(service.get(locations["zone"].id))


def test_suppression_refusee_si_des_sous_emplacements_existent(db, locations):
    service = LocationService(db)

    with pytest.raises(ConflictError):
        service.delete(service.get(locations["batiment"].id))


def test_arbre_imbrique(db, locations):
    service = LocationService(db)

    arbre = service.tree(locations["batiment"].site_id)

    codes = [node["code"] for node in arbre]
    assert "BAT-01" in codes
    assert "ATL-99" in codes

    batiment = next(node for node in arbre if node["code"] == "BAT-01")
    enfants = [node["code"] for node in batiment["children"]]
    assert enfants == ["ATL-01"]

    atelier = batiment["children"][0]
    petits = [node["code"] for node in atelier["children"]]
    assert petits == ["ZON-01"]
    assert atelier["children"][0]["equipment_count"] == 0


def test_compteur_equipements_par_emplacement(db, locations, equipment):
    service = LocationService(db)

    zone = service.enrich(service.get(locations["zone"].id))
    atelier = service.enrich(service.get(locations["atelier"].id))

    assert zone.equipment_count == 1
    assert atelier.equipment_count == 0


def test_deplacement_d_un_emplacement_mise_a_jour_le_chemin(db, locations):
    service = LocationService(db)

    service.move(locations["zone"], locations["nord"].id)

    zone = service.enrich(service.get(locations["zone"].id))
    assert zone.path == "ATL-99 / ZON-01"
