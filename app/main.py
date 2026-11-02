"""Point d'entrée de l'application GMAO.

Expose :
  * l'API REST sur /api (documentée sur /docs) ;
  * l'interface web Jinja2 + HTMX sur / ;
  * les fichiers statiques sur /static.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api import (
    analytics_router,
    audit_router,
    equipment_router,
    equipment_types_router,
    interventions_router,
    locations_router,
    maintenance_execution_router,
    maintenance_schedule_router,
    maintenance_suppliers_router,
    maintenance_tools_router,
    periodic_maintenance_router,
    sites_router,
    spare_parts_router,
    work_orders_router,
)
from app.config import CURRENT_USER_COOKIE, STATIC_DIR
from app.database import SessionLocal, engine, init_db
from app.errors import DomainError
from app.models.user import User
from app.web.router import router as web_router
from app.web.session import decode_user


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield


app = FastAPI(
    title="GMAO",
    description=(
        "Gestion de maintenance assistée par ordinateur — application pédagogique. "
        "La saisie d'opérations datées dans le passé est autorisée, mais encadrée : "
        "motif de dérogation obligatoire, retard mesuré, journalisation."
    ),
    version="0.5.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

_PUBLIC_PATHS = {"/login", "/logout", "/health", "/docs", "/redoc", "/openapi.json"}
_PUBLIC_PREFIXES = ("/static", "/api")


@app.middleware("http")
async def require_web_login(request: Request, call_next):
    """Protège l'interface web ; l'API reste utilisable avec X-GMAO-User."""
    import os

    if os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("GMAO_NO_AUTH") == "1":
        return await call_next(request)
    path = request.url.path
    if path in _PUBLIC_PATHS or path.startswith(_PUBLIC_PREFIXES):
        return await call_next(request)

    token = request.cookies.get(CURRENT_USER_COOKIE)
    user_id = decode_user(token)
    if user_id is not None:
        with SessionLocal() as db:
            user = db.get(User, user_id)
            if user is not None and user.is_active:
                request.state.current_user = user
                return await call_next(request)

    from urllib.parse import quote

    target = quote(path + (f"?{request.url.query}" if request.url.query else ""), safe="/?=&")
    return RedirectResponse(url=f"/login?next={target}", status_code=303)


# API REST
app.include_router(analytics_router)
app.include_router(sites_router)
app.include_router(locations_router)
app.include_router(equipment_types_router)
app.include_router(equipment_router)
app.include_router(maintenance_suppliers_router)
app.include_router(periodic_maintenance_router)
app.include_router(maintenance_execution_router)
app.include_router(maintenance_schedule_router)
app.include_router(spare_parts_router)
app.include_router(maintenance_tools_router)
app.include_router(work_orders_router)
app.include_router(interventions_router)
app.include_router(audit_router)

# Interface web
app.include_router(web_router)


@app.exception_handler(DomainError)
async def domain_error_handler(_request: Request, exc: DomainError) -> JSONResponse:
    """Transforme une erreur métier en réponse HTTP cohérente."""
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.get("/health")
def health() -> dict[str, str]:
    """Sonde de santé : interroge réellement la base.

    Le HEALTHCHECK du conteneur s'appuie sur cette route ; un simple
    « status: ok » ne détecterait pas une base verrouillée ou absente.
    """
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"status": "ok"}
