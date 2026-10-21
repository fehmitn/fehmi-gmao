from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.equipment_location import EquipmentLocation
from app.models.location import Location


class LocationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, location_id: int) -> Location | None:
        return self.db.get(Location, location_id)

    def get_by_code(self, site_id: int, code: str) -> Location | None:
        stmt = select(Location).where(Location.site_id == site_id, Location.code == code)
        return self.db.scalars(stmt).first()

    def list_by_site(self, site_id: int) -> list[Location]:
        stmt = select(Location).where(Location.site_id == site_id).order_by(Location.code)
        return list(self.db.scalars(stmt).all())

    def list_all(self) -> list[Location]:
        stmt = select(Location).order_by(Location.site_id, Location.code)
        return list(self.db.scalars(stmt).all())

    def children(self, location_id: int) -> list[Location]:
        stmt = select(Location).where(Location.parent_id == location_id).order_by(Location.code)
        return list(self.db.scalars(stmt).all())

    def subtree_ids(self, root_id: int) -> list[int]:
        """Identifiants du sous-arbre (racine comprise) via une CTE récursive.

        La partie récursive est unie à la CTE elle-même (``cte.union_all``) :
        c'est la seule forme qui fait réellement itérer SQLite sur toute la
        profondeur de l'arbre.
        """
        cte = (
            select(Location.id).where(Location.id == root_id).cte("subtree", recursive=True)
        )
        descendants = select(Location.id).join(cte, Location.parent_id == cte.c.id)
        cte = cte.union_all(descendants)
        return list(self.db.scalars(select(cte.c.id)).all())

    def ancestors(self, location_id: int) -> list[Location]:
        """Emplacements ancêtres, de la racine jusqu'au parent direct.

        La remontée est protégée contre les cycles (données corrompues ou
        importées) : sans cette garde, une boucle infinie pourrait se
        produire.
        """
        chain: list[Location] = []
        visited = {location_id}
        current = self.get(location_id)
        while current is not None and current.parent_id is not None:
            if current.parent_id in visited:
                break
            visited.add(current.parent_id)
            parent = self.get(current.parent_id)
            if parent is None:
                break
            chain.append(parent)
            current = parent
        chain.reverse()
        return chain

    def path(self, location_id: int) -> str:
        """Chemin lisible « Usine / Bâtiment / Zone »."""
        location = self.get(location_id)
        if location is None:
            return ""
        parts = [ancestor.code for ancestor in self.ancestors(location_id)]
        parts.append(location.code)
        return " / ".join(parts)

    def depth(self, location_id: int) -> int:
        """Profondeur dans l'arbre (racine = 1)."""
        return len(self.ancestors(location_id)) + 1

    def count_equipments(self, location_id: int) -> int:
        stmt = select(func.count(EquipmentLocation.id)).where(
            EquipmentLocation.location_id == location_id,
            EquipmentLocation.effective_to.is_(None),
        )
        return int(self.db.scalar(stmt) or 0)

    def has_history(self, location_id: int) -> bool:
        """Vrai si l'emplacement a été porté par un équipement (historique)."""
        stmt = select(func.count(EquipmentLocation.id)).where(
            EquipmentLocation.location_id == location_id
        )
        return int(self.db.scalar(stmt) or 0) > 0

    def add(self, location: Location) -> Location:
        self.db.add(location)
        self.db.commit()
        self.db.refresh(location)
        return location

    def save(self, location: Location) -> Location:
        self.db.commit()
        self.db.refresh(location)
        return location

    def delete(self, location: Location) -> None:
        self.db.delete(location)
        self.db.commit()
