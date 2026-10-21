"""Routes API : usines / sites."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.site import SiteCreate, SiteRead, SiteUpdate
from app.services.site_service import SiteService

router = APIRouter(prefix="/api/sites", tags=["sites"])


@router.get("", response_model=list[SiteRead])
def list_sites(
    active_only: bool = False,
    db: Session = Depends(get_db),
) -> list[SiteRead]:
    service = SiteService(db)
    return [SiteRead.model_validate(service.enrich(site)) for site in service.list(active_only)]


@router.post("", response_model=SiteRead, status_code=status.HTTP_201_CREATED)
def create_site(
    payload: SiteCreate,
    response: Response,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> SiteRead:
    service = SiteService(db)
    site = service.create(payload, actor=actor)
    return SiteRead.model_validate(service.enrich(site))


@router.get("/{site_id}", response_model=SiteRead)
def get_site(site_id: int, db: Session = Depends(get_db)) -> SiteRead:
    service = SiteService(db)
    return SiteRead.model_validate(service.enrich(service.get(site_id)))


@router.put("/{site_id}", response_model=SiteRead)
def update_site(
    site_id: int,
    payload: SiteUpdate,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> SiteRead:
    service = SiteService(db)
    site = service.update(service.get(site_id), payload, actor=actor)
    return SiteRead.model_validate(service.enrich(site))


@router.delete("/{site_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_site(
    site_id: int,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    service = SiteService(db)
    service.delete(service.get(site_id), actor=actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
