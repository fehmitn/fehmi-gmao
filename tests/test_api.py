"""Tests de l'API REST et des pages web."""

from __future__ import annotations

from datetime import date, timedelta

from app.models.enums import (
    MaintenanceAnchor,
    MaintenanceIntervalUnit,
    MaintenanceType,
)
from app.schemas.equipment import EquipmentUpdate
from app.schemas.maintenance_supplier import MaintenanceSupplierCreate
from app.schemas.periodic_maintenance import PeriodicMaintenanceCreate
from app.services.clock import today
from app.services.equipment_service import EquipmentService
from app.services.maintenance_supplier_service import MaintenanceSupplierService
from app.services.periodic_maintenance_service import PeriodicMaintenanceService
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


def test_fiche_d_un_equipement_non_implante_propose_l_implantation(
    client, equipement_non_implante
):
    """L'équipement hérité de la v0.1 peut être implanté depuis sa fiche."""
    reponse = client.get(f"/equipments/{equipement_non_implante.id}")

    assert reponse.status_code == 200
    assert "Implanter l'équipement" in reponse.text
    assert "Enregistrer l'implantation" in reponse.text


def test_implantation_de_l_equipement_non_implante_par_le_web(
    client, equipement_non_implante, locations
):
    reponse = client.post(
        f"/equipments/{equipement_non_implante.id}/placements",
        data={
            "location_id": str(locations["zone"].id),
            "effective_from": REFERENCE_DATE.isoformat(),
            "reason": "Emplacement réel retrouvé",
        },
        follow_redirects=False,
    )

    assert reponse.status_code == 303
    assert "err=" not in reponse.headers["location"]


# ------------------------------------------------ maintenance périodique (API)
def test_api_fournisseur_de_maintenance_crud(client):
    reponse = client.post(
        "/api/maintenance-suppliers",
        json={"code": "SUP-API", "name": "Fournisseur API", "specialty": "Hydraulique"},
    )
    assert reponse.status_code == 201
    fournisseur = reponse.json()
    assert fournisseur["periodic_maintenance_count"] == 0

    reponse = client.get("/api/maintenance-suppliers")
    assert reponse.status_code == 200
    assert [item["code"] for item in reponse.json()] == ["SUP-API"]

    reponse = client.put(
        f"/api/maintenance-suppliers/{fournisseur['id']}",
        json={"name": "Fournisseur renommé"},
    )
    assert reponse.status_code == 200
    assert reponse.json()["name"] == "Fournisseur renommé"

    reponse = client.delete(f"/api/maintenance-suppliers/{fournisseur['id']}")
    assert reponse.status_code == 204
    assert client.get("/api/maintenance-suppliers").json() == []


def test_api_maintenance_execution_et_echeancier(client, equipment, equipment_type):
    client.put(
        f"/api/equipments/{equipment.id}",
        json={"commissioning_date": "2026-01-31"},
    )
    fournisseur = client.post(
        "/api/maintenance-suppliers",
        json={"code": "SUP-API", "name": "Mécanique API"},
    ).json()

    reponse = client.post(
        f"/api/equipment-types/{equipment_type.id}/periodic-maintenances",
        json={
            "code": "GRAISSAGE",
            "label": "Graissage des paliers",
            "interval_value": 1,
            "interval_unit": "months",
            "maintenance_type": "preventive_systematic",
            "anchor": "commissioning",
            "supplier_id": fournisseur["id"],
            "tolerance_days": 0,
        },
    )
    assert reponse.status_code == 201, reponse.text
    regle = reponse.json()
    assert regle["equipment_type_code"] == "PMP-CF"
    assert regle["supplier_name"] == "Mécanique API"
    assert regle["periodicity_label"] == "chaque mois"
    assert regle["maintenance_type_label"] == "Préventive systématique"

    echeancier = client.get(
        "/api/maintenance-schedule",
        params={"equipment_type_id": equipment_type.id},
    )
    assert echeancier.status_code == 200
    resume = echeancier.json()
    assert resume["total"] == 1
    assert resume["overdue_count"] == 1
    ligne = resume["rows"][0]
    assert ligne["status"] == "overdue"
    assert ligne["previous_due_date"] == "2026-05-31"
    assert ligne["days_remaining"] == -15

    reponse = client.post(
        f"/api/equipments/{equipment.id}/maintenance-executions",
        json={
            "periodic_maintenance_id": regle["id"],
            "performed_on": "2026-06-05",
            "notes": "Graissage réalisé",
        },
    )
    assert reponse.status_code == 201, reponse.text
    execution = reponse.json()
    assert execution["theoretical_due_date"] == "2026-05-31"
    assert execution["delay_days"] == 5
    assert execution["delay_label"] == "5 j de retard"
    assert execution["maintenance_code"] == "GRAISSAGE"
    assert execution["supplier_name"] == "Mécanique API"

    historique = client.get(
        f"/api/equipments/{equipment.id}/maintenance-executions"
    )
    assert historique.status_code == 200
    assert len(historique.json()) == 1

    echeancier = client.get(
        "/api/maintenance-schedule",
        params={"equipment_type_id": equipment_type.id},
    ).json()
    assert echeancier["overdue_count"] == 0
    assert echeancier["rows"][0]["status"] == "due_soon"
    assert echeancier["rows"][0]["due_date"] == "2026-06-30"

    # Une réalisation dans le futur est refusée.
    reponse = client.post(
        f"/api/equipments/{equipment.id}/maintenance-executions",
        json={
            "periodic_maintenance_id": regle["id"],
            "performed_on": "2026-06-16",
        },
    )
    assert reponse.status_code == 422

    # La règle ne peut plus être supprimée : l'historique doit être préservé.
    assert (
        client.delete(f"/api/periodic-maintenances/{regle['id']}").status_code == 409
    )
    # Le fournisseur non plus, tant qu'il est rattaché à une règle.
    assert (
        client.delete(f"/api/maintenance-suppliers/{fournisseur['id']}").status_code
        == 409
    )


def test_api_regle_date_fixe_sans_date_refusee(client, equipment_type):
    reponse = client.post(
        f"/api/equipment-types/{equipment_type.id}/periodic-maintenances",
        json={
            "code": "INSPECTION",
            "label": "Inspection réglementaire",
            "interval_value": 1,
            "interval_unit": "years",
            "maintenance_type": "regulatory",
            "anchor": "fixed_date",
        },
    )

    assert reponse.status_code == 422


def test_api_code_de_regle_duplique_dans_la_famille(client, equipment_type):
    payload = {
        "code": "GRAISSAGE",
        "label": "Graissage",
        "interval_value": 3,
        "interval_unit": "months",
    }
    assert (
        client.post(
            f"/api/equipment-types/{equipment_type.id}/periodic-maintenances",
            json=payload,
        ).status_code
        == 201
    )
    assert (
        client.post(
            f"/api/equipment-types/{equipment_type.id}/periodic-maintenances",
            json=payload,
        ).status_code
        == 409
    )


# --------------------------------------------- maintenance périodique (web)
def test_page_des_fournisseurs_et_creation_par_le_web(client):
    reponse = client.get("/maintenance-suppliers")
    assert reponse.status_code == 200
    assert "Nouveau fournisseur de maintenance" in reponse.text

    reponse = client.post(
        "/maintenance-suppliers",
        data={
            "code": "SUP-WEB",
            "name": "Fournisseur web",
            "specialty": "Électricité",
            "is_active": "1",
        },
    )
    assert reponse.status_code == 200
    assert "SUP-WEB" in reponse.text
    assert "Fournisseur web" in reponse.text


def test_pages_web_de_la_famille_et_de_l_echeancier(
    client, db, admin, equipment, equipment_type
):
    service = EquipmentService(db)
    equipment = service.update(
        service.get(equipment.id),
        EquipmentUpdate(commissioning_date=date(2026, 1, 31)),
        actor=admin,
    )
    fournisseur = MaintenanceSupplierService(db).create(
        MaintenanceSupplierCreate(code="SUP-WEB", name="Fournisseur web"),
        actor=admin,
    )
    regle = PeriodicMaintenanceService(db).create(
        equipment_type.id,
        PeriodicMaintenanceCreate(
            code="GRAISSAGE",
            label="Graissage des paliers",
            interval_value=3,
            interval_unit=MaintenanceIntervalUnit.MONTHS,
            maintenance_type=MaintenanceType.PREVENTIVE_SYSTEMATIC,
            anchor=MaintenanceAnchor.COMMISSIONING,
            supplier_id=fournisseur.id,
        ),
        actor=admin,
    )

    for chemin in (
        "/maintenance-suppliers",
        f"/maintenance-suppliers/{fournisseur.id}/edit",
        f"/equipment-types/{equipment_type.id}",
        f"/equipment-types/{equipment_type.id}/periodic-maintenances/{regle.id}/edit",
        "/maintenance-schedule",
        "/audit?action=execute",
    ):
        reponse = client.get(chemin)
        assert reponse.status_code == 200, chemin

    famille = client.get(f"/equipment-types/{equipment_type.id}")
    assert "GRAISSAGE" in famille.text
    assert "tous les 3 mois" in famille.text
    assert "SUP-WEB" in famille.text
    assert "Graissage des paliers" in famille.text

    detail = client.get(f"/equipments/{equipment.id}")
    assert "Maintenance périodique héritée" in detail.text
    assert "Graissage des paliers" in detail.text

    echeancier = client.get("/maintenance-schedule")
    assert "Projection théorique des échéances" in echeancier.text
    assert "Graissage des paliers" in echeancier.text
    assert "PMP-001" in echeancier.text


def test_creation_regle_et_realisation_par_le_web(
    client, db, admin, equipment, equipment_type
):
    service = EquipmentService(db)
    equipment = service.update(
        service.get(equipment.id),
        EquipmentUpdate(commissioning_date=date(2026, 1, 31)),
        actor=admin,
    )

    reponse = client.post(
        f"/equipment-types/{equipment_type.id}/periodic-maintenances",
        data={
            "code": "GRAISSAGE",
            "label": "Graissage des paliers",
            "interval_value": "1",
            "interval_unit": "months",
            "maintenance_type": "preventive_systematic",
            "anchor": "commissioning",
            "tolerance_days": "0",
            "sort_order": "0",
            "is_active": "1",
        },
        follow_redirects=False,
    )
    assert reponse.status_code == 303
    assert f"/equipment-types/{equipment_type.id}" in reponse.headers["location"]

    regle = PeriodicMaintenanceService(db).list_for_type(equipment_type.id)[0]

    reponse = client.post(
        f"/equipments/{equipment.id}/maintenance-executions",
        data={
            "periodic_maintenance_id": str(regle.id),
            "performed_on": "2026-06-05",
            "notes": "Graissage réalisé",
        },
        follow_redirects=False,
    )
    assert reponse.status_code == 303
    assert "msg=" in reponse.headers["location"]
    assert "err=" not in reponse.headers["location"]

    detail = client.get(f"/equipments/{equipment.id}")
    assert "5 j de retard" in detail.text
    assert "31/05/2026" in detail.text
