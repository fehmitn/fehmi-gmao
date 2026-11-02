"""Routes API de l'analyse de maintenance."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.analytics import AnalyticsSummary, DashboardAlerts
from app.services.analytics_service import AnalyticsService, DEFAULT_PERIOD

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/kpis", response_model=AnalyticsSummary)
def analytics_kpis(
    days: int = Query(DEFAULT_PERIOD, ge=1, le=3650),
    site_id: int | None = None,
    db: Session = Depends(get_db),
) -> AnalyticsSummary:
    """MTBF, MTTR, disponibilité et coûts par équipement."""
    return AnalyticsService(db).summary(days=days, site_id=site_id)


@router.get("/costs", response_model=AnalyticsSummary)
def analytics_costs(
    days: int = Query(DEFAULT_PERIOD, ge=1, le=3650),
    site_id: int | None = None,
    db: Session = Depends(get_db),
) -> AnalyticsSummary:
    """Détail des coûts de pièces par ordre de travail."""
    return AnalyticsService(db).summary(days=days, site_id=site_id)


@router.get("/alerts", response_model=DashboardAlerts)
def analytics_alerts(
    threshold_days: int = Query(3, ge=0, le=365),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
) -> DashboardAlerts:
    """Demandes correctives non affectées et OT préventifs en retard."""
    return AnalyticsService(db).alerts(threshold_days=threshold_days, limit=limit)
