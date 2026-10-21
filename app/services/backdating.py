"""Moteur de règle « saisie rétroactive ».

Contexte pédagogique
--------------------
Dans un GMAO réel, on interdit (ou on limite strictement) la saisie d'une
opération datée dans le passé : une intervention saisie le 12 mars pour le
10 mars fausse le calcul du MTBF, du taux de réalisation du préventif et
de la charge des techniciens.

Cette application pédagogique, au contraire, **autorise** la saisie
rétroactive, mais elle l'encadre :

* la date du futur reste interdite (une dérogation ne fabrique pas le futur) ;
* une date passée **exige un motif de dérogation** ;
* chaque saisie rétroactive conserve une « empreinte » : date de saisie,
  retard en jours, motif, auteur ;
* le retard est mesuré et reporté dans le journal d'audit, ce qui permet de
  mesurer la qualité des données saisies.

Le même moteur (BackdatingPolicy) sert aux implantations/déplacements
d'équipements aujourd'hui, et aux interventions de maintenance demain.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.errors import (
    BackdatingReasonRequired,
    DateBeforeOriginError,
    FutureDateNotAllowed,
)
from app.services.clock import today


@dataclass(frozen=True)
class BackdatingDecision:
    """Verdict du moteur de rétrodatation pour une opération datée."""

    target_date: date
    reference_date: date
    delay_days: int
    derogation_reason: str | None

    @property
    def is_backdated(self) -> bool:
        return self.delay_days > 0

    @property
    def label(self) -> str:
        if not self.is_backdated:
            return "Saisie en temps réel"
        return f"Saisie rétroactive de {self.delay_days} jour(s)"

    @property
    def fingerprint(self) -> dict:
        """Empreinte sérialisable, stockée avec l'opération."""
        return {
            "target_date": self.target_date.isoformat(),
            "reference_date": self.reference_date.isoformat(),
            "delay_days": self.delay_days,
            "is_backdated": self.is_backdated,
            "derogation_reason": self.derogation_reason,
        }


class BackdatingPolicy:
    """Règles de saisie d'une opération datée."""

    def __init__(self, reference_date: date | None = None) -> None:
        self.reference_date = reference_date or today()

    def evaluate(
        self,
        target_date: date,
        derogation_reason: str | None = None,
    ) -> BackdatingDecision:
        """Calcule le retard sans lever d'exception."""
        delay = (self.reference_date - target_date).days
        reason = (derogation_reason or "").strip()
        return BackdatingDecision(
            target_date=target_date,
            reference_date=self.reference_date,
            delay_days=max(delay, 0),
            derogation_reason=reason or None,
        )

    def enforce(
        self,
        target_date: date,
        derogation_reason: str | None = None,
        *,
        minimum_date: date | None = None,
        minimum_label: str = "la date d'origine",
    ) -> BackdatingDecision:
        """Applique les règles et lève une exception si l'opération est irrecevable.

        Raises:
            FutureDateNotAllowed: la date est dans le futur.
            DateBeforeOriginError: la date précède l'origine admissible.
            BackdatingReasonRequired: date passée sans motif de dérogation.
        """
        decision = self.evaluate(target_date, derogation_reason)

        if target_date > self.reference_date:
            raise FutureDateNotAllowed(target_date.isoformat())

        if minimum_date is not None and target_date < minimum_date:
            raise DateBeforeOriginError(
                target_date.isoformat(),
                minimum_date.isoformat(),
                minimum_label,
            )

        if decision.is_backdated and not decision.derogation_reason:
            raise BackdatingReasonRequired(
                target_date.isoformat(),
                decision.delay_days,
            )

        return decision
