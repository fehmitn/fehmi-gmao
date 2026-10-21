"""Service des usines / sites."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.errors import ConflictError, NotFoundError
from app.models.enums import AuditAction
from app.models.site import Site
from app.models.user import User
from app.repositories.equipment import EquipmentRepository
from app.repositories.location import LocationRepository
from app.repositories.site import SiteRepository
from app.schemas.site import SiteCreate, SiteUpdate
from app.services.audit_service import AuditService


class SiteService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = SiteRepository(db)
        self.location_repository = LocationRepository(db)
        self.equipment_repository = EquipmentRepository(db)
        self.audit = AuditService(db)

    def list(self, active_only: bool = False) -> list[Site]:
        return self.repository.list_all(active_only=active_only)

    def get(self, site_id: int) -> Site:
        site = self.repository.get(site_id)
        if site is None:
            raise NotFoundError(f"Usine {site_id} introuvable.")
        return site

    def create(self, payload: SiteCreate, actor: User | None = None) -> Site:
        code = payload.code.strip()
        if self.repository.get_by_code(code):
            raise ConflictError(f"Une usine avec le code '{code}' existe déjà.")
        site = Site(
            code=code,
            name=payload.name.strip(),
            description=payload.description,
            address=payload.address,
            city=payload.city,
            country=payload.country,
            timezone=payload.timezone,
            is_active=payload.is_active,
        )
        site = self.repository.add(site)
        self.audit.record(
            AuditAction.CREATE,
            "site",
            site.id,
            actor=actor,
            payload={"code": site.code, "name": site.name},
        )
        return site

    def update(
        self,
        site: Site,
        payload: SiteUpdate,
        actor: User | None = None,
    ) -> Site:
        data = payload.model_dump(exclude_unset=True)
        if "code" in data and data["code"]:
            code = str(data["code"]).strip()
            existing = self.repository.get_by_code(code)
            if existing is not None and existing.id != site.id:
                raise ConflictError(f"Une usine avec le code '{code}' existe déjà.")
            site.code = code
        if "name" in data and data["name"]:
            site.name = str(data["name"]).strip()
        for field in ("description", "address", "city", "country", "timezone"):
            if field in data:
                value = data[field]
                setattr(site, field, value.strip() if isinstance(value, str) else value)
        if "is_active" in data and data["is_active"] is not None:
            site.is_active = bool(data["is_active"])

        site = self.repository.save(site)
        self.audit.record(
            AuditAction.UPDATE,
            "site",
            site.id,
            actor=actor,
            payload={k: str(v) for k, v in data.items() if v is not None},
        )
        return site

    def delete(self, site: Site, actor: User | None = None) -> None:
        equipment_count = self.equipment_repository.count_by_site().get(site.id, 0)
        if equipment_count:
            raise ConflictError(
                f"Impossible de supprimer l'usine '{site.code}' : "
                f"{equipment_count} équipement(s) y sont rattachés."
            )
        payload = {"code": site.code, "name": site.name}
        site_id = site.id
        self.repository.delete(site)
        self.audit.record(AuditAction.DELETE, "site", site_id, actor=actor, payload=payload)

    def enrich(self, site: Site) -> Site:
        """Ajoute les compteurs affichés dans les listes."""
        site.location_count = len(self.location_repository.list_by_site(site.id))
        site.equipment_count = self.equipment_repository.count_by_site().get(site.id, 0)
        return site
