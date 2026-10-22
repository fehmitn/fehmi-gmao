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
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api import (
    audit_router,
    equipment_router,
    equipment_types_router,
    locations_router,
    sites_router,
)
from app.config import STATIC_DIR
from app.database import engine, init_db
from app.errors import DomainError
from app.web.router import router as web_router


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
    version="0.2.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# API REST
app.include_router(sites_router)
app.include_router(locations_router)
app.include_router(equipment_types_router)
app.include_router(equipment_router)
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
