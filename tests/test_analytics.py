"""Tests de l'analyse de maintenance (fiabilité, coûts et alertes)."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal

import pytest

from app.models.enums import StockMovementType, WorkOrderStatus
from app.models.spare_part import SparePart, StockMovement
from app.models.work_order import WorkOrder
from app.services.analytics_service import AnalyticsService, normalize_period
from tests.conftest import REFERENCE_DATE


def _work_order(
    db,
    equipment,
    code: str,
    *,
    is_corrective: bool = True,
    status: str = WorkOrderStatus.DONE.value,
    ended_days_ago: int | None = 1,
    duration_hours: float = 2,
    due_days_ago: int | None = None,
    assigned_to_id: int | None = None,
    created_days_ago: int = 10,
) -> WorkOrder:
    ended_at = (
        datetime.combine(REFERENCE_DATE - timedelta(days=ended_days_ago), time(12, 0))
        if ended_days_ago is not None
        else None
    )
    started_at = (
        ended_at - timedelta(hours=duration_hours) if ended_at is not None else None
    )
    work_order = WorkOrder(
        code=code,
        equipment_id=equipment.id,
        status=status,
        is_corrective=is_corrective,
        intervention_started_at=started_at,
        intervention_ended_at=ended_at,
        due_date=(
            REFERENCE_DATE - timedelta(days=due_days_ago)
            if due_days_ago is not None
            else None
        ),
        assigned_to_id=assigned_to_id,
        created_at=datetime.combine(
            REFERENCE_DATE - timedelta(days=created_days_ago), time(9, 0)
        ),
    )
    db.add(work_order)
    db.commit()
    db.refresh(work_order)
    return work_order


def _part(db, code: str = "PR-6205") -> SparePart:
    part = SparePart(
        code=code,
        name="Roulement 6205",
        unit="pièce",
        quantity=Decimal("10"),
        min_quantity=Decimal("1"),
        unit_cost=Decimal("10.00"),
    )
    db.add(part)
    db.commit()
    db.refresh(part)
    return part


def _movement(
    db,
    part: SparePart,
    work_order: WorkOrder,
    *,
    quantity: str = "2",
    unit_cost: str | None = "10.00",
) -> StockMovement:
    movement = StockMovement(
        spare_part_id=part.id,
        work_order_id=work_order.id,
        movement_type=StockMovementType.EXIT.value,
        quantity=Decimal(quantity),
        quantity_delta=-Decimal(quantity),
        resulting_quantity=Decimal("8"),
        movement_date=REFERENCE_DATE - timedelta(days=2),
        unit_cost=Decimal(unit_cost) if unit_cost is not None else None,
    )
    db.add(movement)
    db.commit()
    db.refresh(movement)
    return movement


def test_summary_computes_mtbf_mttr_and_availability(db, equipment):
    # Deux pannes terminées dans la fenêtre : 2 h puis 3 h d'arrêt.
    _work_order(db, equipment, "OT-2026-0001", ended_days_ago=10, duration_hours=2)
    _work_order(db, equipment, "OT-2026-0002", ended_days_ago=5, duration_hours=3)
    # Bruit qui ne doit pas compter : préventif, non terminé, hors fenêtre.
    _work_order(
        db, equipment, "OT-2026-0003", is_corrective=False, ended_days_ago=3
    )
    _work_order(
        db,
        equipment,
        "OT-2026-0004",
        status=WorkOrderStatus.IN_PROGRESS.value,
        ended_days_ago=2,
    )
    _work_order(db, equipment, "OT-2026-0005", ended_days_ago=200)

    summary = AnalyticsService(db).summary(days=30)

    assert summary.equipment_count == 1
    assert summary.total_failures == 2
    assert summary.total_downtime_minutes == 300
    row = summary.equipment[0]
    assert row.failure_count == 2
    assert row.mttr_minutes == pytest.approx(150)
    # Fenêtre de 30 jours = 43 200 minutes ; (43 200 - 300) / 2 = 21 450.
    assert row.mtbf_minutes == pytest.approx(21450)
    assert row.availability == pytest.approx(1 - 300 / 43200)
    assert summary.global_mttr_minutes == pytest.approx(150)
    assert summary.global_availability == pytest.approx(1 - 300 / 43200)
    assert row.mttr_label == "2 h 30 min"
    assert row.availability_label.endswith(" %")


def test_summary_without_failure_has_no_mtbf_nor_mttr(db, equipment):
    summary = AnalyticsService(db).summary(days=90)

    row = summary.equipment[0]
    assert row.failure_count == 0
    assert row.mttr_minutes is None
    assert row.mtbf_minutes is None
    assert row.availability == 1.0
    assert row.parts_cost == Decimal("0")
    assert row.mttr_label == "—"


def test_summary_aggregates_parts_cost_with_snapshot_and_fallback(db, equipment):
    work_order = _work_order(db, equipment, "OT-2026-0010")
    part = _part(db)
    # Coût figé au moment du mouvement : 2 × 7 = 14.
    _movement(db, part, work_order, quantity="2", unit_cost="7.00")
    # Mouvement historique sans coût : repli sur le prix courant 10 → 10.
    _movement(db, part, work_order, quantity="1", unit_cost=None)

    service = AnalyticsService(db)
    assert service.parts_cost(work_order.id) == Decimal("24.00")

    summary = service.summary(days=30)
    assert summary.total_parts_cost == Decimal("24.00")
    assert summary.equipment[0].parts_cost == Decimal("24.00")
    assert len(summary.cost_lines) == 1
    line = summary.cost_lines[0]
    assert line.code == "OT-2026-0010"
    assert line.parts_cost == Decimal("24.00")
    assert line.kind_label == "Corrective"


def test_parts_cost_ignores_entries_and_other_work_orders(db, equipment):
    work_order = _work_order(db, equipment, "OT-2026-0011")
    other = _work_order(db, equipment, "OT-2026-0012")
    part = _part(db)
    _movement(db, part, work_order, quantity="2", unit_cost="5.00")
    _movement(db, part, other, quantity="4", unit_cost="5.00")
    entry = StockMovement(
        spare_part_id=part.id,
        work_order_id=work_order.id,
        movement_type=StockMovementType.ENTRY.value,
        quantity=Decimal("10"),
        quantity_delta=Decimal("10"),
        resulting_quantity=Decimal("20"),
        movement_date=REFERENCE_DATE,
        unit_cost=Decimal("5.00"),
    )
    db.add(entry)
    db.commit()

    assert AnalyticsService(db).parts_cost(work_order.id) == Decimal("10.00")


def test_recurrent_failures_threshold(db, equipment, ancien_equipement):
    for index in range(3):
        _work_order(
            db,
            equipment,
            f"OT-2026-10{index}",
            ended_days_ago=30 * (index + 1),
        )
    for index in range(2):
        _work_order(
            db,
            ancien_equipement,
            f"OT-2026-20{index}",
            ended_days_ago=40 * (index + 1),
        )

    summary = AnalyticsService(db).summary(days=365)
    rows = {row.equipment_code: row for row in summary.equipment}

    assert rows["PMP-001"].failure_count_12m == 3
    assert rows["PMP-001"].recurrent is True
    assert "Pannes récurrentes" in rows["PMP-001"].recurrent_label
    assert rows["PMP-OLD"].failure_count_12m == 2
    assert rows["PMP-OLD"].recurrent is False
    assert rows["PMP-OLD"].recurrent_label == ""


def test_alerts_detect_unassigned_requests_and_overdue_work_orders(
    db, equipment, admin
):
    _work_order(
        db,
        equipment,
        "OT-2026-3001",
        created_days_ago=5,
        ended_days_ago=None,
        status=WorkOrderStatus.OPEN.value,
    )
    # Récente : pas encore en alerte.
    _work_order(
        db,
        equipment,
        "OT-2026-3002",
        created_days_ago=1,
        ended_days_ago=None,
        status=WorkOrderStatus.OPEN.value,
    )
    # Affectée : sort du bloc « non affectées ».
    _work_order(
        db,
        equipment,
        "OT-2026-3003",
        created_days_ago=10,
        ended_days_ago=None,
        status=WorkOrderStatus.OPEN.value,
        assigned_to_id=admin.id,
    )

    _work_order(
        db,
        equipment,
        "OT-2026-3004",
        is_corrective=False,
        status=WorkOrderStatus.OPEN.value,
        ended_days_ago=None,
        due_days_ago=4,
    )
    _work_order(
        db,
        equipment,
        "OT-2026-3005",
        is_corrective=False,
        status=WorkOrderStatus.DONE.value,
        due_days_ago=8,
    )

    alerts = AnalyticsService(db).alerts(threshold_days=3)

    assert [alert.code for alert in alerts.unassigned] == ["OT-2026-3001"]
    assert alerts.unassigned[0].age_days == 5
    assert alerts.unassigned[0].age_label == "5 j"
    assert [alert.code for alert in alerts.overdue_work_orders] == ["OT-2026-3004"]
    assert alerts.overdue_work_orders[0].days_late == 4
    assert alerts.total_count == 2


def test_alerts_limit_is_applied(db, equipment):
    for index in range(5):
        _work_order(
            db,
            equipment,
            f"OT-2026-40{index}",
            created_days_ago=10 + index,
            ended_days_ago=None,
            status=WorkOrderStatus.OPEN.value,
        )

    alerts = AnalyticsService(db).alerts(threshold_days=3, limit=2)
    assert len(alerts.unassigned) == 2


def test_normalize_period_keeps_supported_values():
    assert normalize_period(30) == 30
    assert normalize_period(90) == 90
    assert normalize_period(365) == 365
    assert normalize_period(7) == 365
    assert normalize_period(None) == 365


def test_analytics_api_endpoints(client, db, equipment):
    _work_order(db, equipment, "OT-2026-5001", ended_days_ago=2)

    kpis = client.get("/api/analytics/kpis", params={"days": 30})
    assert kpis.status_code == 200
    payload = kpis.json()
    assert payload["total_failures"] == 1
    assert payload["equipment"][0]["equipment_code"] == "PMP-001"

    costs = client.get("/api/analytics/costs", params={"days": 30})
    assert costs.status_code == 200
    assert "cost_lines" in costs.json()

    alerts = client.get("/api/analytics/alerts")
    assert alerts.status_code == 200
    assert alerts.json()["threshold_days"] == 3


def test_analytics_web_page_and_equipment_badge(client, db, equipment):
    for index in range(3):
        _work_order(
            db,
            equipment,
            f"OT-2026-60{index}",
            ended_days_ago=20 * (index + 1),
        )

    page = client.get("/analytics", params={"days": 365})
    assert page.status_code == 200
    assert "Analyse de maintenance" in page.text
    assert "PMP-001" in page.text
    assert "Pannes récurrentes" in page.text

    detail = client.get(f"/equipments/{equipment.id}")
    assert detail.status_code == 200
    assert "Pannes récurrentes" in detail.text
    assert "MTTR" in detail.text
