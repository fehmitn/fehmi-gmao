"""Service du tableau de bord."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.equipment import Equipment
from app.models.equipment_location import EquipmentLocation
from app.models.location import Location
from app.models.site import Site
from app.repositories.base import Page
from app.schemas.dashboard import DashboardStats, SiteSummary


class DashboardService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def stats(self) -> DashboardStats:
        site_count = int(self.db.scalar(select(func.count(Site.id))) or 0)
        location_count = int(self.db.scalar(select(func.count(Location.id))) or 0)
        equipment_count = int(self.db.scalar(select(func.count(Equipment.id))) or 0)

        active_count = int(
            self.db.scalar(
                select(func.count(Equipment.id)).where(Equipment.is_active.is_(True))
            )
            or 0
        )
        critical_count = int(
            self.db.scalar(
                select(func.count(Equipment.id)).where(Equipment.is_critical.is_(True))
            )
            or 0
        )
        backdated_count = int(
            self.db.scalar(
                select(func.count(EquipmentLocation.id)).where(
                    EquipmentLocation.entry_delay_days.is_not(None)
                )
            )
            or 0
        )
        unplaced_count = int(
            self.db.scalar(
                select(func.count(Equipment.id)).where(
                    ~Equipment.id.in_(
                        select(EquipmentLocation.equipment_id).where(
                            EquipmentLocation.effective_to.is_(None)
                        )
                    )
                )
            )
            or 0
        )

        by_status = {
            status: int(count)
            for status, count in self.db.execute(
                select(Equipment.status, func.count(Equipment.id)).group_by(
                    Equipment.status
                )
            ).all()
        }
        by_criticality = {
            criticality: int(count)
            for criticality, count in self.db.execute(
                select(Equipment.criticality, func.count(Equipment.id))
                .where(Equipment.criticality.is_not(None))
                .group_by(Equipment.criticality)
            ).all()
        }

        sites: list[SiteSummary] = []
        for site in self.db.scalars(select(Site).order_by(Site.name)).all():
            site_equipment = int(
                self.db.scalar(
                    select(func.count(Equipment.id)).where(Equipment.site_id == site.id)
                )
                or 0
            )
            site_locations = int(
                self.db.scalar(
                    select(func.count(Location.id)).where(Location.site_id == site.id)
                )
                or 0
            )
            site_critical = int(
                self.db.scalar(
                    select(func.count(Equipment.id)).where(
                        Equipment.site_id == site.id,
                        Equipment.is_critical.is_(True),
                    )
                )
                or 0
            )
            sites.append(
                SiteSummary(
                    site_id=site.id,
                    code=site.code,
                    name=site.name,
                    location_count=site_locations,
                    equipment_count=site_equipment,
                    critical_count=site_critical,
                )
            )

        return DashboardStats(
            site_count=site_count,
            location_count=location_count,
            equipment_count=equipment_count,
            active_equipment_count=active_count,
            critical_equipment_count=critical_count,
            backdated_placement_count=backdated_count,
            unplaced_equipment_count=unplaced_count,
            equipment_by_status=by_status,
            equipment_by_criticality=by_criticality,
            sites=sites,
        )

    def recent_backdates(self, limit: int = 10) -> Page[EquipmentLocation]:
        stmt = (
            select(EquipmentLocation)
            .where(EquipmentLocation.entry_delay_days.is_not(None))
            .order_by(EquipmentLocation.entry_delay_days.desc(), EquipmentLocation.id.desc())
            .limit(limit)
        )
        items = list(self.db.scalars(stmt).all())
        return Page(items=items, total=len(items), page=1, size=limit)
