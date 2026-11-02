"""Configuration Jinja2 et utilitaires de rendu."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.config import TEMPLATES_DIR
from app.services.clock import today

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals["app_today"] = today


def _as_decimal(value) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def format_quantity(value) -> str:
    """Affiche une quantité sans zéros inutiles, avec la virgule française."""
    number = _as_decimal(value)
    if number is None:
        return "—"
    text = f"{number.normalize():f}"
    return text.replace(".", ",")


def format_money(value) -> str:
    """Affiche un montant avec deux décimales et séparateurs français."""
    number = _as_decimal(value)
    if number is None:
        return "—"
    text = f"{number:,.2f}"
    return text.replace(",", " ").replace(".", ",")


templates.env.filters["qty"] = format_quantity
templates.env.filters["money"] = format_money


def render(
    request: Request,
    name: str,
    context: dict | None = None,
    status_code: int = 200,
):
    """Rend un template avec le contexte standard (utilisateur, messages)."""
    payload = dict(context or {})
    payload.setdefault("request", request)
    payload.setdefault("msg", request.query_params.get("msg"))
    payload.setdefault("err", request.query_params.get("err"))
    return templates.TemplateResponse(
        request=request,
        name=name,
        context=payload,
        status_code=status_code,
    )
