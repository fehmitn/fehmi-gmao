"""Exceptions du domaine, traduites en réponses HTTP par les couches API et web."""

from __future__ import annotations


class DomainError(Exception):
    """Erreur métier attendue, affichable telle quelle à l'utilisateur."""

    status_code = 400

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class NotFoundError(DomainError):
    status_code = 404


class ConflictError(DomainError):
    """Conflit d'unicité ou d'état (code déjà utilisé, opération impossible)."""

    status_code = 409


class ValidationError(DomainError):
    """Règle de saisie non respectée."""

    status_code = 422


class AuthenticationRequiredError(DomainError):
    """Action réservée aux utilisateurs connectés."""

    status_code = 401


class PermissionDeniedError(DomainError):
    """Rôle ou affectation insuffisants pour effectuer l'action."""

    status_code = 403


class BackdatingReasonRequired(ValidationError):
    """Saisie rétroative sans motif de dérogation."""

    def __init__(self, target_date: str, delay_days: int) -> None:
        self.target_date = target_date
        self.delay_days = delay_days
        super().__init__(
            f"Saisie rétroactive au {target_date} ({delay_days} jour(s) de retard) : "
            "un motif de dérogation est obligatoire."
        )


class FutureDateNotAllowed(ValidationError):
    """Date postérieure à aujourd'hui : toujours interdite, même en dérogation."""

    def __init__(self, target_date: str) -> None:
        self.target_date = target_date
        super().__init__(
            f"La date {target_date} est dans le futur : la saisie rétroative "
            "ne s'applique qu'aux dates passées."
        )


class DateBeforeOriginError(ValidationError):
    """Date antérieure à l'origine admise (mise en service, création...)."""

    def __init__(self, target_date: str, origin_date: str, origin_label: str) -> None:
        self.target_date = target_date
        super().__init__(
            f"La date {target_date} est antérieure à {origin_label} ({origin_date})."
        )
