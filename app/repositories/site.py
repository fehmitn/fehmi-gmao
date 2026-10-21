from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.site import Site


class SiteRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, site_id: int) -> Site | None:
        return self.db.get(Site, site_id)

    def get_by_code(self, code: str) -> Site | None:
        stmt = select(Site).where(Site.code == code)
        return self.db.scalars(stmt).first()

    def list_all(self, active_only: bool = False) -> list[Site]:
        stmt = select(Site).order_by(Site.name)
        if active_only:
            stmt = stmt.where(Site.is_active.is_(True))
        return list(self.db.scalars(stmt).all())

    def add(self, site: Site) -> Site:
        self.db.add(site)
        self.db.commit()
        self.db.refresh(site)
        return site

    def save(self, site: Site) -> Site:
        self.db.commit()
        self.db.refresh(site)
        return site

    def delete(self, site: Site) -> None:
        self.db.delete(site)
        self.db.commit()
