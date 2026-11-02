"""Maintenance périodique portée par les familles d'équipements.

Couvre le référentiel fournisseurs, l'unicité des règles par famille, la
validation de l'ancrage, la saisie des réalisations d'OT (écart, refus du
futur, règle inactive / hors famille) et les statuts de l'échéancier.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.errors import (
    ConflictError,
    FutureDateNotAllowed,
    NotFoundError,
    ValidationError,
)
from app.models.audit import AuditLog
from app.models.enums import (
    AuditAction,
    MaintenanceAnchor,
    MaintenanceIntervalUnit,
    MaintenanceType,
)
from app.schemas.equipment import EquipmentUpdate
from app.schemas.equipment_type import EquipmentTypeCreate
from app.schemas.maintenance_execution import MaintenanceExecutionCreate
from app.schemas.maintenance_supplier import (
    MaintenanceSupplierCreate,
    MaintenanceSupplierUpdate,
)
from app.schemas.periodic_maintenance import (
    PeriodicMaintenanceCreate,
    PeriodicMaintenanceUpdate,
)
from app.services.equipment_service import EquipmentService
from app.services.equipment_type_service import EquipmentTypeService
from app.services.maintenance_execution_service import MaintenanceExecutionService
from app.services.maintenance_schedule_service import MaintenanceScheduleService
from app.services.maintenance_supplier_service import MaintenanceSupplierService
from app.services.periodic_maintenance_service import PeriodicMaintenanceService
from tests.conftest import REFERENCE_DATE


def _supplier(db, admin, code="SUP-MECA", name="Mécanique industrielle"):
    return MaintenanceSupplierService(db).create(
        MaintenanceSupplierCreate(code=code, name=name),
        actor=admin,
    )


def _rule(
    db,
    admin,
    equipment_type,
    *,
    code="GRAISSAGE",
    label="Graissage des paliers",
    interval_value=1,
    interval_unit=MaintenanceIntervalUnit.MONTHS,
    maintenance_type=MaintenanceType.PREVENTIVE_SYSTEMATIC,
    anchor=MaintenanceAnchor.COMMISSIONING,
    fixed_date=None,
    supplier_id=None,
    tolerance_days=0,
    is_active=True,
):
    return PeriodicMaintenanceService(db).create(
        equipment_type.id,
        PeriodicMaintenanceCreate(
            code=code,
            label=label,
            interval_value=interval_value,
            interval_unit=interval_unit,
            maintenance_type=maintenance_type,
            anchor=anchor,
            fixed_date=fixed_date,
            supplier_id=supplier_id,
            tolerance_days=tolerance_days,
            is_active=is_active,
        ),
        actor=admin,
    )


def _set_commissioning(db, equipment, value):
    service = EquipmentService(db)
    return service.update(
        service.get(equipment.id),
        EquipmentUpdate(commissioning_date=value),
        actor=None,
    )


def _set_hours(db, equipment, *, current, initial=0):
    service = EquipmentService(db)
    return service.update(
        service.get(equipment.id),
        EquipmentUpdate(
            operating_hours=current,
            initial_operating_hours=initial,
        ),
        actor=None,
    )


def _execute(
    db,
    equipment,
    rule,
    performed_on,
    admin,
    notes=None,
    operating_hours=None,
):
    return MaintenanceExecutionService(db).create(
        equipment,
        rule,
        MaintenanceExecutionCreate(
            periodic_maintenance_id=rule.id,
            performed_on=performed_on,
            notes=notes,
            operating_hours=operating_hours,
        ),
        actor=admin,
    )


# --------------------------------------------------------------- fournisseurs
def test_fournisseur_cree_et_compte_dans_les_regles(db, admin, equipment_type):
    supplier = _supplier(db, admin)
    assert supplier.periodic_maintenance_count == 0

    _rule(db, admin, equipment_type, supplier_id=supplier.id)
    supplier = MaintenanceSupplierService(db).get(supplier.id)

    assert supplier.periodic_maintenance_count == 1
    assert MaintenanceSupplierService(db).list()[0].code == "SUP-MECA"


def test_fournisseur_code_unique(db, admin):
    _supplier(db, admin)

    with pytest.raises(ConflictError):
        _supplier(db, admin)


def test_suppression_fournisseur_refusee_s_il_est_utilise(db, admin, equipment_type):
    supplier = _supplier(db, admin)
    _rule(db, admin, equipment_type, supplier_id=supplier.id)
    service = MaintenanceSupplierService(db)

    with pytest.raises(ConflictError):
        service.delete(service.get(supplier.id), actor=admin)

    assert service.get(supplier.id).code == "SUP-MECA"


def test_suppression_fournisseur_libre(db, admin):
    supplier = _supplier(db, admin)
    service = MaintenanceSupplierService(db)

    service.delete(service.get(supplier.id), actor=admin)

    with pytest.raises(NotFoundError):
        service.get(supplier.id)


def test_mise_a_jour_fournisseur(db, admin):
    supplier = _supplier(db, admin)
    service = MaintenanceSupplierService(db)

    updated = service.update(
        service.get(supplier.id),
        MaintenanceSupplierUpdate(name="Nouveau nom", is_active=False),
        actor=admin,
    )

    assert updated.name == "Nouveau nom"
    assert updated.is_active is False
    assert service.list(active_only=True) == []


# ---------------------------------------------------------------------- règles
def test_code_de_regle_unique_par_famille_mais_reutilisable_ailleurs(
    db, admin, equipment_type
):
    _rule(db, admin, equipment_type)

    with pytest.raises(ConflictError):
        _rule(db, admin, equipment_type)

    autre_famille = EquipmentTypeService(db).create(
        EquipmentTypeCreate(code="MOT-AS", name="Moteur", category="Moteurs"),
        actor=admin,
    )
    regle = _rule(db, admin, autre_famille)

    assert regle.code == "GRAISSAGE"


def test_ancrage_date_fixe_exige_une_date(db, admin, equipment_type):
    with pytest.raises(ValidationError):
        _rule(
            db,
            admin,
            equipment_type,
            anchor=MaintenanceAnchor.FIXED_DATE,
            fixed_date=None,
        )


def test_date_fixe_ignoree_si_l_ancrage_n_est_pas_une_date_fixe(
    db, admin, equipment_type
):
    regle = _rule(
        db,
        admin,
        equipment_type,
        anchor=MaintenanceAnchor.COMMISSIONING,
        fixed_date=date(2026, 1, 1),
    )

    assert regle.fixed_date is None


def test_mise_a_jour_regle_et_libelles(db, admin, equipment_type):
    regle = _rule(db, admin, equipment_type, interval_value=3)
    service = PeriodicMaintenanceService(db)

    assert regle.periodicity_label == "tous les 3 mois"

    regle = service.update(
        service.get(regle.id),
        PeriodicMaintenanceUpdate(
            label="Graissage complet",
            interval_unit=MaintenanceIntervalUnit.WEEKS,
            interval_value=2,
        ),
        actor=admin,
    )

    assert regle.label == "Graissage complet"
    assert regle.periodicity_label == "tous les 2 semaines"
    assert regle.interval_unit_label == "semaine(s)"


def test_suppression_regle_refusee_si_des_realisations_existent(
    db, admin, equipment, equipment_type
):
    equipment = _set_commissioning(db, equipment, date(2026, 1, 31))
    regle = _rule(db, admin, equipment_type)
    _execute(db, equipment, regle, date(2026, 6, 5), admin)
    service = PeriodicMaintenanceService(db)

    with pytest.raises(ConflictError):
        service.delete(service.get(regle.id), actor=admin)


def test_suppression_regle_sans_realisation(db, admin, equipment_type):
    regle = _rule(db, admin, equipment_type)
    service = PeriodicMaintenanceService(db)

    service.delete(service.get(regle.id), actor=admin)

    with pytest.raises(NotFoundError):
        service.get(regle.id)


# ---------------------------------------------------------------- réalisations
def test_realisation_loggue_le_retard_par_rapport_a_l_echeance(db, admin, equipment, equipment_type):
    equipment = _set_commissioning(db, equipment, date(2026, 1, 31))
    regle = _rule(db, admin, equipment_type)

    execution = _execute(db, equipment, regle, date(2026, 6, 5), admin)

    assert execution.theoretical_due_date == date(2026, 5, 31)
    assert execution.delay_days == 5
    assert execution.delay_label == "5 j de retard"
    assert execution.delay_css == "text-bg-danger"
    assert execution.performed_by_id == admin.id
    assert execution.maintenance_code == "GRAISSAGE"

    audit = db.scalars(
        select(AuditLog).where(AuditLog.action == AuditAction.EXECUTE.value)
    ).all()
    assert len(audit) == 1
    assert audit[0].entity_type == "maintenance_execution"


def test_realisation_en_avance_loggue_un_ecart_negatif(db, admin, equipment, equipment_type):
    equipment = _set_commissioning(db, equipment, date(2026, 6, 1))
    regle = _rule(
        db,
        admin,
        equipment_type,
        interval_value=10,
        interval_unit=MaintenanceIntervalUnit.DAYS,
    )

    execution = _execute(db, equipment, regle, date(2026, 6, 9), admin)

    assert execution.theoretical_due_date == date(2026, 6, 11)
    assert execution.delay_days == -2
    assert execution.delay_label == "2 j d'avance"
    assert execution.delay_css == "text-bg-info"


def test_realisation_future_refusee(db, admin, equipment, equipment_type):
    equipment = _set_commissioning(db, equipment, date(2026, 1, 31))
    regle = _rule(db, admin, equipment_type)

    with pytest.raises(FutureDateNotAllowed):
        _execute(db, equipment, regle, REFERENCE_DATE + timedelta(days=1), admin)


def test_realisation_refusee_si_regle_inactive(db, admin, equipment, equipment_type):
    equipment = _set_commissioning(db, equipment, date(2026, 1, 31))
    regle = _rule(db, admin, equipment_type, is_active=False)

    with pytest.raises(ValidationError):
        _execute(db, equipment, regle, date(2026, 6, 5), admin)


def test_realisation_refusee_si_regle_d_une_autre_famille(db, admin, equipment, equipment_type):
    equipment = _set_commissioning(db, equipment, date(2026, 1, 31))
    autre_famille = EquipmentTypeService(db).create(
        EquipmentTypeCreate(code="MOT-AS", name="Moteur", category="Moteurs"),
        actor=admin,
    )
    regle = _rule(db, admin, autre_famille)

    with pytest.raises(ValidationError):
        _execute(db, equipment, regle, date(2026, 6, 5), admin)


def test_realisation_refusee_sans_ancrage(db, admin, equipment, equipment_type):
    regle = _rule(db, admin, equipment_type)

    # L'équipement de test n'a pas de date de mise en service.
    with pytest.raises(ValidationError):
        _execute(db, equipment, regle, date(2026, 6, 5), admin)


# ------------------------------------------------------------------- échéancier
def test_echeancier_marque_en_retard_une_echeance_non_couverte(
    db, admin, equipment, equipment_type
):
    equipment = _set_commissioning(db, equipment, date(2026, 1, 31))
    _rule(db, admin, equipment_type)

    rows = MaintenanceScheduleService(db).rows(equipment_id=equipment.id)

    assert len(rows) == 1
    row = rows[0]
    assert row.status == "overdue"
    assert row.previous_due_date == date(2026, 5, 31)
    assert row.due_date == date(2026, 5, 31)
    assert row.days_remaining == -15
    assert row.status_label == "En retard"


def test_echeancier_tolerance_evite_le_statut_en_retard(
    db, admin, equipment, equipment_type
):
    equipment = _set_commissioning(db, equipment, date(2026, 1, 31))
    _rule(db, admin, equipment_type, tolerance_days=20)

    row = MaintenanceScheduleService(db).rows(equipment_id=equipment.id)[0]

    assert row.status == "due_soon"
    assert row.status_label == "Dans la tolérance"
    assert row.days_remaining == -15


def test_echeancier_une_realisation_couvre_l_echeance_precedente(
    db, admin, equipment, equipment_type
):
    equipment = _set_commissioning(db, equipment, date(2026, 1, 31))
    regle = _rule(db, admin, equipment_type)
    _execute(db, equipment, regle, date(2026, 6, 5), admin)

    row = MaintenanceScheduleService(db).rows(equipment_id=equipment.id)[0]

    assert row.status == "due_soon"
    assert row.due_date == date(2026, 6, 30)
    assert row.days_remaining == 15
    assert row.last_performed_on == date(2026, 6, 5)
    assert row.last_delay_days == 5


def test_echeancier_signale_un_ancrage_indisponible(db, equipment, equipment_type, admin):
    _rule(db, admin, equipment_type)

    row = MaintenanceScheduleService(db).rows(equipment_id=equipment.id)[0]

    assert row.status == "no_anchor"
    assert row.due_date is None
    assert row.days_remaining is None


def test_echeancier_date_fixe(db, admin, equipment, equipment_type):
    _rule(
        db,
        admin,
        equipment_type,
        anchor=MaintenanceAnchor.FIXED_DATE,
        fixed_date=REFERENCE_DATE - timedelta(days=45),
        interval_value=1,
        interval_unit=MaintenanceIntervalUnit.YEARS,
    )

    row = MaintenanceScheduleService(db).rows(equipment_id=equipment.id)[0]

    assert row.anchor_date == REFERENCE_DATE - timedelta(days=45)
    assert row.status == "overdue"
    assert row.days_remaining == -45


def test_resume_de_l_echeancier(db, admin, equipment, equipment_type):
    equipment = _set_commissioning(db, equipment, date(2026, 3, 1))
    _rule(db, admin, equipment_type, code="EN-RETARD")
    _rule(
        db,
        admin,
        equipment_type,
        code="A-VENIR",
        anchor=MaintenanceAnchor.FIXED_DATE,
        fixed_date=REFERENCE_DATE + timedelta(days=16),
        interval_value=1,
        interval_unit=MaintenanceIntervalUnit.YEARS,
    )

    summary = MaintenanceScheduleService(db).summary(equipment_type_id=equipment_type.id)

    assert summary.total == 2
    assert summary.overdue_count == 1
    assert summary.due_soon_count == 1
    assert summary.no_anchor_count == 0


# ------------------------------------------------------- heures de fonctionnement
def test_regle_en_heures_force_l_ancrage_mise_en_service(db, admin, equipment_type):
    regle = _rule(
        db,
        admin,
        equipment_type,
        interval_value=500,
        interval_unit=MaintenanceIntervalUnit.HOURS,
        anchor=MaintenanceAnchor.FIXED_DATE,
        fixed_date=date(2026, 1, 1),
    )

    assert regle.interval_unit == MaintenanceIntervalUnit.HOURS.value
    assert regle.anchor == MaintenanceAnchor.COMMISSIONING.value
    assert regle.fixed_date is None
    assert regle.periodicity_label == "toutes les 500 heures de fonctionnement"


def test_echeancier_heures_en_attente_du_seuil(db, admin, equipment, equipment_type):
    _set_hours(db, equipment, current=412)
    _rule(
        db,
        admin,
        equipment_type,
        interval_value=250,
        interval_unit=MaintenanceIntervalUnit.HOURS,
    )

    row = MaintenanceScheduleService(db).rows(equipment_id=equipment.id)[0]

    assert row.is_hour_based is True
    assert row.due_date is None
    assert row.due_operating_hours == 500
    assert row.hours_remaining == 88
    assert row.status == "hours_waiting"


def test_echeancier_heures_signale_un_controle_a_10_heures(
    db, admin, equipment, equipment_type
):
    _set_hours(db, equipment, current=1995)
    _rule(
        db,
        admin,
        equipment_type,
        interval_value=500,
        interval_unit=MaintenanceIntervalUnit.HOURS,
    )

    row = MaintenanceScheduleService(db).rows(equipment_id=equipment.id)[0]

    assert row.due_operating_hours == 2000
    assert row.hours_remaining == 5
    assert row.status == "hours_due_soon"
    assert row.status_label == "Contrôle des heures à planifier"


def test_echeancier_heures_seuil_depasse(db, admin, equipment, equipment_type):
    _set_hours(db, equipment, current=2075)
    _rule(
        db,
        admin,
        equipment_type,
        interval_value=500,
        interval_unit=MaintenanceIntervalUnit.HOURS,
    )

    row = MaintenanceScheduleService(db).rows(equipment_id=equipment.id)[0]

    assert row.due_operating_hours == 2500
    assert row.hours_remaining == 425
    # Le seuil 2000 est dépassé mais l'échéancier suit le prochain seuil.
    assert row.status == "hours_waiting"


def test_echeancier_heures_sans_releve(db, admin, equipment, equipment_type):
    _rule(
        db,
        admin,
        equipment_type,
        interval_value=500,
        interval_unit=MaintenanceIntervalUnit.HOURS,
    )

    row = MaintenanceScheduleService(db).rows(equipment_id=equipment.id)[0]

    assert row.status == "hours_no_reading"
    assert row.hours_remaining is None
    assert row.due_operating_hours is None


def test_realisation_en_heures_met_a_jour_le_compteur_et_repart_du_releve(
    db, admin, equipment, equipment_type
):
    equipment = _set_hours(db, equipment, current=1995)
    regle = _rule(
        db,
        admin,
        equipment_type,
        interval_value=500,
        interval_unit=MaintenanceIntervalUnit.HOURS,
    )

    execution = _execute(
        db,
        equipment,
        regle,
        REFERENCE_DATE,
        admin,
        operating_hours=2000,
    )

    assert execution.operating_hours == 2000
    assert execution.theoretical_due_date is None
    assert execution.delay_days is None
    assert execution.delay_label is None

    equipment = EquipmentService(db).get(equipment.id)
    assert equipment.operating_hours == 2000

    row = MaintenanceScheduleService(db).rows(equipment_id=equipment.id)[0]
    assert row.due_operating_hours == 2500
    assert row.hours_remaining == 500
    assert row.last_performed_hours == 2000


def test_realisation_en_heures_exige_un_releve(db, admin, equipment, equipment_type):
    _set_hours(db, equipment, current=1995)
    regle = _rule(
        db,
        admin,
        equipment_type,
        interval_value=500,
        interval_unit=MaintenanceIntervalUnit.HOURS,
    )

    # Le relevé courant de l'équipement sert de valeur par défaut.
    execution = _execute(db, equipment, regle, REFERENCE_DATE, admin)

    assert execution.operating_hours == 1995


def test_resume_compte_les_controles_horaires(db, admin, equipment, equipment_type):
    _set_hours(db, equipment, current=1995)
    _rule(
        db,
        admin,
        equipment_type,
        code="HEURES",
        interval_value=500,
        interval_unit=MaintenanceIntervalUnit.HOURS,
    )

    summary = MaintenanceScheduleService(db).summary(equipment_type_id=equipment_type.id)

    assert summary.total == 1
    assert summary.hours_based_count == 1
    assert summary.due_soon_count == 1
    assert summary.overdue_count == 0
