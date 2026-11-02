"""Tests des pièces de rechange compatibles et de la substitution à l'usage."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.errors import ConflictError, ValidationError
from app.models.spare_part import StockMovement
from app.models.user import User
from app.schemas.intervention import (
    InterventionPartCreate,
    InterventionPartUse,
    InterventionRequestCreate,
    InterventionStart,
)
from app.schemas.spare_part import SparePartCreate
from app.schemas.user import UserCreate
from app.services.intervention_service import InterventionService
from app.services.spare_part_service import SparePartService
from app.services.user_service import UserService


def _user(db, username: str, role: str) -> User:
    return UserService(db).create(
        UserCreate(
            username=username,
            display_name=username.title(),
            role=role,
            password="secret",
        )
    )


def _part(db, code: str, *, unit: str = "pièce", cost: str = "20", stock: str = "10", active: bool = True):
    return SparePartService(db).create(
        SparePartCreate(
            code=code,
            name=f"Pièce {code}",
            unit=unit,
            quantity=Decimal(stock),
            min_quantity=Decimal("1"),
            unit_cost=Decimal(cost),
            is_active=active,
        )
    )


@pytest.fixture()
def demandeur(db) -> User:
    return _user(db, "demandeur", "lecture")


@pytest.fixture()
def technicien(db) -> User:
    return _user(db, "technicien", "technicien")


@pytest.fixture()
def responsable(db) -> User:
    return _user(db, "responsable", "responsable")


@pytest.fixture()
def piece_origine(db, admin):
    # Pièce demandée : 20 €, stock largement suffisant.
    return _part(db, "PR-ORIG", cost="20", stock="10")


@pytest.fixture()
def piece_compatible(db, admin):
    # Pièce moins chère : 12 €.
    return _part(db, "PR-COMPAT", cost="12", stock="8")


@pytest.fixture()
def piece_chere(db, admin):
    # Pièce plus chère : 30 €.
    return _part(db, "PR-CHERE", cost="30", stock="8")


def _intervention_prete(db, equipment, demandeur, technicien, responsable, piece):
    service = InterventionService(db)
    intervention = service.create_request(
        InterventionRequestCreate(
            equipment_id=equipment.id,
            description="Jeu excessif au niveau du roulement.",
            priority="high",
        ),
        actor=demandeur,
    )
    service.assign(intervention, technicien.id, actor=responsable)
    service.start(intervention, InterventionStart(), actor=technicien)
    item = service.request_part(
        intervention,
        InterventionPartCreate(spare_part_id=piece.id, quantity=Decimal("2")),
        actor=technicien,
    )
    return service, service.get(intervention.id), item


# --------------------------------------------------------------- relations
def test_relation_orientee_et_proprietes_de_prix(db, piece_origine, piece_compatible):
    service = SparePartService(db)
    # La pièce compatible (12 €) remplace la pièce d'origine (20 €).
    link = service.add_interchange(piece_compatible, piece_origine.id)

    assert link.part_code == "PR-COMPAT"
    assert link.replaces_code == "PR-ORIG"
    assert link.is_cheaper is True
    assert link.price_difference == Decimal("-8.00")

    assert [item.id for item in service.interchanges(piece_compatible)] == [link.id]
    assert [item.id for item in service.replacements(piece_origine)] == [link.id]


def test_l_inverse_n_est_pas_cree_automatiquement(db, piece_origine, piece_compatible):
    service = SparePartService(db)
    service.add_interchange(piece_compatible, piece_origine.id)

    assert service.interchanges(piece_origine) == []
    assert service.replacements(piece_compatible) == []
    assert service.repository.find_interchange(piece_origine.id, piece_compatible.id) is None


def test_une_piece_plus_chere_peut_etre_declaree_avec_avertissement(
    db, piece_origine, piece_chere
):
    service = SparePartService(db)
    link = service.add_interchange(piece_chere, piece_origine.id)

    # La règle de prix est un avertissement : la relation est acceptée.
    assert link.is_cheaper is False
    assert link.price_difference == Decimal("10.00")


def test_auto_substitution_refusee(db, piece_origine):
    with pytest.raises(ValidationError):
        SparePartService(db).add_interchange(piece_origine, piece_origine.id)


def test_unites_differentes_refusees(db, piece_origine):
    litre = _part(db, "PR-LITRE", unit="litre", cost="5")

    with pytest.raises(ValidationError):
        SparePartService(db).add_interchange(litre, piece_origine.id)


def test_doublon_refuse(db, piece_origine, piece_compatible):
    service = SparePartService(db)
    service.add_interchange(piece_compatible, piece_origine.id)

    with pytest.raises(ConflictError):
        service.add_interchange(piece_compatible, piece_origine.id)


def test_suppression_de_la_compatibilite(db, piece_origine, piece_compatible):
    service = SparePartService(db)
    link = service.add_interchange(piece_compatible, piece_origine.id)

    service.remove_interchange(piece_compatible, link.id)

    assert service.interchanges(piece_compatible) == []
    assert service.replacements(piece_origine) == []


def test_candidates_ignorent_les_pieces_inactives(db, piece_origine, piece_compatible):
    service = SparePartService(db)
    inactive = _part(db, "PR-INACTIF", cost="5", active=False)
    service.add_interchange(piece_compatible, piece_origine.id)
    service.add_interchange(inactive, piece_origine.id)

    candidates = service.replacement_candidates(piece_origine)
    assert [item.code for item in candidates] == ["PR-COMPAT"]


# --------------------------------------------------------------- consommation
def test_le_technicien_choisit_la_piece_moins_chere_meme_si_le_stock_suffit(
    db,
    equipment,
    demandeur,
    technicien,
    responsable,
    piece_origine,
    piece_compatible,
):
    service = InterventionService(db)
    SparePartService(db).add_interchange(piece_compatible, piece_origine.id)
    _, intervention, item = _intervention_prete(
        db, equipment, demandeur, technicien, responsable, piece_origine
    )

    utilisation = service.use_part(
        intervention,
        item,
        InterventionPartUse(
            quantity=Decimal("2"), replacement_part_id=piece_compatible.id
        ),
        actor=technicien,
    )

    assert utilisation.status == "used"
    assert utilisation.used_spare_part_id == piece_compatible.id
    assert utilisation.is_substituted is True
    assert utilisation.used_part_code == "PR-COMPAT"
    assert SparePartService(db).get(piece_origine.id).quantity == Decimal("10.00")
    assert SparePartService(db).get(piece_compatible.id).quantity == Decimal("6.00")

    movement = db.query(StockMovement).order_by(StockMovement.id.desc()).first()
    assert movement.spare_part_id == piece_compatible.id
    assert "remplacée par PR-COMPAT" in (movement.notes or "")


def test_substitution_refusee_si_la_piece_n_est_pas_compatible(
    db,
    equipment,
    demandeur,
    technicien,
    responsable,
    piece_origine,
    piece_chere,
):
    service = InterventionService(db)
    _, intervention, item = _intervention_prete(
        db, equipment, demandeur, technicien, responsable, piece_origine
    )

    with pytest.raises(ValidationError):
        service.use_part(
            intervention,
            item,
            InterventionPartUse(
                quantity=Decimal("1"), replacement_part_id=piece_chere.id
            ),
            actor=technicien,
        )


def test_stock_insuffisant_sur_la_piece_compatible(
    db,
    equipment,
    demandeur,
    technicien,
    responsable,
    piece_origine,
):
    service = InterventionService(db)
    candidate = _part(db, "PR-VIDE", cost="5", stock="1")
    SparePartService(db).add_interchange(candidate, piece_origine.id)
    _, intervention, item = _intervention_prete(
        db, equipment, demandeur, technicien, responsable, piece_origine
    )

    with pytest.raises(ConflictError):
        service.use_part(
            intervention,
            item,
            InterventionPartUse(
                quantity=Decimal("2"), replacement_part_id=candidate.id
            ),
            actor=technicien,
        )


def test_consommation_normale_renseigne_la_piece_utilisee(
    db, equipment, demandeur, technicien, responsable, piece_origine
):
    service = InterventionService(db)
    _, intervention, item = _intervention_prete(
        db, equipment, demandeur, technicien, responsable, piece_origine
    )

    utilisation = service.use_part(
        intervention,
        item,
        InterventionPartUse(quantity=Decimal("1")),
        actor=technicien,
    )

    assert utilisation.used_spare_part_id == piece_origine.id
    assert utilisation.is_substituted is False


# --------------------------------------------------------------------- API
def test_api_compatibilites_et_candidats(
    client, db, piece_origine, piece_compatible
):
    creation = client.post(
        f"/api/spare-parts/{piece_compatible.id}/interchanges",
        json={"replaces_id": piece_origine.id, "note": "Même dimensions"},
    )
    assert creation.status_code == 201, creation.text
    payload = creation.json()
    assert payload["part_code"] == "PR-COMPAT"
    assert payload["replaces_code"] == "PR-ORIG"
    assert payload["is_cheaper"] is True

    detail = client.get(f"/api/spare-parts/{piece_origine.id}/interchanges")
    assert detail.status_code == 200
    assert len(detail.json()["can_be_replaced_by"]) == 1

    candidates = client.get(
        f"/api/spare-parts/{piece_origine.id}/replacement-candidates"
    )
    assert candidates.status_code == 200
    assert [item["code"] for item in candidates.json()] == ["PR-COMPAT"]

    suppression = client.delete(
        f"/api/spare-parts/{piece_compatible.id}/interchanges/{payload['id']}"
    )
    assert suppression.status_code == 204


def test_api_consommation_avec_substitution(
    client,
    db,
    equipment,
    demandeur,
    technicien,
    responsable,
    piece_origine,
    piece_compatible,
):
    SparePartService(db).add_interchange(piece_compatible, piece_origine.id)
    _, intervention, item = _intervention_prete(
        db, equipment, demandeur, technicien, responsable, piece_origine
    )

    response = client.post(
        f"/api/interventions/{intervention.id}/parts/{item.id}/use",
        json={"quantity": 2, "replacement_part_id": piece_compatible.id},
        headers={"X-GMAO-User": technicien.username},
    )
    assert response.status_code == 200, response.text
    assert response.json()["used_spare_part_id"] == piece_compatible.id
    assert response.json()["is_substituted"] is True


# --------------------------------------------------------------------- web
def test_page_piece_affiche_les_compatibilites_et_les_prix(
    client, db, piece_origine, piece_compatible
):
    SparePartService(db).add_interchange(piece_compatible, piece_origine.id)

    page = client.get(f"/spare-parts/{piece_origine.id}")
    assert page.status_code == 200
    assert "Pièces compatibles" in page.text
    assert "PR-COMPAT" in page.text
    assert "moins chère" in page.text


def test_page_intervention_affiche_les_choix_et_les_prix(
    client,
    db,
    equipment,
    demandeur,
    technicien,
    responsable,
    piece_origine,
    piece_compatible,
):
    SparePartService(db).add_interchange(piece_compatible, piece_origine.id)
    _, intervention, _ = _intervention_prete(
        db, equipment, demandeur, technicien, responsable, piece_origine
    )
    client.post("/user/switch", data={"username": technicien.username})

    page = client.get(f"/interventions/{intervention.id}")
    assert page.status_code == 200
    assert 'name="replacement_part_id"' in page.text
    assert "PR-ORIG" in page.text
    assert "PR-COMPAT" in page.text
    assert "moins chère" in page.text
    assert "12,00 €" in page.text
