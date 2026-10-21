"""Règles de saisie rétroactive : le cœur pédagogique de l'application."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.errors import (
    BackdatingReasonRequired,
    DateBeforeOriginError,
    FutureDateNotAllowed,
)
from app.services.backdating import BackdatingPolicy
from tests.conftest import REFERENCE_DATE


def test_une_date_du_passe_est_autorisee_avec_motif():
    policy = BackdatingPolicy()
    cible = REFERENCE_DATE - timedelta(days=12)

    decision = policy.enforce(cible, "Reprise d'inventaire papier")

    assert decision.is_backdated is True
    assert decision.delay_days == 12
    assert decision.derogation_reason == "Reprise d'inventaire papier"


def test_une_date_du_passe_sans_motif_est_refusee():
    policy = BackdatingPolicy()
    cible = REFERENCE_DATE - timedelta(days=1)

    with pytest.raises(BackdatingReasonRequired) as exc:
        policy.enforce(cible, None)

    assert "motif de dérogation est obligatoire" in exc.value.message
    assert exc.value.status_code == 422


def test_un_motif_vide_est_equivalent_a_absence_de_motif():
    policy = BackdatingPolicy()
    cible = REFERENCE_DATE - timedelta(days=3)

    with pytest.raises(BackdatingReasonRequired):
        policy.enforce(cible, "   ")


def test_le_futur_reste_interdit_meme_avec_derogation():
    policy = BackdatingPolicy()
    cible = REFERENCE_DATE + timedelta(days=1)

    with pytest.raises(FutureDateNotAllowed) as exc:
        policy.enforce(cible, "Motif quelconque")

    assert "dans le futur" in exc.value.message


def test_une_date_anterieure_a_lorigine_est_refusee():
    policy = BackdatingPolicy()
    origine = REFERENCE_DATE - timedelta(days=100)

    with pytest.raises(DateBeforeOriginError):
        policy.enforce(
            origine - timedelta(days=1),
            "Motif",
            minimum_date=origine,
            minimum_label="la mise en service",
        )


def test_evaluate_ne_leve_pas_exception():
    policy = BackdatingPolicy()

    decision = policy.evaluate(REFERENCE_DATE + timedelta(days=10))

    assert decision.is_backdated is False
    assert decision.delay_days == 0
    assert decision.label == "Saisie en temps réel"


def test_evaluate_ignore_le_futur_pour_le_retard():
    policy = BackdatingPolicy()

    decision = policy.evaluate(REFERENCE_DATE + timedelta(days=5))

    assert decision.delay_days == 0


def test_empreinte_de_retrodatation():
    policy = BackdatingPolicy()
    cible = REFERENCE_DATE - timedelta(days=7)

    empreinte = policy.enforce(cible, "Reprise").fingerprint

    assert empreinte["target_date"] == cible.isoformat()
    assert empreinte["delay_days"] == 7
    assert empreinte["is_backdated"] is True
    assert empreinte["derogation_reason"] == "Reprise"


def test_saisie_retroactive_refusee_par_lapi_sans_motif(client, db, locations):
    """Contrôle de bout en bout : la règle s'applique bien à la saisie web/API."""
    reponse = client.post(
        "/api/equipments",
        json={
            "code": "PMP-XXX",
            "name": "Pompe saisie en retard",
            "location_id": locations["zone"].id,
            "effective_from": "2026-01-10",
        },
    )

    assert reponse.status_code == 422
    assert "motif de dérogation" in reponse.json()["detail"]


def test_saisie_retroactive_acceptee_avec_motif(client, locations):
    reponse = client.post(
        "/api/equipments",
        json={
            "code": "PMP-YYY",
            "name": "Pompe saisie en retard",
            "location_id": locations["zone"].id,
            "effective_from": "2026-01-10",
            "derogation_reason": "Reprise d'inventaire papier",
        },
    )

    assert reponse.status_code == 201
    assert reponse.json()["code"] == "PMP-YYY"

    # L'empreinte de rétrodatation est conservée sur la ligne d'implantation.
    historique = client.get(f"/api/equipments/{reponse.json()['id']}/placements").json()
    assert historique[0]["entry_delay_days"] == (date(2026, 6, 15) - date(2026, 1, 10)).days
    assert historique[0]["derogation_reason"] == "Reprise d'inventaire papier"


def test_audit_trace_la_derogation(client, locations):
    reponse = client.post(
        "/api/equipments",
        json={
            "code": "PMP-ZZZ",
            "name": "Pompe tracée",
            "location_id": locations["zone"].id,
            "effective_from": "2026-01-10",
            "derogation_reason": "Reprise d'inventaire papier",
        },
    )
    assert reponse.status_code == 201

    journal = client.get("/api/audit", params={"action": "backdate"}).json()

    assert len(journal) == 1
    assert journal[0]["reason"] == "Reprise d'inventaire papier"
    assert journal[0]["entity_type"] == "equipment"
