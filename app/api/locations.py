"""Routes API : emplacements et types d'emplacement."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.location import (
    LocationCreate,
    LocationRead,
    LocationTypeCreate,
    LocationTypeRead,
    LocationUpdate,
)
from app.services.location_service import LocationService
from app.repositories.location_type import LocationTypeRepository

router = APIRouter(prefix="/api", tags=["locations"])


@router.get("/location-types", response_model=list[LocationTypeRead])
def list_location_types(
    active_only: bool = False,
    db: Session = Depends(get_db),
) -> list[LocationTypeRead]:
    repository = LocationTypeRepository(db)
    return [
        LocationTypeRead.model_validate(item)
        for item in repository.list_all(active_only=active_only)
    ]


@router.post(
    "/location-types",
    response_model=LocationTypeRead,
    status_code=status.HTTP_201_CREATED,
)
def create_location_type(
    payload: LocationTypeCreate,
    db: Session = Depends(get_db),
) -> LocationTypeRead:
    from app.models.location_type import LocationType

    repository = LocationTypeRepository(db)
    if repository.get_by_code(payload.code.strip()):
        from app.errors import ConflictError

        raise ConflictError(
            f"Un type d'emplacement avec le code '{payload.code}' existe déjà."
        )
    created = repository.add(
        LocationType(
            code=payload.code.strip(),
            label=payload.label.strip(),
            description=payload.description,
            sort_order=payload.sort_order,
        )
    )
    return LocationTypeRead.model_validate(created)


@router.get("/sites/{site_id}/locations", response_model=list[LocationRead])
def list_locations(site_id: int, db: Session = Depends(get_db)) -> list[LocationRead]:
    service = LocationService(db)
    return [
        LocationRead.model_validate(service.enrich(location))
        for location in service.list_by_site(site_id)
    ]


@router.get("/locations", response_model=list[LocationRead])
def list_all_locations(db: Session = Depends(get_db)) -> list[LocationRead]:
    service = LocationService(db)
    return [
        LocationRead.model_validate(service.enrich(location))
        for location in service.list_all()
    ]


@router.post("/locations", response_model=LocationRead, status_code=status.HTTP_201_CREATED)
def create_location(
    payload: LocationCreate,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> LocationRead:
    service = LocationService(db)
    location = service.create(payload, actor=actor)
    return LocationRead.model_validate(service.enrich(location))


@router.get("/locations/{location_id}", response_model=LocationRead)
def get_location(location_id: int, db: Session = Depends(get_db)) -> LocationRead:
    service = LocationService(db)
    return LocationRead.model_validate(service.enrich(service.get(location_id)))


@router.put("/locations/{location_id}", response_model=LocationRead)
def update_location(
    location_id: int,
    payload: LocationUpdate,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> LocationRead:
    service = LocationService(db)
    location = service.update(service.get(location_id), payload, actor=actor)
    return LocationRead.model_validate(service.enrich(location))


@router.delete("/locations/{location_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_location(
    location_id: int,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    service = LocationService(db)
    service.delete(service.get(location_id), actor=actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
