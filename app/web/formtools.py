"""Outils de lecture des formulaires HTML (formulaires HTMX ou standard)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from fastapi import Request


async def form_data(request: Request) -> dict[str, str]:
    """Transforme un formulaire en dictionnaire de chaînes."""
    form = await request.form()
    return {key: (value if isinstance(value, str) else "") for key, value in form.items()}


def text(data: dict[str, str], key: str, default: str | None = None) -> str | None:
    value = (data.get(key) or "").strip()
    return value or default


def optional_text(data: dict[str, str], key: str) -> str | None:
    value = (data.get(key) or "").strip()
    return value or None


def as_int(data: dict[str, str], key: str) -> int | None:
    value = (data.get(key) or "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"'{key}' doit être un entier.") from exc


def as_bool(data: dict[str, str], key: str, default: bool = False) -> bool:
    value = (data.get(key) or "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "on", "oui", "yes"}


def as_date(data: dict[str, str], key: str) -> date | None:
    value = (data.get(key) or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"'{key}' doit être une date au format AAAA-MM-JJ.") from exc


def as_datetime(data: dict[str, str], key: str) -> datetime | None:
    """Lit un champ ``datetime-local`` (AAAA-MM-JJTHH:MM) ou ISO complet."""
    value = (data.get(key) or "").strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            f"'{key}' doit être une date et une heure au format AAAA-MM-JJTHH:MM."
        ) from exc


def as_decimal(data: dict[str, str], key: str) -> Decimal | None:
    value = (data.get(key) or "").strip().replace(",", ".")
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"'{key}' doit être un montant numérique.") from exc
