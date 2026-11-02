"""Calcul des échéances de maintenance périodique.

Le moteur est volontairement pur (aucune dépendance à la base) : les tests
couvrent les fins de mois, les trois ancrages et les unités jours / semaines /
mois / années, ainsi que le calcul de l'échéance de référence d'un OT.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.models.enums import MaintenanceAnchor, MaintenanceIntervalUnit
from app.services.periodicity import (
    add_interval,
    add_months,
    first_due_date,
    next_due_date,
    occurrence,
    periodicity_label,
    previous_due_date,
    reference_due_date,
    resolve_anchor_date,
)


def test_add_months_respecte_la_fin_de_mois():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)
    assert add_months(date(2026, 3, 31), -1) == date(2026, 2, 28)
    assert add_months(date(2026, 1, 31), 2) == date(2026, 3, 31)


def test_add_interval_toutes_les_unites():
    assert add_interval(date(2026, 6, 1), 10, MaintenanceIntervalUnit.DAYS) == date(
        2026, 6, 11
    )
    assert add_interval(date(2026, 6, 1), 2, MaintenanceIntervalUnit.WEEKS) == date(
        2026, 6, 15
    )
    assert add_interval(date(2026, 1, 31), 1, MaintenanceIntervalUnit.MONTHS) == date(
        2026, 2, 28
    )
    assert add_interval(date(2024, 2, 29), 1, MaintenanceIntervalUnit.YEARS) == date(
        2025, 2, 28
    )


def test_intervalle_non_positif_refuse():
    with pytest.raises(ValueError):
        add_interval(date(2026, 6, 1), 0, MaintenanceIntervalUnit.DAYS)


def test_les_heures_ne_sont_pas_une_unite_calendaire():
    """Une périodicité en heures ne peut pas produire une date d'échéance."""
    with pytest.raises(ValueError):
        add_interval(date(2026, 6, 1), 500, MaintenanceIntervalUnit.HOURS)


def test_ancrage_date_fixe_est_la_premiere_echeance():
    fixed = date(2026, 5, 1)

    assert (
        first_due_date(
            fixed,
            3,
            MaintenanceIntervalUnit.MONTHS,
            MaintenanceAnchor.FIXED_DATE,
        )
        == fixed
    )
    assert occurrence(
        fixed, 3, MaintenanceIntervalUnit.MONTHS, MaintenanceAnchor.FIXED_DATE, 2
    ) == date(2026, 11, 1)


def test_ancrage_mise_en_service_decale_la_premiere_echeance():
    commissioning = date(2026, 1, 31)

    assert (
        first_due_date(
            commissioning,
            1,
            MaintenanceIntervalUnit.MONTHS,
            MaintenanceAnchor.COMMISSIONING,
        )
        == date(2026, 2, 28)
    )


def test_les_occurrences_partent_de_l_ancrage_sans_derive_de_fin_de_mois():
    """31 janvier + 2 mois = 31 mars, pas 28 mars (pas d'enchaînement)."""
    anchor = date(2026, 1, 31)

    assert (
        next_due_date(
            anchor,
            1,
            MaintenanceIntervalUnit.MONTHS,
            date(2026, 3, 1),
            MaintenanceAnchor.COMMISSIONING,
        )
        == date(2026, 3, 31)
    )
    assert (
        previous_due_date(
            anchor,
            1,
            MaintenanceIntervalUnit.MONTHS,
            date(2026, 3, 1),
            MaintenanceAnchor.COMMISSIONING,
        )
        == date(2026, 2, 28)
    )


def test_next_due_date_est_inclusive_et_saute_les_occurrences_passees():
    anchor = date(2026, 6, 1)

    assert (
        next_due_date(
            anchor,
            10,
            MaintenanceIntervalUnit.DAYS,
            date(2026, 6, 15),
            MaintenanceAnchor.COMMISSIONING,
        )
        == date(2026, 6, 21)
    )
    assert (
        next_due_date(
            anchor,
            10,
            MaintenanceIntervalUnit.DAYS,
            date(2026, 6, 11),
            MaintenanceAnchor.COMMISSIONING,
        )
        == date(2026, 6, 11)
    )


def test_previous_due_date_est_strictement_anterieure():
    anchor = date(2026, 6, 1)

    assert (
        previous_due_date(
            anchor,
            10,
            MaintenanceIntervalUnit.DAYS,
            date(2026, 6, 15),
            MaintenanceAnchor.COMMISSIONING,
        )
        == date(2026, 6, 11)
    )
    # La première échéance (11 juin) n'est pas encore « précédente » le 11 juin.
    assert (
        previous_due_date(
            anchor,
            10,
            MaintenanceIntervalUnit.DAYS,
            date(2026, 6, 11),
            MaintenanceAnchor.COMMISSIONING,
        )
        is None
    )


def test_reference_due_date_retient_la_derniere_echeance_couverte():
    anchor = date(2026, 1, 31)

    # Réalisation le 5 juin : la dernière échéance théorique est le 31 mai.
    assert reference_due_date(
        anchor,
        1,
        MaintenanceIntervalUnit.MONTHS,
        date(2026, 6, 5),
        MaintenanceAnchor.COMMISSIONING,
    ) == date(2026, 5, 31)
    # Réalisation exactement le jour de l'échéance.
    assert reference_due_date(
        anchor,
        1,
        MaintenanceIntervalUnit.MONTHS,
        date(2026, 3, 31),
        MaintenanceAnchor.COMMISSIONING,
    ) == date(2026, 3, 31)
    # Réalisation avant la première échéance : référence = première échéance.
    assert reference_due_date(
        anchor,
        1,
        MaintenanceIntervalUnit.MONTHS,
        date(2026, 2, 1),
        MaintenanceAnchor.COMMISSIONING,
    ) == date(2026, 2, 28)


def test_reference_due_date_en_jours():
    anchor = date(2026, 6, 1)

    assert reference_due_date(
        anchor,
        10,
        MaintenanceIntervalUnit.DAYS,
        date(2026, 6, 20),
        MaintenanceAnchor.COMMISSIONING,
    ) == date(2026, 6, 11)
    assert reference_due_date(
        anchor,
        10,
        MaintenanceIntervalUnit.DAYS,
        date(2026, 6, 21),
        MaintenanceAnchor.COMMISSIONING,
    ) == date(2026, 6, 21)


def test_resolve_anchor_date():
    fixed = date(2026, 5, 1)

    assert (
        resolve_anchor_date(
            MaintenanceAnchor.FIXED_DATE,
            fixed_date=fixed,
            commissioning_date=date(2020, 1, 1),
            first_placement_date=date(2021, 1, 1),
        )
        == fixed
    )
    assert resolve_anchor_date(
        MaintenanceAnchor.COMMISSIONING,
        fixed_date=fixed,
        commissioning_date=date(2020, 1, 1),
        first_placement_date=date(2021, 1, 1),
    ) == date(2020, 1, 1)
    assert resolve_anchor_date(
        MaintenanceAnchor.FIRST_PLACEMENT,
        fixed_date=fixed,
        commissioning_date=date(2020, 1, 1),
        first_placement_date=date(2021, 1, 1),
    ) == date(2021, 1, 1)
    assert (
        resolve_anchor_date(
            MaintenanceAnchor.COMMISSIONING,
            fixed_date=None,
            commissioning_date=None,
            first_placement_date=date(2021, 1, 1),
        )
        is None
    )


@pytest.mark.parametrize(
    ("value", "unit", "attendu"),
    [
        (1, MaintenanceIntervalUnit.DAYS, "chaque jour"),
        (7, MaintenanceIntervalUnit.DAYS, "tous les 7 jours"),
        (1, MaintenanceIntervalUnit.WEEKS, "chaque semaine"),
        (2, MaintenanceIntervalUnit.WEEKS, "tous les 2 semaines"),
        (1, MaintenanceIntervalUnit.MONTHS, "chaque mois"),
        (3, MaintenanceIntervalUnit.MONTHS, "tous les 3 mois"),
        (1, MaintenanceIntervalUnit.YEARS, "chaque année"),
        (5, MaintenanceIntervalUnit.YEARS, "tous les 5 ans"),
        (1, MaintenanceIntervalUnit.HOURS, "chaque heure de fonctionnement"),
        (500, MaintenanceIntervalUnit.HOURS, "toutes les 500 heures de fonctionnement"),
    ],
)
def test_libelle_de_periodicite(value, unit, attendu):
    assert periodicity_label(value, unit) == attendu
