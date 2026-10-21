"""Configuration de la base de test et fixtures partagées.

La base de test est un fichier SQLite temporaire, distinct de la base de
développement. La date « du jour » est figée (``GMAO_TODAY``) afin que les
tests de rétrodatation soient déterministes.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path

TEST_DB_PATH = Path(tempfile.gettempdir()) / "gmao_tests.db"

# Doit être défini AVANT l'import de app.config (lecture au moment de l'import).
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH.as_posix()}"
os.environ["GMAO_TODAY"] = "2026-06-15"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.enums import Criticality, EquipmentStatus  # noqa: E402
from app.repositories.location_type import LocationTypeRepository  # noqa: E402
from app.repositories.user import UserRepository  # noqa: E402
from app.schemas.equipment import EquipmentCreate  # noqa: E402
from app.schemas.equipment_type import EquipmentTypeCreate  # noqa: E402
from app.schemas.location import LocationCreate  # noqa: E402
from app.schemas.site import SiteCreate  # noqa: E402
from app.services.equipment_service import EquipmentService  # noqa: E402
from app.services.equipment_type_service import EquipmentTypeService  # noqa: E402
from app.services.location_service import LocationService  # noqa: E402
from app.services.site_service import SiteService  # noqa: E402

#: Date de référence figée des tests (cf. variable d'environnement GMAO_TODAY).
REFERENCE_DATE = date(2026, 6, 15)


@pytest.fixture()
def db() -> Iterator[Session]:
    """Session SQLAlchemy sur une base neuve pour chaque test."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db: Session) -> Iterator[TestClient]:
    """Client HTTP (FastAPI) branché sur la base de test."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def admin(db: Session):
    users = {user.username: user for user in UserRepository(db).list_active()}
    if not users:
        from app.models.user import User

        user = User(username="admin", display_name="Administrateur", role="admin")
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    return users["admin"]


@pytest.fixture()
def location_type(db: Session):
    repository = LocationTypeRepository(db)
    item = repository.get_by_code("ATL")
    if item is None:
        from app.models.location_type import LocationType

        item = LocationType(code="ATL", label="Atelier", sort_order=20)
        db.add(item)
        db.commit()
        db.refresh(item)
    return item


@pytest.fixture()
def site(db: Session, admin):
    return SiteService(db).create(
        SiteCreate(code="USN-01", name="Usine de test", city="Casablanca"),
        actor=admin,
    )


@pytest.fixture()
def locations(db: Session, site, location_type):
    """Arborescence : BAT-01 > ATL-01 > ZON-01, plus une racine Atelier Nord."""
    service = LocationService(db)
    bat = service.create(
        LocationCreate(
            site_id=site.id,
            location_type_id=location_type.id,
            code="BAT-01",
            name="Bâtiment A",
        )
    )
    atelier = service.create(
        LocationCreate(
            site_id=site.id,
            parent_id=bat.id,
            location_type_id=location_type.id,
            code="ATL-01",
            name="Atelier mécanique",
        )
    )
    zone = service.create(
        LocationCreate(
            site_id=site.id,
            parent_id=atelier.id,
            location_type_id=location_type.id,
            code="ZON-01",
            name="Zone des pompes",
        )
    )
    nord = service.create(
        LocationCreate(
            site_id=site.id,
            location_type_id=location_type.id,
            code="ATL-99",
            name="Atelier Nord",
        )
    )
    return {
        "batiment": bat,
        "atelier": atelier,
        "zone": zone,
        "nord": nord,
    }


@pytest.fixture()
def equipment_type(db: Session, admin):
    return EquipmentTypeService(db).create(
        EquipmentTypeCreate(
            code="PMP-CF",
            name="Pompe centrifuge",
            category="Pompes",
            manufacturer="Grundfos",
            model="CR 15-6",
            criticality=Criticality.B,
        ),
        actor=admin,
    )


@pytest.fixture()
def equipment(db: Session, locations, equipment_type, admin):
    return EquipmentService(db).create(
        EquipmentCreate(
            code="PMP-001",
            name="Pompe d'alimentation",
            equipment_type_id=equipment_type.id,
            location_id=locations["zone"].id,
            status=EquipmentStatus.OPERATIONAL,
            criticality=Criticality.B,
        ),
        actor=admin,
    )


@pytest.fixture()
def ancien_equipement(db: Session, locations, equipment_type, admin):
    """Équipement implanté dans le passé (saisie rétroactive justifiée)."""
    return EquipmentService(db).create(
        EquipmentCreate(
            code="PMP-OLD",
            name="Pompe ancienne",
            equipment_type_id=equipment_type.id,
            location_id=locations["zone"].id,
            status=EquipmentStatus.OPERATIONAL,
            criticality=Criticality.B,
            effective_from=REFERENCE_DATE - timedelta(days=100),
            derogation_reason="Reprise de l'inventaire papier de l'atelier",
        ),
        actor=admin,
    )
