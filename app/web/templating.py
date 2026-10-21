"""Configuration Jinja2 et utilitaires de rendu."""

from __future__ import annotations

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.config import TEMPLATES_DIR
from app.services.clock import today

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals["app_today"] = today


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
