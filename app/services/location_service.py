"""Service des emplacements (arborescence par usine)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import MAX_LOCATION_DEPTH
from app.errors import ConflictError, NotFoundError, ValidationError
from app.models.enums import AuditAction
from app.models.location import Location
from app.models.user import User
from app.repositories.equipment_location import EquipmentLocationRepository
from app.repositories.location import LocationRepository
from app.repositories.location_type import LocationTypeRepository
from app.repositories.site import SiteRepository
from app.schemas.location import LocationCreate, LocationUpdate
from app.services.audit_service import AuditService


class LocationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = LocationRepository(db)
        self.type_repository = LocationTypeRepository(db)
        self.site_repository = SiteRepository(db)
        self.placement_repository = EquipmentLocationRepository(db)
        self.audit = AuditService(db)

    # ------------------------------------------------------------------ lecture
    def list_by_site(self, site_id: int) -> list[Location]:
        return self.repository.list_by_site(site_id)

    def list_all(self) -> list[Location]:
        return self.repository.list_all()

    def get(self, location_id: int) -> Location:
        location = self.repository.get(location_id)
        if location is None:
            raise NotFoundError(f"Emplacement {location_id} introuvable.")
        return location

    def tree(self, site_id: int) -> list[dict]:
        """Arborescence imbriquée de l'usine, prête pour l'affichage."""
        locations = self.list_by_site(site_id)
        nodes: dict[int, dict] = {}
        for location in locations:
            nodes[location.id] = {
                "id": location.id,
                "code": location.code,
                "name": location.name,
                "description": location.description,
                "is_active": location.is_active,
                "location_type_id": location.location_type_id,
                "location_type_label": location.location_type.label,
                "parent_id": location.parent_id,
                "path": self.repository.path(location.id),
                "depth": self.repository.depth(location.id),
                "equipment_count": self.repository.count_equipments(location.id),
                "children": [],
            }
        roots: list[dict] = []
        for location in locations:
            node = nodes[location.id]
            parent = nodes.get(location.parent_id) if location.parent_id else None
            if parent is None:
                roots.append(node)
            else:
                parent["children"].append(node)
        return roots

    def enrich(self, location: Location) -> Location:
        site = self.site_repository.get(location.site_id)
        location.site_code = site.code if site else None
        location.path = self.repository.path(location.id)
        location.depth = self.repository.depth(location.id)
        location.equipment_count = self.repository.count_equipments(location.id)
        location.child_count = len(self.repository.children(location.id))
        return location

    # ------------------------------------------------------------------ écriture
    def create(self, payload: LocationCreate, actor: User | None = None) -> Location:
        code = payload.code.strip()
        if self.repository.get_by_code(payload.site_id, code):
            raise ConflictError(
                f"Un emplacement avec le code '{code}' existe déjà dans cette usine."
            )
        if self.type_repository.get(payload.location_type_id) is None:
            raise NotFoundError(f"Type d'emplacement {payload.location_type_id} introuvable.")

        parent = None
        if payload.parent_id is not None:
            parent = self.get(payload.parent_id)
            if parent.site_id != payload.site_id:
                raise ValidationError(
                    "Le parent doit appartenir à la même usine que l'emplacement."
                )
            if self.repository.depth(parent.id) + 1 > MAX_LOCATION_DEPTH:
                raise ValidationError(
                    f"Profondeur maximale atteinte ({MAX_LOCATION_DEPTH} niveaux)."
                )

        location = Location(
            site_id=payload.site_id,
            parent_id=payload.parent_id,
            location_type_id=payload.location_type_id,
            code=code,
            name=payload.name.strip(),
            description=payload.description,
            is_active=payload.is_active,
        )
        location = self.repository.add(location)
        self.audit.record(
            AuditAction.CREATE,
            "location",
            location.id,
            actor=actor,
            payload={"code": location.code, "name": location.name, "site_id": location.site_id},
        )
        return location

    def update(
        self,
        location: Location,
        payload: LocationUpdate,
        actor: User | None = None,
    ) -> Location:
        data = payload.model_dump(exclude_unset=True)
        if "parent_id" in data:
            self._set_parent(location, data["parent_id"])
        if "location_type_id" in data and data["location_type_id"]:
            if self.type_repository.get(data["location_type_id"]) is None:
                raise NotFoundError(
                    f"Type d'emplacement {data['location_type_id']} introuvable."
                )
            location.location_type_id = data["location_type_id"]
        if "code" in data and data["code"]:
            code = str(data["code"]).strip()
            existing = self.repository.get_by_code(location.site_id, code)
            if existing is not None and existing.id != location.id:
                raise ConflictError(
                    f"Un emplacement avec le code '{code}' existe déjà dans cette usine."
                )
            location.code = code
        if "name" in data and data["name"]:
            location.name = str(data["name"]).strip()
        if "description" in data:
            value = data["description"]
            location.description = value.strip() if isinstance(value, str) else value
        if "is_active" in data and data["is_active"] is not None:
            location.is_active = bool(data["is_active"])

        location = self.repository.save(location)
        self.audit.record(
            AuditAction.UPDATE,
            "location",
            location.id,
            actor=actor,
            payload={k: str(v) for k, v in data.items() if v is not None},
        )
        return location

    def move(
        self,
        location: Location,
        new_parent_id: int | None,
        actor: User | None = None,
    ) -> Location:
        """Déplace un emplacement (nouveau parent) en refusant les cycles."""
        self._set_parent(location, new_parent_id)
        location = self.repository.save(location)
        self.audit.record(
            AuditAction.MOVE,
            "location",
            location.id,
            actor=actor,
            payload={
                "code": location.code,
                "new_parent_id": str(new_parent_id),
                "path": self.repository.path(location.id),
            },
        )
        return location

    def delete(self, location: Location, actor: User | None = None) -> None:
        children = self.repository.children(location.id)
        if children:
            raise ConflictError(
                f"Impossible de supprimer '{location.code}' : "
                f"{len(children)} sous-emplacement(s) lui sont rattachés."
            )
        if self.repository.has_history(location.id):
            raise ConflictError(
                f"Impossible de supprimer '{location.code}' : "
                "des équipements y ont été implantés (historique conservé)."
            )
        payload = {"code": location.code, "name": location.name}
        location_id = location.id
        self.repository.delete(location)
        self.audit.record(
            AuditAction.DELETE, "location", location_id, actor=actor, payload=payload
        )

    # ------------------------------------------------------------------ interne
    def _set_parent(self, location: Location, new_parent_id: int | None) -> None:
        if new_parent_id is None:
            location.parent_id = None
            return
        if new_parent_id == location.id:
            raise ValidationError("Un emplacement ne peut pas être son propre parent.")
        parent = self.get(new_parent_id)
        if parent.site_id != location.site_id:
            raise ValidationError(
                "Le parent doit appartenir à la même usine que l'emplacement."
            )
        if new_parent_id in self.repository.subtree_ids(location.id):
            raise ValidationError(
                "Déplacement impossible : le parent choisi est un sous-emplacement "
                "de l'emplacement déplacé (cycle). "
            )
        if self.repository.depth(parent.id) + 1 > MAX_LOCATION_DEPTH:
            raise ValidationError(
                f"Profondeur maximale atteinte ({MAX_LOCATION_DEPTH} niveaux)."
            )
        location.parent_id = new_parent_id
