"""Horloge du domaine.

La date du jour est injectable (variable d'environnement GMAO_TODAY) afin
de pouvoir tester les règles de rétrodatation de façon déterministe.
"""

from __future__ import annotations

from datetime import date, datetime

from app.config import TODAY_OVERRIDE


def today() -> date:
    if TODAY_OVERRIDE:
        return date.fromisoformat(TODAY_OVERRIDE)
    return date.today()


def now() -> datetime:
    return datetime.now()
