"""Moteur de calcul des échéances de maintenance périodique.

L'échéancier est une **projection théorique** : les occurrences sont
calculées depuis une date d'ancrage (mise en service, première implantation
ou date fixe). Aucune échéance n'est stockée par équipement ; les réalisations
d'OT viennent seulement logger l'écart avec l'échéance théorique de référence.

Le calcul est volontairement sans dépendance externe : ``add_months`` gère la
fin de mois (31 janvier + 1 mois = 28 ou 29 février) comme le ferait un
calendrier, contrairement à un ajout de 30 jours. Les occurrences sont
calculées **depuis l'ancrage** (et non en chaînant les ajouts) afin d'éviter
une dérive de fin de mois : 31 janvier + 2 mois = 31 mars.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta

from app.models.enums import MaintenanceAnchor, MaintenanceIntervalUnit

#: Garde-fou contre une boucle infinie sur une donnée corrompue.
MAX_ITERATIONS = 100_000


def add_months(day: date, months: int) -> date:
    """Ajoute un nombre de mois en respectant la fin de mois."""
    month_index = day.month - 1 + months
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(day.day, last_day))


def add_interval(day: date, value: int, unit: MaintenanceIntervalUnit | str) -> date:
    """Ajoute un intervalle calendaire à une date."""
    if value <= 0:
        raise ValueError("La périodicité doit être strictement positive.")
    unit = MaintenanceIntervalUnit(unit)
    if unit is MaintenanceIntervalUnit.DAYS:
        return day + timedelta(days=value)
    if unit is MaintenanceIntervalUnit.WEEKS:
        return day + timedelta(weeks=value)
    if unit is MaintenanceIntervalUnit.MONTHS:
        return add_months(day, value)
    if unit is MaintenanceIntervalUnit.YEARS:
        return add_months(day, value * 12)
    if unit is MaintenanceIntervalUnit.HOURS:
        raise ValueError("Les heures de fonctionnement ne sont pas basées sur une date.")
    raise ValueError(f"Unité de périodicité inconnue : {unit}")


def resolve_anchor_date(
    anchor: MaintenanceAnchor | str,
    *,
    fixed_date: date | None,
    commissioning_date: date | None,
    first_placement_date: date | None,
) -> date | None:
    """Résout la date d'ancrage effective, ou None si elle est indisponible."""
    anchor = MaintenanceAnchor(anchor)
    if anchor is MaintenanceAnchor.FIXED_DATE:
        return fixed_date
    if anchor is MaintenanceAnchor.COMMISSIONING:
        return commissioning_date
    if anchor is MaintenanceAnchor.FIRST_PLACEMENT:
        return first_placement_date
    return None


def first_due_date(
    anchor: date,
    value: int,
    unit: MaintenanceIntervalUnit | str,
    anchor_kind: MaintenanceAnchor | str = MaintenanceAnchor.COMMISSIONING,
) -> date:
    """Première échéance théorique.

    Pour une date fixe, la date saisie **est** la première échéance. Pour une
    mise en service / première implantation, l'ancrage est le point de départ
    et la première échéance arrive un intervalle plus tard.
    """
    return occurrence(anchor, value, unit, anchor_kind, 0)


def occurrence(
    anchor: date,
    value: int,
    unit: MaintenanceIntervalUnit | str,
    anchor_kind: MaintenanceAnchor | str,
    index: int,
) -> date:
    """k-ième occurrence (0 = première échéance), calculée depuis l'ancrage.

    Le calcul repart toujours de l'ancrage pour conserver le jour du mois
    (sauf mois trop court) et éviter la dérive des fins de mois.
    """
    if index < 0:
        raise ValueError("L'index d'occurrence doit être positif ou nul.")
    unit = MaintenanceIntervalUnit(unit)
    if MaintenanceAnchor(anchor_kind) is MaintenanceAnchor.FIXED_DATE:
        offset = index
    else:
        offset = index + 1
    if offset == 0:
        return anchor
    return add_interval(anchor, value * offset, unit)


def _estimate_index_days(
    first: date,
    reference: date,
    value: int,
    unit: MaintenanceIntervalUnit,
    *,
    inclusive: bool,
) -> int:
    """Estimation rapide du nombre d'intervalles en jours / semaines."""
    step = value if unit is MaintenanceIntervalUnit.DAYS else value * 7
    delta = (reference - first).days
    if delta <= 0:
        return 0
    if inclusive:
        return delta // step
    return (delta - 1) // step


def next_due_date(
    anchor: date,
    value: int,
    unit: MaintenanceIntervalUnit | str,
    reference_day: date,
    anchor_kind: MaintenanceAnchor | str = MaintenanceAnchor.COMMISSIONING,
) -> date:
    """Première occurrence théorique supérieure ou égale au jour de référence."""
    unit = MaintenanceIntervalUnit(unit)
    first = first_due_date(anchor, value, unit, anchor_kind)
    if first >= reference_day:
        return first

    index = 0
    if unit in (MaintenanceIntervalUnit.DAYS, MaintenanceIntervalUnit.WEEKS):
        index = _estimate_index_days(
            first, reference_day, value, unit, inclusive=True
        )
    iterations = 0
    while True:
        current = occurrence(anchor, value, unit, anchor_kind, index)
        if current >= reference_day:
            # L'estimation peut dépasser d'un cran : reculer si possible.
            if index > 0:
                previous = occurrence(anchor, value, unit, anchor_kind, index - 1)
                if previous >= reference_day:
                    index -= 1
                    continue
            return current
        index += 1
        iterations += 1
        if iterations > MAX_ITERATIONS:
            raise ValueError("Périodicité trop courte : calcul d'échéance abandonné.")


def previous_due_date(
    anchor: date,
    value: int,
    unit: MaintenanceIntervalUnit | str,
    reference_day: date,
    anchor_kind: MaintenanceAnchor | str = MaintenanceAnchor.COMMISSIONING,
) -> date | None:
    """Dernière occurrence théorique **strictement antérieure** au jour donné."""
    unit = MaintenanceIntervalUnit(unit)
    first = first_due_date(anchor, value, unit, anchor_kind)
    if first >= reference_day:
        return None

    index = 0
    if unit in (MaintenanceIntervalUnit.DAYS, MaintenanceIntervalUnit.WEEKS):
        index = _estimate_index_days(
            first, reference_day, value, unit, inclusive=False
        )
    iterations = 0
    # Ajustement autour de l'estimation.
    while occurrence(anchor, value, unit, anchor_kind, index + 1) < reference_day:
        index += 1
        iterations += 1
        if iterations > MAX_ITERATIONS:
            raise ValueError("Périodicité trop courte : calcul d'échéance abandonné.")
    while index > 0 and occurrence(anchor, value, unit, anchor_kind, index) >= reference_day:
        index -= 1
        iterations += 1
        if iterations > MAX_ITERATIONS:
            raise ValueError("Périodicité trop courte : calcul d'échéance abandonné.")
    current = occurrence(anchor, value, unit, anchor_kind, index)
    if current >= reference_day:
        return None
    return current


def reference_due_date(
    anchor: date,
    value: int,
    unit: MaintenanceIntervalUnit | str,
    performed_on: date,
    anchor_kind: MaintenanceAnchor | str = MaintenanceAnchor.COMMISSIONING,
) -> date:
    """Échéance de référence d'une réalisation.

    On retient la dernière occurrence théorique **au plus tard** égale à la
    date de réalisation. Si l'OT est réalisé avant la première échéance, la
    référence est cette première échéance (l'écart sera négatif = avance).
    """
    unit = MaintenanceIntervalUnit(unit)
    first = first_due_date(anchor, value, unit, anchor_kind)
    if performed_on < first:
        return first

    index = 0
    if unit in (MaintenanceIntervalUnit.DAYS, MaintenanceIntervalUnit.WEEKS):
        index = _estimate_index_days(
            first, performed_on, value, unit, inclusive=True
        )
    iterations = 0
    while occurrence(anchor, value, unit, anchor_kind, index + 1) <= performed_on:
        index += 1
        iterations += 1
        if iterations > MAX_ITERATIONS:
            raise ValueError("Périodicité trop courte : calcul d'échéance abandonné.")
    while index > 0 and occurrence(anchor, value, unit, anchor_kind, index) > performed_on:
        index -= 1
        iterations += 1
        if iterations > MAX_ITERATIONS:
            raise ValueError("Périodicité trop courte : calcul d'échéance abandonné.")
    return occurrence(anchor, value, unit, anchor_kind, index)


def periodicity_label(value: int, unit: MaintenanceIntervalUnit | str) -> str:
    """Libellé lisible : « tous les 3 mois », « chaque semaine »..."""
    unit = MaintenanceIntervalUnit(unit)
    if value == 1:
        return {
            MaintenanceIntervalUnit.DAYS: "chaque jour",
            MaintenanceIntervalUnit.WEEKS: "chaque semaine",
            MaintenanceIntervalUnit.MONTHS: "chaque mois",
            MaintenanceIntervalUnit.YEARS: "chaque année",
            MaintenanceIntervalUnit.HOURS: "chaque heure de fonctionnement",
        }[unit]
    plural = {
        MaintenanceIntervalUnit.DAYS: "jours",
        MaintenanceIntervalUnit.WEEKS: "semaines",
        MaintenanceIntervalUnit.MONTHS: "mois",
        MaintenanceIntervalUnit.YEARS: "ans",
        MaintenanceIntervalUnit.HOURS: "heures de fonctionnement",
    }[unit]
    if unit is MaintenanceIntervalUnit.HOURS:
        return f"toutes les {value} heures de fonctionnement"
    return f"tous les {value} {plural}"
