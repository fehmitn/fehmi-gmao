"""Tests de l'inventaire : pièces de rechange et équipements de maintenance."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.errors import ConflictError, ValidationError
from app.models.enums import (
    CalibrationResult,
    CalibrationStatus,
    MaintenanceIntervalUnit,
    StockMovementType,
    ToolStatus,
)
from app.schemas.maintenance_tool import (
    CalibrationCreate,
    MaintenanceToolCreate,
    ToolUsageCreate,
    ToolUsageReturn,
)
from app.schemas.spare_part import (
    SparePartCreate,
    SparePartUpdate,
    StockMovementCreate,
)
from app.services.maintenance_tool_service import MaintenanceToolService
from app.services.spare_part_service import SparePartService
from tests.conftest import REFERENCE_DATE


def _part_payload(**overrides) -> SparePartCreate:
    data = {
        "code": "PR-ROUL-6205",
        "name": "Roulement 6205 2RS",
        "category": "Roulement",
        "unit": "pièce",
        "quantity": Decimal("10"),
        "min_quantity": Decimal("5"),
        "unit_cost": Decimal("12.50"),
    }
    data.update(overrides)
    return SparePartCreate(**data)


def _tool_payload(**overrides) -> MaintenanceToolCreate:
    data = {
        "code": "OUT-PIED-01",
        "name": "Pied à coulisse numérique",
        "category": "Instrument de mesure",
        "requires_calibration": True,
        "calibration_interval_value": 6,
        "calibration_interval_unit": MaintenanceIntervalUnit.MONTHS,
    }
    data.update(overrides)
    return MaintenanceToolCreate(**data)


def test_mouvements_de_stock_et_alertes(db, admin, site):
    service = SparePartService(db)
    part = service.create(_part_payload(), actor=admin)

    part = service.get(part.id)
    assert part.quantity == Decimal("10")
    assert part.movement_count == 1
    initial = service.movements(part.id)[0]
    assert initial.movement_type == StockMovementType.ENTRY.value
    assert initial.reference == "Stock initial"
    assert initial.resulting_quantity == Decimal("10")

    exit_movement = service.record_movement(
        part,
        StockMovementCreate(
            movement_type=StockMovementType.EXIT,
            quantity=Decimal("3"),
            reference="Bon de sortie 42",
        ),
        actor=admin,
    )
    assert exit_movement.quantity_delta == Decimal("-3")
    assert exit_movement.resulting_quantity == Decimal("7")
    assert service.get(part.id).quantity == Decimal("7")

    service.record_movement(
        service.get(part.id),
        StockMovementCreate(
            movement_type=StockMovementType.INVENTORY,
            quantity=Decimal("2"),
            notes="Inventaire physique",
        ),
        actor=admin,
    )
    refreshed = service.get(part.id)
    assert refreshed.quantity == Decimal("2")
    assert refreshed.is_low_stock is True
    assert refreshed.stock_status_label == "Sous le seuil"
    assert service.summary()["low_stock"] == 1

    with pytest.raises(ConflictError):
        service.record_movement(
            refreshed,
            StockMovementCreate(
                movement_type=StockMovementType.EXIT,
                quantity=Decimal("10"),
            ),
            actor=admin,
        )

    with pytest.raises(ConflictError):
        service.delete(service.get(part.id), actor=admin)

    assert len(service.movements(part.id)) == 3


def test_mouvement_futur_refuse_et_mise_a_jour_sans_stock_direct(db, admin, site):
    service = SparePartService(db)
    part = service.create(_part_payload(), actor=admin)

    with pytest.raises(ValidationError):
        service.record_movement(
            part,
            StockMovementCreate(
                movement_type=StockMovementType.ENTRY,
                quantity=Decimal("1"),
                movement_date=REFERENCE_DATE + timedelta(days=1),
            ),
            actor=admin,
        )

    updated = service.update(
        part,
        SparePartUpdate(name="Roulement 6205 étanche", min_quantity=Decimal("3")),
        actor=admin,
    )
    assert updated.name == "Roulement 6205 étanche"
    assert updated.quantity == Decimal("10")
    assert updated.min_quantity == Decimal("3")


def test_piece_sans_historique_supprimable(db, admin, site):
    service = SparePartService(db)
    part = service.create(_part_payload(quantity=Decimal("0")), actor=admin)
    assert part.movement_count == 0

    service.delete(part, actor=admin)

    assert db.get(type(part), part.id) is None


def test_etalonnage_periodique_et_blocage_du_pret(db, admin, site):
    service = MaintenanceToolService(db)
    tool = service.create(
        _tool_payload(last_calibration_date=REFERENCE_DATE - timedelta(days=100)),
        actor=admin,
    )

    assert tool.next_calibration_date == date(2026, 9, 7)
    assert tool.calibration_status is CalibrationStatus.VALID

    usage = service.start_usage(
        tool,
        ToolUsageCreate(
            used_by_id=admin.id,
            started_on=REFERENCE_DATE,
            notes="Contrôle dimensionnel",
        ),
        actor=admin,
    )
    assert usage.is_open is True
    assert service.get(tool.id).status == ToolStatus.IN_USE.value

    with pytest.raises(ConflictError):
        service.start_usage(
            service.get(tool.id),
            ToolUsageCreate(used_by_id=admin.id),
            actor=admin,
        )

    service.end_usage(
        service.get(tool.id),
        usage,
        ToolUsageReturn(ended_on=REFERENCE_DATE, return_notes="Rangé au coffre"),
        actor=admin,
    )
    refreshed = service.get(tool.id)
    assert refreshed.status == ToolStatus.AVAILABLE.value
    assert refreshed.open_usage is None

    service.add_calibration(
        refreshed,
        CalibrationCreate(
            calibrated_on=REFERENCE_DATE - timedelta(days=200),
            result=CalibrationResult.PASSED,
        ),
        actor=admin,
    )
    overdue = service.get(tool.id)
    assert overdue.calibration_status is CalibrationStatus.OVERDUE
    with pytest.raises(ConflictError, match="Étalonnage en retard"):
        service.start_usage(overdue, ToolUsageCreate(used_by_id=admin.id), actor=admin)


def test_outil_sans_etalonnage_ou_non_conforme_est_bloque(db, admin, site, client):
    service = MaintenanceToolService(db)

    missing = service.create(_tool_payload(code="OUT-CAL-01"), actor=admin)
    assert missing.calibration_status is CalibrationStatus.MISSING
    with pytest.raises(ConflictError, match="Aucun étalonnage"):
        service.start_usage(missing, ToolUsageCreate(used_by_id=admin.id), actor=admin)
    assert client.get(f"/maintenance-tools/{missing.id}").status_code == 200

    failed = service.create(
        _tool_payload(
            code="OUT-CAL-02",
            last_calibration_date=REFERENCE_DATE - timedelta(days=30),
        ),
        actor=admin,
    )
    service.add_calibration(
        failed,
        CalibrationCreate(
            calibrated_on=REFERENCE_DATE,
            result=CalibrationResult.FAILED,
            notes="Dérive hors tolérance",
        ),
        actor=admin,
    )
    failed = service.get(failed.id)
    assert failed.status == ToolStatus.OUT_OF_SERVICE.value
    assert failed.checkout_block_reason is not None
    with pytest.raises(ConflictError):
        service.start_usage(failed, ToolUsageCreate(used_by_id=admin.id), actor=admin)
    assert client.get(f"/maintenance-tools/{failed.id}").status_code == 200


def test_periodicite_etalonnage_calendaire_obligatoire(db, admin, site):
    service = MaintenanceToolService(db)

    with pytest.raises(ValidationError, match="calendaire"):
        service.create(
            _tool_payload(
                code="OUT-HEURES",
                calibration_interval_value=500,
                calibration_interval_unit=MaintenanceIntervalUnit.HOURS,
            ),
            actor=admin,
        )

    with pytest.raises(ValidationError, match="périodicité"):
        service.create(
            _tool_payload(code="OUT-SANS-PERIODE", calibration_interval_value=None),
            actor=admin,
        )

    with pytest.raises(ValidationError, match="prêt"):
        service.create(
            _tool_payload(code="OUT-DEJA-PRETE", status=ToolStatus.IN_USE),
            actor=admin,
        )


def test_calibration_calcule_la_prochaine_echeance_et_refuse_la_suppression(db, admin, site):
    service = MaintenanceToolService(db)
    tool = service.create(_tool_payload(code="OUT-CAL-03"), actor=admin)

    calibration = service.add_calibration(
        tool,
        CalibrationCreate(
            calibrated_on=REFERENCE_DATE,
            certificate_number="CERT-2026-001",
            cost=Decimal("120"),
        ),
        actor=admin,
    )
    assert calibration.next_due_date == date(2026, 12, 15)
    refreshed = service.get(tool.id)
    assert refreshed.last_calibration_date == REFERENCE_DATE
    assert refreshed.next_calibration_date == date(2026, 12, 15)
    assert refreshed.calibration_status is CalibrationStatus.VALID

    with pytest.raises(ConflictError):
        service.delete(refreshed, actor=admin)


def test_api_inventaire_et_pages_web(client, db, admin, site):
    part = SparePartService(db).create(_part_payload(), actor=admin)
    tool = MaintenanceToolService(db).create(
        _tool_payload(last_calibration_date=REFERENCE_DATE - timedelta(days=100)),
        actor=admin,
    )

    response = client.get("/api/spare-parts")
    assert response.status_code == 200
    assert response.json()[0]["code"] == "PR-ROUL-6205"

    response = client.get("/api/spare-parts/summary")
    assert response.status_code == 200
    assert response.json()["total"] == 1

    response = client.post(
        f"/api/spare-parts/{part.id}/movements",
        json={"movement_type": "exit", "quantity": 2, "reference": "OT-001"},
    )
    assert response.status_code == 201
    assert response.json()["movement_type"] == "exit"

    response = client.get("/api/maintenance-tools")
    assert response.status_code == 200
    payload = response.json()[0]
    assert payload["code"] == "OUT-PIED-01"
    assert payload["calibration_status"] == "valid"

    response = client.post(
        f"/api/maintenance-tools/{tool.id}/calibrations",
        json={"calibrated_on": REFERENCE_DATE.isoformat(), "result": "passed"},
    )
    assert response.status_code == 201
    assert response.json()["next_due_date"] == "2026-12-15"

    response = client.post(
        f"/api/maintenance-tools/{tool.id}/usages",
        json={"used_by_id": admin.id, "started_on": REFERENCE_DATE.isoformat()},
    )
    assert response.status_code == 201
    usage_id = response.json()["id"]
    assert client.get(f"/maintenance-tools/{tool.id}").status_code == 200

    response = client.post(
        f"/api/maintenance-tools/{tool.id}/usages/{usage_id}/return",
        json={"ended_on": REFERENCE_DATE.isoformat()},
    )
    assert response.status_code == 200
    assert response.json()["ended_on"] == REFERENCE_DATE.isoformat()

    for path in (
        "/",
        "/spare-parts",
        "/spare-parts/new",
        f"/spare-parts/{part.id}",
        f"/spare-parts/{part.id}/edit",
        "/maintenance-tools",
        "/maintenance-tools/new",
        f"/maintenance-tools/{tool.id}",
        f"/maintenance-tools/{tool.id}/edit",
    ):
        response = client.get(path)
        assert response.status_code == 200, path

    assert "Historique des mouvements" in client.get(f"/spare-parts/{part.id}").text
    assert "Fiche d'utilisation" in client.get(f"/maintenance-tools/{tool.id}").text


def test_formulaires_web_inventaire(client, db, admin, site):
    response = client.post(
        "/spare-parts",
        data={
            "code": "PR-WEB-01",
            "name": "Filtre à huile",
            "quantity": "3",
            "min_quantity": "1",
            "is_active": "1",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    response = client.post(
        "/maintenance-tools",
        data={
            "code": "OUT-WEB-01",
            "name": "Micromètre",
            "requires_calibration": "1",
            "calibration_interval_value": "12",
            "calibration_interval_unit": "months",
            "is_active": "1",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    parts = SparePartService(db).list(search="PR-WEB-01")
    assert len(parts) == 1
    tools = MaintenanceToolService(db).list(search="OUT-WEB-01")
    assert len(tools) == 1
    assert tools[0].calibration_status is CalibrationStatus.MISSING
