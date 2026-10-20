from fastapi import FastAPI

from app.api import equipment_router
from app.database import init_db

app = FastAPI(
    title="GMAO",
    description="Gestion de maintenance assistée par ordinateur",
    version="0.1.0",
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


app.include_router(equipment_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
