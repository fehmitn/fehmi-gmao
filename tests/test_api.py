"""Tests de l'API REST et des pages web."""

from __future__ import annotations

from datetime import timedelta

from app.services.clock import today
from tests.conftest import REFERENCE_DATE


def test_document_de_l_api(client):
    reponse = client.get("/docs")

    assert reponse.status_code == 200


def test_tableau_de_bord_api(client, site, locations, equipment):
    reponse = client.get("/api/stats/dashboard")

    assert reponse.status_code == 200
    donnees = reponse.json()
    assert donnees["site_count"] == 1
    assert donnees["location_count"] == 4
    assert donnees["equipment_count"] == 1
    assert donnees["sites"][0]["code"] == "USN-01"


def test_liste_des_equipements_avec_recherche(client, equipment):
    reponse = client.get("/api/equipments", params={"search": "PMP"})

    assert reponse.status_code == 200
    assert [item["code"] for item in reponse.json()] == ["PMP-001"]


def test_creation_equipement_avec_code_duplique(client, equipment, locations):
    reponse = client.post(
        "/api/equipments",
        json={
            "code": "PMP-001",
            "name": "Doublon",
            "location_id": locations["zone"].id,
        },
    )

    assert reponse.status_code == 409


def test_emplacement_introuvable(client):
    reponse = client.get("/api/locations/999999")

    assert reponse.status_code == 404


def test_pages_web_principales(client, site, locations, equipment):
    for chemin in (
        "/",
        "/sites",
        f"/sites/{site.id}",
        "/locations",
        "/equipment-types",
        "/equipments",
        "/equipments/new",
        f"/equipments/{equipment.id}",
        "/audit",
    ):
        reponse = client.get(chemin)
        assert reponse.status_code == 200, chemin


def test_creation_d_un_equipement_par_le_formulaire_web(client, locations, equipment_type):
    reponse = client.post(
        "/equipments",
        data={
            "code": "PMP-WEB",
            "name": "Pompe saisie depuis le web",
            "equipment_type_id": str(equipment_type.id),
            "location_id": str(locations["zone"].id),
            "status": "operational",
            "criticality": "B",
            "effective_from": REFERENCE_DATE.isoformat(),
        },
        follow_redirects=False,
    )

    assert reponse.status_code == 303
    assert "/equipments/" in reponse.headers["location"]


def test_le_formulaire_web_refuse_une_date_passee_sans_motif(client, locations):
    reponse = client.post(
        "/equipments",
        data={
            "code": "PMP-WEB2",
            "name": "Pompe antidatée",
            "location_id": str(locations["zone"].id),
            "status": "operational",
            "effective_from": (REFERENCE_DATE - timedelta(days=10)).isoformat(),
        },
        follow_redirects=False,
    )

    assert reponse.status_code == 303
    assert "err=" in reponse.headers["location"]


def test_changement_d_utilisateur_pose_le_cookie(client, db, admin):
    reponse = client.post(
        "/user/switch",
        data={"username": admin.username},
        follow_redirects=False,
    )

    assert reponse.status_code == 303
    assert "gmao_current_user" in reponse.cookies


def test_arbre_des_emplacements_est_serie_en_html(client, locations):
    reponse = client.get("/locations")

    assert "ZON-01" in reponse.text
    assert "ATL-01" in reponse.text


def test_detail_emplacement_en_fragment(client, locations):
    reponse = client.get(f"/locations/{locations['zone'].id}")

    assert reponse.status_code == 200
    assert "ZON-01" in reponse.text
