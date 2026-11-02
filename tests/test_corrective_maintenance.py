"""Tests de la maintenance corrective.

Une demande d'intervention peut être créée par tout utilisateur connecté ; le
responsable l'affecte à un technicien qui saisit ses horaires et consomme des
pièces détachées. Les pièces suivent un cycle demande -> utilisation, la
sortie de stock n'étant créée qu'à l'utilisation.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from app.errors import (
    AuthenticationRequiredError,
    ConflictError,
    PermissionDeniedError,
    ValidationError,
)
from app.models.enums import StockMovementType, WorkOrderStatus
from app.models.spare_part import StockMovement
from app.models.user import User
from app.models.work_order import WorkOrder
from app.schemas.intervention import (
    InterventionCancel,
    InterventionFinish,
    InterventionPartCreate,
    InterventionPartUse,
    InterventionRequestCreate,
    InterventionStart,
)
from app.schemas.spare_part import SparePartCreate
from app.schemas.user import UserCreate
from app.schemas.work_order import WorkOrderAssignment, WorkOrderStatusUpdate
from app.services.intervention_service import InterventionService
from app.services.spare_part_service import SparePartService
from app.services.user_service import UserService
from app.services.work_order_service import WorkOrderService


def _user(db, username: str, role: str) -> User:
    return UserService(db).create(
        UserCreate(
            username=username,
            display_name=username.title(),
            role=role,
            password="secret",
        )
    )


@pytest.fixture()
def demandeur(db) -> User:
    return _user(db, "demandeur", "lecture")


@pytest.fixture()
def technicien(db) -> User:
    return _user(db, "technicien", "technicien")


@pytest.fixture()
def autre_technicien(db) -> User:
    return _user(db, "autre-tech", "technicien")


@pytest.fixture()
def responsable(db) -> User:
    return _user(db, "responsable", "responsable")


@pytest.fixture()
def piece(db, admin) -> object:
    return SparePartService(db).create(
        SparePartCreate(
            code="PR-ROUL-6205",
            name="Roulement 6205 2RS",
            unit="pièce",
            quantity=Decimal("10"),
            min_quantity=Decimal("2"),
        ),
        actor=admin,
    )


def _demande(db, equipment, demandeur, **overrides) -> WorkOrder:
    payload = {
        "equipment_id": equipment.id,
        "description": "Fuite au niveau du joint de la pompe.",
        "priority": "high",
    }
    payload.update(overrides)
    return InterventionService(db).create_request(
        InterventionRequestCreate(**payload), actor=demandeur
    )


# --------------------------------------------------------------- création
def test_tout_utilisateur_connecte_peut_creer_une_demande(db, equipment, demandeur):
    intervention = _demande(db, equipment, demandeur)

    assert intervention.is_corrective is True
    assert intervention.code.startswith("OT-2026-")
    assert intervention.status == WorkOrderStatus.OPEN.value
    assert intervention.created_by_id == demandeur.id
    assert intervention.assigned_to_id is None
    assert intervention.kind_label == "Corrective"


def test_creation_refusee_sans_utilisateur_connecte(db, equipment):
    with pytest.raises(AuthenticationRequiredError):
        _demande(db, equipment, None)


def test_creation_refusee_pour_un_equipement_inconnu(db, demandeur):
    with pytest.raises(Exception) as excinfo:
        InterventionService(db).create_request(
            InterventionRequestCreate(
                equipment_id=99999, description="Panne inconnue"
            ),
            actor=demandeur,
        )
    assert getattr(excinfo.value, "status_code", None) == 404


def test_les_ot_preventifs_et_correctifs_sont_separes(db, equipment, admin, demandeur):
    preventive = WorkOrder(
        code="OT-2026-9001",
        equipment_id=equipment.id,
        status=WorkOrderStatus.OPEN.value,
        priority="normal",
        description="Graissage périodique",
        is_corrective=False,
    )
    db.add(preventive)
    db.commit()

    intervention = _demande(db, equipment, demandeur)

    correctives = WorkOrderService(db).list(corrective=True)
    preventives = WorkOrderService(db).list(corrective=False)
    assert [item.id for item in correctives] == [intervention.id]
    assert [item.id for item in preventives] == [preventive.id]


def test_les_services_ot_preventifs_refusent_une_intervention_corrective(
    db, equipment, demandeur, technicien, responsable
):
    intervention = _demande(db, equipment, demandeur)
    service = WorkOrderService(db)

    with pytest.raises(ValidationError):
        service.take(intervention, technicien)
    with pytest.raises(ValidationError):
        service.assign(
            intervention, WorkOrderAssignment(assigned_to_id=technicien.id), actor=responsable
        )
    with pytest.raises(ValidationError):
        service.update_status(
            intervention,
            WorkOrderStatusUpdate(status=WorkOrderStatus.DONE),
            actor=responsable,
        )


# --------------------------------------------------------------- affectation
def test_affectation_reservee_au_responsable(db, equipment, demandeur, technicien, responsable):
    intervention = _demande(db, equipment, demandeur)
    service = InterventionService(db)

    with pytest.raises(PermissionDeniedError):
        service.assign(intervention, technicien.id, actor=technicien)

    affectee = service.assign(intervention, technicien.id, actor=responsable)
    assert affectee.status == WorkOrderStatus.ASSIGNED.value
    assert affectee.assigned_to_id == technicien.id
    assert affectee.assigned_to_name == technicien.display_name


def test_affectation_refusee_a_un_utilisateur_en_lecture(
    db, equipment, demandeur, responsable
):
    intervention = _demande(db, equipment, demandeur)

    with pytest.raises(ValidationError):
        InterventionService(db).assign(intervention, demandeur.id, actor=responsable)


# --------------------------------------------------------------- exécution
def test_le_technicien_saisit_le_debut_et_la_fin(db, equipment, demandeur, technicien, responsable):
    intervention = _demande(db, equipment, demandeur)
    service = InterventionService(db)
    service.assign(intervention, technicien.id, actor=responsable)

    demarree = service.start(
        intervention,
        InterventionStart(started_at=datetime(2026, 6, 15, 8, 30)),
        actor=technicien,
    )
    assert demarree.status == WorkOrderStatus.IN_PROGRESS.value
    assert demarree.intervention_started_at == datetime(2026, 6, 15, 8, 30)
    assert demarree.started_at.isoformat() == "2026-06-15"

    terminee = service.finish(
        demarree,
        InterventionFinish(
            ended_at=datetime(2026, 6, 15, 10, 0),
            work_done="Remplacement du joint et essai d'étanchéité.",
        ),
        actor=technicien,
    )
    assert terminee.status == WorkOrderStatus.DONE.value
    assert terminee.intervention_duration_minutes == 90
    assert terminee.intervention_duration_label == "1 h 30 min"
    assert terminee.work_done.startswith("Remplacement")
    assert terminee.completed_at.isoformat() == "2026-06-15"


def test_un_technicien_non_affecte_ne_peut_pas_intervenir(
    db, equipment, demandeur, technicien, autre_technicien, responsable
):
    intervention = _demande(db, equipment, demandeur)
    service = InterventionService(db)
    service.assign(intervention, technicien.id, actor=responsable)

    with pytest.raises(PermissionDeniedError):
        service.start(intervention, InterventionStart(), actor=autre_technicien)


def test_la_fin_ne_peut_pas_preceder_le_debut(db, equipment, demandeur, technicien, responsable):
    intervention = _demande(db, equipment, demandeur)
    service = InterventionService(db)
    service.assign(intervention, technicien.id, actor=responsable)
    service.start(
        intervention,
        InterventionStart(started_at=datetime(2026, 6, 15, 10, 0)),
        actor=technicien,
    )

    with pytest.raises(ValidationError):
        service.finish(
            intervention,
            InterventionFinish(
                ended_at=datetime(2026, 6, 15, 9, 0), work_done="Compte rendu"
            ),
            actor=technicien,
        )


def test_le_compte_rendu_est_obligatoire(db, equipment, demandeur, technicien, responsable):
    intervention = _demande(db, equipment, demandeur)
    service = InterventionService(db)
    service.assign(intervention, technicien.id, actor=responsable)
    service.start(intervention, InterventionStart(), actor=technicien)

    with pytest.raises(ValidationError):
        service.finish(
            intervention,
            InterventionFinish(work_done="   "),
            actor=technicien,
        )


# --------------------------------------------------------------- pièces
def test_cycle_demande_puis_utilisation_d_une_piece(
    db, equipment, demandeur, technicien, responsable, piece, admin
):
    intervention = _demande(db, equipment, demandeur)
    service = InterventionService(db)
    service.assign(intervention, technicien.id, actor=responsable)

    demande = service.request_part(
        intervention,
        InterventionPartCreate(spare_part_id=piece.id, quantity=Decimal("2")),
        actor=technicien,
    )
    assert demande.status == "requested"
    assert demande.used_quantity is None
    assert service.get(intervention.id).status == WorkOrderStatus.ASSIGNED.value

    # La consommation est interdite tant que l'intervention n'est pas démarrée.
    with pytest.raises(ConflictError):
        service.use_part(
            intervention,
            demande,
            InterventionPartUse(quantity=Decimal("2")),
            actor=technicien,
        )

    service.start(intervention, InterventionStart(), actor=technicien)
    utilisation = service.use_part(
        service.get(intervention.id),
        demande,
        InterventionPartUse(quantity=Decimal("2")),
        actor=technicien,
    )

    assert utilisation.status == "used"
    assert utilisation.used_quantity == Decimal("2.00")
    assert utilisation.used_by_id == technicien.id
    assert SparePartService(db).get(piece.id).quantity == Decimal("8.00")

    mouvement = db.query(StockMovement).order_by(StockMovement.id.desc()).first()
    assert mouvement.movement_type == StockMovementType.EXIT.value
    assert mouvement.work_order_id == intervention.id
    assert mouvement.quantity == Decimal("2.00")
    assert intervention.code in (mouvement.reference or "")
    assert mouvement.actor_id == technicien.id


def test_une_piece_ne_peut_pas_etre_demandee_deux_fois_en_attente(
    db, equipment, demandeur, technicien, responsable, piece
):
    intervention = _demande(db, equipment, demandeur)
    service = InterventionService(db)
    service.assign(intervention, technicien.id, actor=responsable)
    payload = InterventionPartCreate(spare_part_id=piece.id, quantity=Decimal("1"))
    service.request_part(intervention, payload, actor=technicien)

    with pytest.raises(ConflictError):
        service.request_part(intervention, payload, actor=technicien)


def test_stock_insuffisant_refuse_la_consommation(
    db, equipment, demandeur, technicien, responsable, piece
):
    intervention = _demande(db, equipment, demandeur)
    service = InterventionService(db)
    service.assign(intervention, technicien.id, actor=responsable)
    demande = service.request_part(
        intervention,
        InterventionPartCreate(spare_part_id=piece.id, quantity=Decimal("20")),
        actor=technicien,
    )
    service.start(intervention, InterventionStart(), actor=technicien)

    with pytest.raises(ConflictError):
        service.use_part(
            service.get(intervention.id),
            demande,
            InterventionPartUse(quantity=Decimal("20")),
            actor=technicien,
        )
    assert SparePartService(db).get(piece.id).quantity == Decimal("10.00")


def test_la_quantite_utilisee_ne_depasse_pas_la_demande(
    db, equipment, demandeur, technicien, responsable, piece
):
    intervention = _demande(db, equipment, demandeur)
    service = InterventionService(db)
    service.assign(intervention, technicien.id, actor=responsable)
    demande = service.request_part(
        intervention,
        InterventionPartCreate(spare_part_id=piece.id, quantity=Decimal("2")),
        actor=technicien,
    )
    service.start(intervention, InterventionStart(), actor=technicien)

    with pytest.raises(ValidationError):
        service.use_part(
            service.get(intervention.id),
            demande,
            InterventionPartUse(quantity=Decimal("3")),
            actor=technicien,
        )


# --------------------------------------------------------------- annulation
def test_le_demandeur_peut_annuler_et_les_demandes_de_pieces_sont_closes(
    db, equipment, demandeur, technicien, responsable, piece
):
    intervention = _demande(db, equipment, demandeur)
    service = InterventionService(db)
    service.assign(intervention, technicien.id, actor=responsable)
    demande = service.request_part(
        intervention,
        InterventionPartCreate(spare_part_id=piece.id, quantity=Decimal("1")),
        actor=technicien,
    )

    annulee = service.cancel(
        intervention,
        InterventionCancel(reason="Panne résolue par le redémarrage."),
        actor=demandeur,
    )
    assert annulee.status == WorkOrderStatus.CANCELLED.value
    assert service.get_part(annulee, demande.id).status == "cancelled"


def test_annulation_impossible_apres_consommation_de_piece(
    db, equipment, demandeur, technicien, responsable, piece
):
    intervention = _demande(db, equipment, demandeur)
    service = InterventionService(db)
    service.assign(intervention, technicien.id, actor=responsable)
    demande = service.request_part(
        intervention,
        InterventionPartCreate(spare_part_id=piece.id, quantity=Decimal("1")),
        actor=technicien,
    )
    service.start(intervention, InterventionStart(), actor=technicien)
    service.use_part(
        service.get(intervention.id),
        demande,
        InterventionPartUse(quantity=Decimal("1")),
        actor=technicien,
    )

    with pytest.raises(ConflictError):
        service.cancel(
            service.get(intervention.id), InterventionCancel(), actor=responsable
        )


# --------------------------------------------------------------- API / web
def test_api_interventions_avec_entete_utilisateur(
    client, db, equipment, demandeur, technicien, responsable
):
    creation = client.post(
        "/api/interventions",
        json={
            "equipment_id": equipment.id,
            "description": "Arrêt inopiné de la pompe.",
            "priority": "urgent",
        },
        headers={"X-GMAO-User": demandeur.username},
    )
    assert creation.status_code == 201, creation.text
    intervention = creation.json()
    assert intervention["is_corrective"] is True
    assert intervention["status"] == "open"
    assert intervention["created_by_name"] == demandeur.display_name

    # Sans en-tête utilisateur, la création est refusée.
    anonyme = client.post(
        "/api/interventions",
        json={"equipment_id": equipment.id, "description": "Tentative anonyme."},
    )
    assert anonyme.status_code == 401

    # Un technicien ne peut pas affecter.
    refus = client.put(
        f"/api/interventions/{intervention['id']}/assignment",
        json={"assigned_to_id": technicien.id},
        headers={"X-GMAO-User": technicien.username},
    )
    assert refus.status_code == 403

    affectation = client.put(
        f"/api/interventions/{intervention['id']}/assignment",
        json={"assigned_to_id": technicien.id},
        headers={"X-GMAO-User": responsable.username},
    )
    assert affectation.status_code == 200, affectation.text
    assert affectation.json()["assigned_to_id"] == technicien.id

    demarrage = client.post(
        f"/api/interventions/{intervention['id']}/start",
        json={"started_at": "2026-06-15T08:00:00"},
        headers={"X-GMAO-User": technicien.username},
    )
    assert demarrage.status_code == 200, demarrage.text
    assert demarrage.json()["status"] == "in_progress"

    fin = client.post(
        f"/api/interventions/{intervention['id']}/finish",
        json={
            "ended_at": "2026-06-15T09:15:00",
            "work_done": "Réalignement de l'accouplement.",
        },
        headers={"X-GMAO-User": technicien.username},
    )
    assert fin.status_code == 200, fin.text
    assert fin.json()["status"] == "done"
    assert fin.json()["intervention_duration_minutes"] == 75


def test_pages_web_des_interventions(client, db, equipment, demandeur):
    client.post("/user/switch", data={"username": demandeur.username})

    liste = client.get("/interventions")
    assert liste.status_code == 200
    assert "Maintenance corrective" in liste.text
    assert "Nouvelle demande" in liste.text

    formulaire = client.get("/interventions/new")
    assert formulaire.status_code == 200
    assert "Envoyer la demande" in formulaire.text
    assert equipment.code in formulaire.text

    creation = client.post(
        "/interventions",
        data={
            "equipment_id": str(equipment.id),
            "description": "Bruit anormal au niveau du palier.",
            "priority": "normal",
        },
        follow_redirects=False,
    )
    assert creation.status_code == 303
    fiche_url = creation.headers["location"].split("?")[0]
    fiche = client.get(fiche_url)
    assert fiche.status_code == 200
    assert "Bruit anormal au niveau du palier." in fiche.text
    assert "Pièces de rechange de l'intervention" in fiche.text
