from __future__ import annotations

from app.web.templating import render


def render_error(request, message: str, status_code: int = 400):
    return render(
        request,
        "errors/simple.html",
        {"page_title": "Erreur", "message": message},
        status_code=status_code,
    )
