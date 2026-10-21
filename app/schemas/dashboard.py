"""Schemas de la page d'accueil (tableau de bord)."""

from __future__ import annotations

from pydantic import BaseModel


class SiteSummary(BaseModel):
    site_id: int
    code: str
    name: str
    location_count: int
    equipment_count: int
    critical_count: int


class DashboardStats(BaseModel):
    site_count: int
    location_count: int
    equipment_count: int
    active_equipment_count: int
    critical_equipment_count: int
    backdated_placement_count: int
    unplaced_equipment_count: int
    equipment_by_status: dict[str, int]
    equipment_by_criticality: dict[str, int]
    sites: list[SiteSummary]
