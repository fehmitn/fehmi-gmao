"""Routes web (Jinja2 + HTMX)."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, Response
from pydantic import BeforeValidator
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.config import CURRENT_USER_COOKIE
from app.database import get_db
from app.errors import (
    AuthenticationRequiredError,
    DomainError,
    PermissionDeniedError,
)
from app.models.enums import (
    CalibrationResult,
    CalibrationStatus,
    EquipmentStatus,
    MaintenanceAnchor,
    MaintenanceIntervalUnit,
    MaintenanceType,
    MovementType,
    StockMovementType,
    ToolStatus,
    WorkOrderPriority,
    WorkOrderStatus,
)
from app.models.user import User
from app.repositories.location_type import LocationTypeRepository
from app.schemas.equipment import EquipmentCreate, EquipmentUpdate, PlacementCreate
from app.schemas.equipment_type import EquipmentTypeCreate, EquipmentTypeUpdate
from app.schemas.intervention import (
    InterventionCancel,
    InterventionFinish,
    InterventionPartCreate,
    InterventionPartUse,
    InterventionRequestCreate,
    InterventionStart,
)
from app.schemas.location import LocationCreate, LocationUpdate
from app.schemas.maintenance_execution import MaintenanceExecutionCreate
from app.schemas.maintenance_supplier import (
    MaintenanceSupplierCreate,
    MaintenanceSupplierUpdate,
)
from app.schemas.maintenance_tool import (
    CalibrationCreate,
    MaintenanceToolCreate,
    MaintenanceToolUpdate,
    ToolUsageCreate,
    ToolUsageReturn,
)
from app.schemas.periodic_maintenance import (
    PeriodicMaintenanceCreate,
    PeriodicMaintenanceUpdate,
)
from app.schemas.site import SiteCreate, SiteUpdate
from app.schemas.spare_part import (
    SparePartCreate,
    SparePartUpdate,
    StockMovementCreate,
)
from app.services.dashboard_service import DashboardService
from app.services.analytics_service import AnalyticsService, PERIOD_CHOICES
from app.services.equipment_service import EquipmentService
from app.services.equipment_type_service import EquipmentTypeService
from app.services.intervention_service import InterventionService
from app.services.location_service import LocationService
from app.services.maintenance_execution_service import MaintenanceExecutionService
from app.services.maintenance_schedule_service import MaintenanceScheduleService
from app.services.maintenance_supplier_service import MaintenanceSupplierService
from app.services.maintenance_tool_service import MaintenanceToolService
from app.services.periodic_maintenance_service import PeriodicMaintenanceService
from app.services.placement_service import PlacementService
from app.services.site_service import SiteService
from app.services.spare_part_service import SparePartService
from app.services.clock import today
from app.services.user_service import UserService
from app.services.work_order_service import WorkOrderService
from app.web import formtools as ft
from app.web.session import cookie_name, decode_user, encode_user

# Filtre entier optionnel tolérant aux chaînes vides (envoyées par les
# formulaires lorsqu'aucune option n'est sélectionnée).
OptionalInt = Annotated[
    int | None, BeforeValidator(lambda v: None if v in (None, "") else v)
]
from app.web.templating import render

router = APIRouter(tags=["web"])


# --------------------------------------------------------------------- helpers
def _redirect(url: str, msg: str | None = None, err: str | None = None) -> RedirectResponse:
    from urllib.parse import urlencode

    params = {}
    if msg:
        params["msg"] = msg
    if err:
        params["err"] = err
    if params:
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}{urlencode(params)}"
    return RedirectResponse(url=url, status_code=303)


def _safe_next(request: Request) -> str:
    """Redirection interne uniquement (pas d'open redirect)."""
    candidate = request.headers.get("referer") or "/"
    if candidate.startswith("/"):
        return candidate
    return "/"


# ----------------------------------------------------------------- tableau de bord
@router.get("/")
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    service = DashboardService(db)
    stats = service.stats()
    backdates = service.recent_backdates(limit=10)
    schedule = MaintenanceScheduleService(db).summary(horizon_days=30)
    stock_summary = SparePartService(db).summary()
    tool_summary = MaintenanceToolService(db).summary()
    intervention_summary = InterventionService(db).summary()
    users = UserService(db).list_active()
    analytics = AnalyticsService(db).summary(days=90)
    alerts = AnalyticsService(db).alerts(threshold_days=3, limit=5)
    return render(
        request,
        "dashboard.html",
        {
            "stats": stats,
            "backdates": backdates,
            "schedule": schedule,
            "stock_summary": stock_summary,
            "tool_summary": tool_summary,
            "intervention_summary": intervention_summary,
            "analytics": analytics,
            "alerts": alerts,
            "users": users,
            "current_user": actor,
            "page_title": "Tableau de bord",
        },
    )


# ------------------------------------------------------------------- analyse
@router.get("/analytics")
def analytics_page(
    request: Request,
    days: int = 365,
    site_id: OptionalInt = None,
    sort: str = "availability",
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    service = AnalyticsService(db)
    summary = service.summary(days=days, site_id=site_id)

    def sort_key(row):
        if sort == "mttr":
            return (row.mttr_minutes is None, -(row.mttr_minutes or 0), row.equipment_code)
        if sort == "mtbf":
            return (row.mtbf_minutes is None, row.mtbf_minutes or 0, row.equipment_code)
        if sort == "cost":
            return (-row.parts_cost, row.equipment_code)
        if sort == "failures":
            return (-row.failure_count, row.equipment_code)
        if sort == "code":
            return (row.equipment_code,)
        return (
            row.availability is None,
            row.availability if row.availability is not None else 1.0,
            row.equipment_code,
        )

    rows = sorted(summary.equipment, key=sort_key)
    return render(
        request,
        "analytics/list.html",
        {
            "summary": summary,
            "rows": rows,
            "sites": SiteService(db).list(),
            "period_choices": PERIOD_CHOICES,
            "filters": {"days": summary.days, "site_id": site_id, "sort": sort},
            "current_user": actor,
            "page_title": "Analyse de maintenance",
        },
    )


# ----------------------------------------------------------------------- usines
@router.get("/sites")
def sites_page(
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    service = SiteService(db)
    sites = [service.enrich(site) for site in service.list()]
    return render(
        request,
        "sites/list.html",
        {
            "sites": sites,
            "users": UserService(db).list_active(),
            "current_user": actor,
            "page_title": "Usines",
        },
    )


@router.get("/sites/table")
def sites_table(
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    service = SiteService(db)
    sites = [service.enrich(site) for site in service.list()]
    return render(request, "partials/sites_table.html", {"sites": sites})


@router.post("/sites")
async def create_site(
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    data = await ft.form_data(request)
    try:
        payload = SiteCreate(
            code=ft.text(data, "code", "") or "",
            name=ft.text(data, "name", "") or "",
            description=ft.optional_text(data, "description"),
            address=ft.optional_text(data, "address"),
            city=ft.optional_text(data, "city"),
            country=ft.optional_text(data, "country"),
            timezone=ft.optional_text(data, "timezone"),
            is_active=ft.as_bool(data, "is_active", True),
        )
        SiteService(db).create(payload, actor=actor)
    except (DomainError, ValueError) as exc:
        message = exc.message if isinstance(exc, DomainError) else str(exc)
        return render(
            request,
            "partials/sites_table.html",
            {"sites": [], "error": message},
            status_code=400,
        )
    return await _sites_table_response(request, db)


async def _sites_table_response(request: Request, db: Session) -> Response:
    service = SiteService(db)
    sites = [service.enrich(site) for site in service.list()]
    return render(request, "partials/sites_table.html", {"sites": sites})


@router.get("/sites/{site_id}")
def site_detail(
    site_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    service = SiteService(db)
    site = service.enrich(service.get(site_id))
    locations = LocationService(db)
    types = LocationTypeRepository(db).list_all()
    return render(
        request,
        "sites/detail.html",
        {
            "site": site,
            "tree": locations.tree(site.id),
            "location_types": types,
            "users": UserService(db).list_active(),
            "current_user": actor,
            "page_title": f"Usine {site.code}",
        },
    )


@router.post("/sites/{site_id}/update")
async def update_site(
    site_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    data = await ft.form_data(request)
    try:
        payload = SiteUpdate(
            code=ft.optional_text(data, "code"),
            name=ft.optional_text(data, "name"),
            description=ft.optional_text(data, "description"),
            address=ft.optional_text(data, "address"),
            city=ft.optional_text(data, "city"),
            country=ft.optional_text(data, "country"),
            timezone=ft.optional_text(data, "timezone"),
            is_active=ft.as_bool(data, "is_active", True),
        )
        service = SiteService(db)
        site = service.update(service.get(site_id), payload, actor=actor)
    except (DomainError, ValueError) as exc:
        message = exc.message if isinstance(exc, DomainError) else str(exc)
        return _redirect(f"/sites/{site_id}", err=message)
    return _redirect(f"/sites/{site_id}", msg=f"Usine {site.code} mise à jour.")


@router.post("/sites/{site_id}/delete")
def delete_site(
    site_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    try:
        SiteService(db).delete(SiteService(db).get(site_id), actor=actor)
    except DomainError as exc:
        return _redirect("/sites", err=exc.message)
    return _redirect("/sites", msg="Usine supprimée.")


# ------------------------------------------------------------------ emplacements
@router.get("/locations")
def locations_page(
    request: Request,
    site_id: OptionalInt = None,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    site_service = SiteService(db)
    sites = site_service.list()
    selected = site_id or (sites[0].id if sites else None)
    locations = LocationService(db)
    return render(
        request,
        "locations/tree.html",
        {
            "sites": sites,
            "selected_site": selected,
            "tree": locations.tree(selected) if selected else [],
            "location_types": LocationTypeRepository(db).list_all(),
            "users": UserService(db).list_active(),
            "current_user": actor,
            "page_title": "Emplacements",
        },
    )


@router.get("/locations/{location_id}")
def location_detail(
    location_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    service = LocationService(db)
    location = service.enrich(service.get(location_id))
    types = LocationTypeRepository(db).list_all()
    candidates = [
        item
        for item in service.list_by_site(location.site_id)
        if item.id != location.id
    ]
    return render(
        request,
        "partials/location_detail.html",
        {
            "location": location,
            "location_types": types,
            "parent_candidates": candidates,
        },
    )


@router.post("/locations")
async def create_location(
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    data = await ft.form_data(request)
    try:
        payload = LocationCreate(
            site_id=ft.as_int(data, "site_id") or 0,
            parent_id=ft.as_int(data, "parent_id"),
            location_type_id=ft.as_int(data, "location_type_id") or 0,
            code=ft.text(data, "code", "") or "",
            name=ft.text(data, "name", "") or "",
            description=ft.optional_text(data, "description"),
            is_active=ft.as_bool(data, "is_active", True),
        )
        LocationService(db).create(payload, actor=actor)
    except (DomainError, ValueError) as exc:
        message = exc.message if isinstance(exc, DomainError) else str(exc)
        return _redirect(_safe_next(request), err=message)
    return _redirect(_safe_next(request), msg="Emplacement créé.")


@router.post("/locations/{location_id}/update")
async def update_location(
    location_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    data = await ft.form_data(request)
    try:
        payload = LocationUpdate(
            parent_id=ft.as_int(data, "parent_id"),
            location_type_id=ft.as_int(data, "location_type_id"),
            code=ft.optional_text(data, "code"),
            name=ft.optional_text(data, "name"),
            description=ft.optional_text(data, "description"),
            is_active=ft.as_bool(data, "is_active", True),
        )
        service = LocationService(db)
        service.update(service.get(location_id), payload, actor=actor)
    except (DomainError, ValueError) as exc:
        message = exc.message if isinstance(exc, DomainError) else str(exc)
        return _redirect(_safe_next(request), err=message)
    return _redirect(_safe_next(request), msg="Emplacement mis à jour.")


@router.post("/locations/{location_id}/move")
async def move_location(
    location_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    data = await ft.form_data(request)
    try:
        service = LocationService(db)
        service.move(service.get(location_id), ft.as_int(data, "parent_id"), actor=actor)
    except (DomainError, ValueError) as exc:
        message = exc.message if isinstance(exc, DomainError) else str(exc)
        return _redirect(_safe_next(request), err=message)
    return _redirect(_safe_next(request), msg="Emplacement déplacé.")


@router.post("/locations/{location_id}/delete")
def delete_location(
    location_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    try:
        service = LocationService(db)
        service.delete(service.get(location_id), actor=actor)
    except DomainError as exc:
        return _redirect(_safe_next(request), err=exc.message)
    return _redirect(_safe_next(request), msg="Emplacement supprimé.")


# ------------------------------------------------ fournisseurs de maintenance
@router.get("/maintenance-suppliers")
def maintenance_suppliers_page(
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    service = MaintenanceSupplierService(db)
    return render(
        request,
        "maintenance_suppliers/list.html",
        {
            "suppliers": service.list(),
            "users": UserService(db).list_active(),
            "current_user": actor,
            "page_title": "Fournisseurs de maintenance",
        },
    )


@router.get("/maintenance-suppliers/table")
def maintenance_suppliers_table(
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    return _maintenance_suppliers_table_response(request, db)


def _maintenance_suppliers_table_response(
    request: Request, db: Session, error: str | None = None
) -> Response:
    service = MaintenanceSupplierService(db)
    return render(
        request,
        "partials/maintenance_suppliers_table.html",
        {"suppliers": service.list(), "error": error},
    )


@router.post("/maintenance-suppliers")
async def create_maintenance_supplier(
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    data = await ft.form_data(request)
    try:
        payload = MaintenanceSupplierCreate(
            code=ft.text(data, "code", "") or "",
            name=ft.text(data, "name", "") or "",
            contact_name=ft.optional_text(data, "contact_name"),
            phone=ft.optional_text(data, "phone"),
            email=ft.optional_text(data, "email"),
            specialty=ft.optional_text(data, "specialty"),
            notes=ft.optional_text(data, "notes"),
            is_active=ft.as_bool(data, "is_active", True),
        )
        MaintenanceSupplierService(db).create(payload, actor=actor)
    except (DomainError, ValueError) as exc:
        message = exc.message if isinstance(exc, DomainError) else str(exc)
        return _maintenance_suppliers_table_response(request, db, error=message)
    return _maintenance_suppliers_table_response(request, db)


@router.get("/maintenance-suppliers/{supplier_id}/edit")
def edit_maintenance_supplier_page(
    supplier_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    supplier = MaintenanceSupplierService(db).get(supplier_id)
    return render(
        request,
        "maintenance_suppliers/edit.html",
        {
            "supplier": supplier,
            "users": UserService(db).list_active(),
            "current_user": actor,
            "page_title": f"Fournisseur {supplier.code}",
        },
    )


@router.post("/maintenance-suppliers/{supplier_id}/update")
async def update_maintenance_supplier(
    supplier_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    data = await ft.form_data(request)
    try:
        payload = MaintenanceSupplierUpdate(
            code=ft.optional_text(data, "code"),
            name=ft.optional_text(data, "name"),
            contact_name=ft.optional_text(data, "contact_name"),
            phone=ft.optional_text(data, "phone"),
            email=ft.optional_text(data, "email"),
            specialty=ft.optional_text(data, "specialty"),
            notes=ft.optional_text(data, "notes"),
            is_active=ft.as_bool(data, "is_active", False),
        )
        service = MaintenanceSupplierService(db)
        service.update(service.get(supplier_id), payload, actor=actor)
    except (DomainError, ValueError) as exc:
        message = exc.message if isinstance(exc, DomainError) else str(exc)
        return _redirect(f"/maintenance-suppliers/{supplier_id}/edit", err=message)
    return _redirect("/maintenance-suppliers", msg="Fournisseur mis à jour.")


@router.post("/maintenance-suppliers/{supplier_id}/delete")
def delete_maintenance_supplier(
    supplier_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    try:
        service = MaintenanceSupplierService(db)
        service.delete(service.get(supplier_id), actor=actor)
    except DomainError as exc:
        return _redirect("/maintenance-suppliers", err=exc.message)
    return _redirect("/maintenance-suppliers", msg="Fournisseur supprimé.")


# ------------------------------------------------------------ pièces de rechange
def _spare_part_create_payload(data: dict[str, str]) -> SparePartCreate:
    return SparePartCreate(
        code=ft.text(data, "code", "") or "",
        name=ft.text(data, "name", "") or "",
        description=ft.optional_text(data, "description"),
        category=ft.optional_text(data, "category"),
        unit=ft.text(data, "unit", "pièce") or "pièce",
        manufacturer=ft.optional_text(data, "manufacturer"),
        manufacturer_reference=ft.optional_text(data, "manufacturer_reference"),
        supplier_id=ft.as_int(data, "supplier_id"),
        site_id=ft.as_int(data, "site_id"),
        storage_location=ft.optional_text(data, "storage_location"),
        quantity=ft.as_decimal(data, "quantity") or Decimal("0"),
        min_quantity=ft.as_decimal(data, "min_quantity") or Decimal("0"),
        max_quantity=ft.as_decimal(data, "max_quantity"),
        unit_cost=ft.as_decimal(data, "unit_cost"),
        is_active=ft.as_bool(data, "is_active", True),
        notes=ft.optional_text(data, "notes"),
    )


def _spare_part_update_payload(data: dict[str, str]) -> SparePartUpdate:
    return SparePartUpdate(
        code=ft.optional_text(data, "code"),
        name=ft.optional_text(data, "name"),
        description=ft.optional_text(data, "description"),
        category=ft.optional_text(data, "category"),
        unit=ft.optional_text(data, "unit"),
        manufacturer=ft.optional_text(data, "manufacturer"),
        manufacturer_reference=ft.optional_text(data, "manufacturer_reference"),
        supplier_id=ft.as_int(data, "supplier_id"),
        site_id=ft.as_int(data, "site_id"),
        storage_location=ft.optional_text(data, "storage_location"),
        min_quantity=ft.as_decimal(data, "min_quantity") or Decimal("0"),
        max_quantity=ft.as_decimal(data, "max_quantity"),
        unit_cost=ft.as_decimal(data, "unit_cost"),
        is_active=ft.as_bool(data, "is_active", False),
        notes=ft.optional_text(data, "notes"),
    )


def _spare_part_form_context(
    db: Session, actor: User | None, part, title: str
) -> dict:
    return {
        "part": part,
        "suppliers": MaintenanceSupplierService(db).list(active_only=True),
        "sites": SiteService(db).list(active_only=True),
        "users": UserService(db).list_active(),
        "current_user": actor,
        "page_title": title,
    }


@router.get("/spare-parts")
def spare_parts_page(
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    service = SparePartService(db)
    search = request.query_params.get("search") or None
    category = request.query_params.get("category") or None
    low_stock_only = request.query_params.get("low_stock") == "1"
    active_only = request.query_params.get("active_only") == "1"
    parts = service.list(
        search=search,
        category=category,
        low_stock_only=low_stock_only,
        active_only=active_only,
    )
    return render(
        request,
        "spare_parts/list.html",
        {
            "parts": parts,
            "summary": service.summary(),
            "categories": service.categories(),
            "filters": {
                "search": search or "",
                "category": category or "",
                "low_stock": low_stock_only,
                "active_only": active_only,
            },
            "users": UserService(db).list_active(),
            "current_user": actor,
            "page_title": "Pièces de rechange",
        },
    )


@router.get("/spare-parts/new")
def new_spare_part_page(
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    return render(
        request,
        "spare_parts/form.html",
        _spare_part_form_context(db, actor, None, "Nouvelle pièce de rechange"),
    )


@router.post("/spare-parts")
async def create_spare_part(
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    data = await ft.form_data(request)
    try:
        part = SparePartService(db).create(
            _spare_part_create_payload(data), actor=actor
        )
    except (DomainError, ValueError) as exc:
        message = exc.message if isinstance(exc, DomainError) else str(exc)
        return _redirect("/spare-parts/new", err=message)
    return _redirect(f"/spare-parts/{part.id}", msg="Pièce de rechange créée.")


@router.get("/spare-parts/{spare_part_id}")
def spare_part_detail_page(
    spare_part_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    service = SparePartService(db)
    part = service.get(spare_part_id)
    return render(
        request,
        "spare_parts/detail.html",
        {
            "part": part,
            "movements": service.movements(spare_part_id),
            "movement_types": list(StockMovementType),
            "work_orders": WorkOrderService(db).list(open_only=True),
            "interchanges": service.interchanges(part),
            "replacements": service.replacements(part),
            "available_parts": [
                item
                for item in service.list(active_only=True)
                if item.id != part.id
            ],
            "users": UserService(db).list_active(),
            "current_user": actor,
            "page_title": f"Pièce {part.code}",
        },
    )


@router.get("/spare-parts/{spare_part_id}/edit")
def edit_spare_part_page(
    spare_part_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    part = SparePartService(db).get(spare_part_id)
    return render(
        request,
        "spare_parts/form.html",
        _spare_part_form_context(db, actor, part, f"Modifier {part.code}"),
    )


@router.post("/spare-parts/{spare_part_id}/update")
async def update_spare_part(
    spare_part_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    data = await ft.form_data(request)
    try:
        service = SparePartService(db)
        service.update(
            service.get(spare_part_id),
            _spare_part_update_payload(data),
            actor=actor,
        )
    except (DomainError, ValueError) as exc:
        message = exc.message if isinstance(exc, DomainError) else str(exc)
        return _redirect(f"/spare-parts/{spare_part_id}/edit", err=message)
    return _redirect(f"/spare-parts/{spare_part_id}", msg="Pièce mise à jour.")


@router.post("/spare-parts/{spare_part_id}/movements")
async def create_stock_movement(
    spare_part_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    data = await ft.form_data(request)
    try:
        payload = StockMovementCreate(
            movement_type=ft.text(data, "movement_type", "entry") or "entry",
            quantity=ft.as_decimal(data, "quantity") or Decimal("0"),
            movement_date=ft.as_date(data, "movement_date"),
            reference=ft.optional_text(data, "reference"),
            notes=ft.optional_text(data, "notes"),
            work_order_id=ft.as_int(data, "work_order_id"),
        )
        service = SparePartService(db)
        service.record_movement(
            service.get(spare_part_id), payload, actor=actor
        )
    except (DomainError, ValueError) as exc:
        message = exc.message if isinstance(exc, DomainError) else str(exc)
        return _redirect(f"/spare-parts/{spare_part_id}", err=message)
    return _redirect(f"/spare-parts/{spare_part_id}", msg="Mouvement de stock enregistré.")


@router.post("/spare-parts/{spare_part_id}/delete")
def delete_spare_part(
    spare_part_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    try:
        service = SparePartService(db)
        service.delete(service.get(spare_part_id), actor=actor)
    except DomainError as exc:
        return _redirect(f"/spare-parts/{spare_part_id}", err=exc.message)
    return _redirect("/spare-parts", msg="Pièce de rechange supprimée.")


@router.post("/spare-parts/{spare_part_id}/interchanges")
async def create_spare_part_interchange(
    spare_part_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    data = await ft.form_data(request)
    try:
        replaces_id = ft.as_int(data, "replaces_id")
        if replaces_id is None:
            raise DomainError("Sélectionnez la pièce à remplacer.")
        service = SparePartService(db)
        part = service.get(spare_part_id)
        service.add_interchange(
            part,
            replaces_id,
            note=ft.optional_text(data, "note"),
            actor=actor,
        )
    except (DomainError, ValueError) as exc:
        message = exc.message if isinstance(exc, DomainError) else str(exc)
        return _redirect(f"/spare-parts/{spare_part_id}", err=message)
    return _redirect(
        f"/spare-parts/{spare_part_id}",
        msg="Compatibilité enregistrée.",
    )


@router.post(
    "/spare-parts/{spare_part_id}/interchanges/{interchange_id}/delete"
)
def delete_spare_part_interchange(
    spare_part_id: int,
    interchange_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    try:
        service = SparePartService(db)
        service.remove_interchange(
            service.get(spare_part_id), interchange_id, actor=actor
        )
    except DomainError as exc:
        return _redirect(f"/spare-parts/{spare_part_id}", err=exc.message)
    return _redirect(
        f"/spare-parts/{spare_part_id}",
        msg="Compatibilité supprimée.",
    )


# ---------------------------------------------- équipements de maintenance
CALIBRATION_INTERVAL_UNITS = [
    unit for unit in MaintenanceIntervalUnit if unit is not MaintenanceIntervalUnit.HOURS
]


def _tool_form_context(
    db: Session, actor: User | None, tool, title: str
) -> dict:
    return {
        "tool": tool,
        "statuses": list(ToolStatus),
        "interval_units": CALIBRATION_INTERVAL_UNITS,
        "suppliers": MaintenanceSupplierService(db).list(active_only=True),
        "sites": SiteService(db).list(active_only=True),
        "users": UserService(db).list_active(),
        "current_user": actor,
        "page_title": title,
    }


def _tool_create_payload(data: dict[str, str]) -> MaintenanceToolCreate:
    return MaintenanceToolCreate(
        code=ft.text(data, "code", "") or "",
        name=ft.text(data, "name", "") or "",
        description=ft.optional_text(data, "description"),
        category=ft.optional_text(data, "category"),
        manufacturer=ft.optional_text(data, "manufacturer"),
        model=ft.optional_text(data, "model"),
        serial_number=ft.optional_text(data, "serial_number"),
        site_id=ft.as_int(data, "site_id"),
        storage_location=ft.optional_text(data, "storage_location"),
        status=ft.text(data, "status", ToolStatus.AVAILABLE.value)
        or ToolStatus.AVAILABLE.value,
        requires_calibration=ft.as_bool(data, "requires_calibration", False),
        calibration_interval_value=ft.as_int(data, "calibration_interval_value"),
        calibration_interval_unit=ft.text(data, "calibration_interval_unit", "months")
        or "months",
        last_calibration_date=ft.as_date(data, "last_calibration_date"),
        next_calibration_date=ft.as_date(data, "next_calibration_date"),
        calibration_provider_id=ft.as_int(data, "calibration_provider_id"),
        legal_reference=ft.optional_text(data, "legal_reference"),
        purchase_date=ft.as_date(data, "purchase_date"),
        commissioning_date=ft.as_date(data, "commissioning_date"),
        is_active=ft.as_bool(data, "is_active", True),
        notes=ft.optional_text(data, "notes"),
    )


def _tool_update_payload(data: dict[str, str]) -> MaintenanceToolUpdate:
    return MaintenanceToolUpdate(
        code=ft.optional_text(data, "code"),
        name=ft.optional_text(data, "name"),
        description=ft.optional_text(data, "description"),
        category=ft.optional_text(data, "category"),
        manufacturer=ft.optional_text(data, "manufacturer"),
        model=ft.optional_text(data, "model"),
        serial_number=ft.optional_text(data, "serial_number"),
        site_id=ft.as_int(data, "site_id"),
        storage_location=ft.optional_text(data, "storage_location"),
        requires_calibration=ft.as_bool(data, "requires_calibration", False),
        calibration_interval_value=ft.as_int(data, "calibration_interval_value"),
        calibration_interval_unit=ft.text(data, "calibration_interval_unit", "months")
        or "months",
        last_calibration_date=ft.as_date(data, "last_calibration_date"),
        next_calibration_date=ft.as_date(data, "next_calibration_date"),
        calibration_provider_id=ft.as_int(data, "calibration_provider_id"),
        legal_reference=ft.optional_text(data, "legal_reference"),
        purchase_date=ft.as_date(data, "purchase_date"),
        commissioning_date=ft.as_date(data, "commissioning_date"),
        is_active=ft.as_bool(data, "is_active", False),
        notes=ft.optional_text(data, "notes"),
    )


@router.get("/maintenance-tools")
def maintenance_tools_page(
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    service = MaintenanceToolService(db)
    search = request.query_params.get("search") or None
    category = request.query_params.get("category") or None
    status = request.query_params.get("status") or None
    calibration_status = request.query_params.get("calibration_status") or None
    tools = service.list(
        search=search,
        category=category,
        status=status,
        calibration_status=calibration_status,
    )
    return render(
        request,
        "maintenance_tools/list.html",
        {
            "tools": tools,
            "summary": service.summary(),
            "categories": service.categories(),
            "statuses": list(ToolStatus),
            "calibration_statuses": list(CalibrationStatus),
            "filters": {
                "search": search or "",
                "category": category or "",
                "status": status or "",
                "calibration_status": calibration_status or "",
            },
            "users": UserService(db).list_active(),
            "current_user": actor,
            "page_title": "Équipements de maintenance",
        },
    )


@router.get("/maintenance-tools/new")
def new_maintenance_tool_page(
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    return render(
        request,
        "maintenance_tools/form.html",
        _tool_form_context(
            db, actor, None, "Nouvel équipement de maintenance"
        ),
    )


@router.post("/maintenance-tools")
async def create_maintenance_tool(
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    data = await ft.form_data(request)
    try:
        tool = MaintenanceToolService(db).create(
            _tool_create_payload(data), actor=actor
        )
    except (DomainError, ValueError) as exc:
        message = exc.message if isinstance(exc, DomainError) else str(exc)
        return _redirect("/maintenance-tools/new", err=message)
    return _redirect(
        f"/maintenance-tools/{tool.id}", msg="Équipement de maintenance créé."
    )


@router.get("/maintenance-tools/{tool_id}")
def maintenance_tool_detail_page(
    tool_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    service = MaintenanceToolService(db)
    tool = service.get(tool_id)
    return render(
        request,
        "maintenance_tools/detail.html",
        {
            "tool": tool,
            "calibrations": service.calibrations(tool_id),
            "usages": service.usages(tool_id),
            "calibration_results": list(CalibrationResult),
            "statuses": list(ToolStatus),
            "suppliers": MaintenanceSupplierService(db).list(active_only=True),
            "work_orders": WorkOrderService(db).list(open_only=True),
            "users": UserService(db).list_active(),
            "current_user": actor,
            "page_title": f"Fiche outil {tool.code}",
        },
    )


@router.get("/maintenance-tools/{tool_id}/edit")
def edit_maintenance_tool_page(
    tool_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    tool = MaintenanceToolService(db).get(tool_id)
    return render(
        request,
        "maintenance_tools/form.html",
        _tool_form_context(db, actor, tool, f"Modifier {tool.code}"),
    )


@router.post("/maintenance-tools/{tool_id}/update")
async def update_maintenance_tool(
    tool_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    data = await ft.form_data(request)
    try:
        service = MaintenanceToolService(db)
        service.update(
            service.get(tool_id), _tool_update_payload(data), actor=actor
        )
    except (DomainError, ValueError) as exc:
        message = exc.message if isinstance(exc, DomainError) else str(exc)
        return _redirect(f"/maintenance-tools/{tool_id}/edit", err=message)
    return _redirect(f"/maintenance-tools/{tool_id}", msg="Fiche outil mise à jour.")


@router.post("/maintenance-tools/{tool_id}/calibrations")
async def create_tool_calibration(
    tool_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    data = await ft.form_data(request)
    try:
        calibrated_on = ft.as_date(data, "calibrated_on")
        if calibrated_on is None:
            raise ValueError("La date d'étalonnage est obligatoire.")
        payload = CalibrationCreate(
            calibrated_on=calibrated_on,
            next_due_date=ft.as_date(data, "next_due_date"),
            provider_id=ft.as_int(data, "provider_id"),
            certificate_number=ft.optional_text(data, "certificate_number"),
            result=ft.text(data, "result", "passed") or "passed",
            cost=ft.as_decimal(data, "cost"),
            notes=ft.optional_text(data, "notes"),
        )
        service = MaintenanceToolService(db)
        service.add_calibration(service.get(tool_id), payload, actor=actor)
    except (DomainError, ValueError) as exc:
        message = exc.message if isinstance(exc, DomainError) else str(exc)
        return _redirect(f"/maintenance-tools/{tool_id}", err=message)
    return _redirect(f"/maintenance-tools/{tool_id}", msg="Étalonnage enregistré.")


@router.post("/maintenance-tools/{tool_id}/usages")
async def start_tool_usage(
    tool_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    data = await ft.form_data(request)
    try:
        payload = ToolUsageCreate(
            work_order_id=ft.as_int(data, "work_order_id"),
            used_by_id=ft.as_int(data, "used_by_id"),
            started_on=ft.as_date(data, "started_on"),
            notes=ft.optional_text(data, "notes"),
        )
        service = MaintenanceToolService(db)
        service.start_usage(service.get(tool_id), payload, actor=actor)
    except (DomainError, ValueError) as exc:
        message = exc.message if isinstance(exc, DomainError) else str(exc)
        return _redirect(f"/maintenance-tools/{tool_id}", err=message)
    return _redirect(f"/maintenance-tools/{tool_id}", msg="Utilisation enregistrée.")


@router.post("/maintenance-tools/{tool_id}/usages/{usage_id}/return")
async def end_tool_usage(
    tool_id: int,
    usage_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    data = await ft.form_data(request)
    try:
        service = MaintenanceToolService(db)
        tool = service.get(tool_id)
        usage = service.repository.get_usage(tool_id, usage_id)
        if usage is None:
            raise ValueError("Utilisation introuvable pour cet outil.")
        service.end_usage(
            tool,
            usage,
            ToolUsageReturn(
                ended_on=ft.as_date(data, "ended_on"),
                return_notes=ft.optional_text(data, "return_notes"),
            ),
            actor=actor,
        )
    except (DomainError, ValueError) as exc:
        message = exc.message if isinstance(exc, DomainError) else str(exc)
        return _redirect(f"/maintenance-tools/{tool_id}", err=message)
    return _redirect(f"/maintenance-tools/{tool_id}", msg="Outil restitué.")


@router.post("/maintenance-tools/{tool_id}/status")
async def update_tool_status(
    tool_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    data = await ft.form_data(request)
    try:
        status = ft.text(data, "status", "")
        if not status:
            raise ValueError("Le statut est obligatoire.")
        service = MaintenanceToolService(db)
        service.set_status(service.get(tool_id), status, actor=actor)
    except (DomainError, ValueError) as exc:
        message = exc.message if isinstance(exc, DomainError) else str(exc)
        return _redirect(f"/maintenance-tools/{tool_id}", err=message)
    return _redirect(f"/maintenance-tools/{tool_id}", msg="Statut mis à jour.")


@router.post("/maintenance-tools/{tool_id}/delete")
def delete_maintenance_tool(
    tool_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    try:
        service = MaintenanceToolService(db)
        service.delete(service.get(tool_id), actor=actor)
    except DomainError as exc:
        return _redirect(f"/maintenance-tools/{tool_id}", err=exc.message)
    return _redirect("/maintenance-tools", msg="Équipement de maintenance supprimé.")


# ---------------------------------------------------------- types d'équipements
@router.get("/equipment-types")
def equipment_types_page(
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    service = EquipmentTypeService(db)
    types = [service.enrich(item) for item in service.list()]
    return render(
        request,
        "equipment_types/list.html",
        {
            "equipment_types": types,
            "users": UserService(db).list_active(),
            "current_user": actor,
            "page_title": "Types d'équipements",
        },
    )


@router.get("/equipment-types/table")
def equipment_types_table(request: Request, db: Session = Depends(get_db)) -> Response:
    service = EquipmentTypeService(db)
    types = [service.enrich(item) for item in service.list()]
    return render(request, "partials/equipment_types_table.html", {"equipment_types": types})


@router.post("/equipment-types")
async def create_equipment_type(
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    data = await ft.form_data(request)
    try:
        payload = EquipmentTypeCreate(
            code=ft.text(data, "code", "") or "",
            name=ft.text(data, "name", "") or "",
            category=ft.text(data, "category", "") or "",
            manufacturer=ft.optional_text(data, "manufacturer"),
            model=ft.optional_text(data, "model"),
            description=ft.optional_text(data, "description"),
            criticality=ft.optional_text(data, "criticality"),
        )
        EquipmentTypeService(db).create(payload, actor=actor)
    except (DomainError, ValueError) as exc:
        message = exc.message if isinstance(exc, DomainError) else str(exc)
        return render(
            request,
            "partials/equipment_types_table.html",
            {"equipment_types": [], "error": message},
            status_code=400,
        )
    return await _equipment_types_table_response(request, db)


async def _equipment_types_table_response(request: Request, db: Session) -> Response:
    service = EquipmentTypeService(db)
    types = [service.enrich(item) for item in service.list()]
    return render(
        request, "partials/equipment_types_table.html", {"equipment_types": types}
    )


@router.get("/equipment-types/{type_id}")
def equipment_type_detail(
    type_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    equipment_type = EquipmentTypeService(db).get(type_id)
    maintenance_service = PeriodicMaintenanceService(db)
    return render(
        request,
        "equipment_types/detail.html",
        {
            "equipment_type": equipment_type,
            "maintenances": maintenance_service.list_for_type(type_id),
            "suppliers": MaintenanceSupplierService(db).list(),
            "interval_units": list(MaintenanceIntervalUnit),
            "maintenance_types": list(MaintenanceType),
            "anchors": list(MaintenanceAnchor),
            "users": UserService(db).list_active(),
            "current_user": actor,
            "page_title": f"Famille {equipment_type.code}",
        },
    )


def _periodic_payload_from_form(data: dict[str, str]) -> PeriodicMaintenanceCreate:
    interval_value = ft.as_int(data, "interval_value")
    if interval_value is None:
        raise ValueError("La périodicité (nombre) est obligatoire.")
    return PeriodicMaintenanceCreate(
        code=ft.text(data, "code", "") or "",
        label=ft.text(data, "label", "") or "",
        description=ft.optional_text(data, "description"),
        interval_value=interval_value,
        interval_unit=ft.text(data, "interval_unit", "months") or "months",
        maintenance_type=ft.text(
            data, "maintenance_type", MaintenanceType.PREVENTIVE_SYSTEMATIC.value
        )
        or MaintenanceType.PREVENTIVE_SYSTEMATIC.value,
        anchor=ft.text(data, "anchor", MaintenanceAnchor.COMMISSIONING.value)
        or MaintenanceAnchor.COMMISSIONING.value,
        fixed_date=ft.as_date(data, "fixed_date"),
        supplier_id=ft.as_int(data, "supplier_id"),
        tolerance_days=ft.as_int(data, "tolerance_days") or 0,
        estimated_duration_minutes=ft.as_int(data, "estimated_duration_minutes"),
        sort_order=ft.as_int(data, "sort_order") or 0,
        is_active=ft.as_bool(data, "is_active", True),
    )


@router.post("/equipment-types/{type_id}/periodic-maintenances")
async def create_periodic_maintenance(
    type_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    data = await ft.form_data(request)
    try:
        payload = _periodic_payload_from_form(data)
        PeriodicMaintenanceService(db).create(type_id, payload, actor=actor)
    except (DomainError, ValueError) as exc:
        message = exc.message if isinstance(exc, DomainError) else str(exc)
        return _redirect(f"/equipment-types/{type_id}", err=message)
    return _redirect(
        f"/equipment-types/{type_id}", msg="Maintenance périodique ajoutée."
    )


@router.get("/equipment-types/{type_id}/periodic-maintenances/{maintenance_id}/edit")
def edit_periodic_maintenance_page(
    type_id: int,
    maintenance_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    equipment_type = EquipmentTypeService(db).get(type_id)
    maintenance = PeriodicMaintenanceService(db).get(maintenance_id)
    return render(
        request,
        "periodic_maintenance/edit.html",
        {
            "equipment_type": equipment_type,
            "maintenance": maintenance,
            "suppliers": MaintenanceSupplierService(db).list(),
            "interval_units": list(MaintenanceIntervalUnit),
            "maintenance_types": list(MaintenanceType),
            "anchors": list(MaintenanceAnchor),
            "users": UserService(db).list_active(),
            "current_user": actor,
            "page_title": f"Modifier {maintenance.code}",
        },
    )


@router.post(
    "/equipment-types/{type_id}/periodic-maintenances/{maintenance_id}/update"
)
async def update_periodic_maintenance(
    type_id: int,
    maintenance_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    data = await ft.form_data(request)
    try:
        payload = PeriodicMaintenanceUpdate(
            code=ft.optional_text(data, "code"),
            label=ft.optional_text(data, "label"),
            description=ft.optional_text(data, "description"),
            interval_value=ft.as_int(data, "interval_value"),
            interval_unit=ft.optional_text(data, "interval_unit"),
            maintenance_type=ft.optional_text(data, "maintenance_type"),
            anchor=ft.optional_text(data, "anchor"),
            fixed_date=ft.as_date(data, "fixed_date"),
            supplier_id=ft.as_int(data, "supplier_id"),
            tolerance_days=ft.as_int(data, "tolerance_days"),
            estimated_duration_minutes=ft.as_int(data, "estimated_duration_minutes"),
            sort_order=ft.as_int(data, "sort_order"),
            is_active=ft.as_bool(data, "is_active", False),
        )
        service = PeriodicMaintenanceService(db)
        service.update(service.get(maintenance_id), payload, actor=actor)
    except (DomainError, ValueError) as exc:
        message = exc.message if isinstance(exc, DomainError) else str(exc)
        return _redirect(
            f"/equipment-types/{type_id}/periodic-maintenances/{maintenance_id}/edit",
            err=message,
        )
    return _redirect(
        f"/equipment-types/{type_id}", msg="Maintenance périodique mise à jour."
    )


@router.post(
    "/equipment-types/{type_id}/periodic-maintenances/{maintenance_id}/delete"
)
def delete_periodic_maintenance(
    type_id: int,
    maintenance_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    try:
        service = PeriodicMaintenanceService(db)
        service.delete(service.get(maintenance_id), actor=actor)
    except DomainError as exc:
        return _redirect(f"/equipment-types/{type_id}", err=exc.message)
    return _redirect(
        f"/equipment-types/{type_id}", msg="Maintenance périodique supprimée."
    )


@router.post("/equipment-types/{type_id}/update")
async def update_equipment_type(
    type_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    data = await ft.form_data(request)
    try:
        payload = EquipmentTypeUpdate(
            code=ft.optional_text(data, "code"),
            name=ft.optional_text(data, "name"),
            category=ft.optional_text(data, "category"),
            manufacturer=ft.optional_text(data, "manufacturer"),
            model=ft.optional_text(data, "model"),
            description=ft.optional_text(data, "description"),
            criticality=ft.optional_text(data, "criticality"),
        )
        service = EquipmentTypeService(db)
        service.update(service.get(type_id), payload, actor=actor)
    except (DomainError, ValueError) as exc:
        message = exc.message if isinstance(exc, DomainError) else str(exc)
        return _redirect("/equipment-types", err=message)
    return _redirect("/equipment-types", msg="Type d'équipement mis à jour.")


@router.post("/equipment-types/{type_id}/delete")
def delete_equipment_type(
    type_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    try:
        service = EquipmentTypeService(db)
        service.delete(service.get(type_id), actor=actor)
    except DomainError as exc:
        return _redirect("/equipment-types", err=exc.message)
    return _redirect("/equipment-types", msg="Type d'équipement supprimé.")


# ------------------------------------------------------------------ équipements
@router.get("/equipments")
def equipments_page(
    request: Request,
    site_id: OptionalInt = None,
    location_id: OptionalInt = None,
    equipment_type_id: OptionalInt = None,
    status_filter: str | None = None,
    criticality: str | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    context = _equipment_list_context(
        request,
        db,
        site_id=site_id,
        location_id=location_id,
        equipment_type_id=equipment_type_id,
        status_filter=status_filter,
        criticality=criticality,
        search=search,
    )
    context.update(
        {
            "users": UserService(db).list_active(),
            "current_user": actor,
            "page_title": "Équipements",
        }
    )
    return render(request, "equipments/list.html", context)


@router.get("/equipments/table")
def equipments_table(
    request: Request,
    site_id: OptionalInt = None,
    location_id: OptionalInt = None,
    equipment_type_id: OptionalInt = None,
    status_filter: str | None = None,
    criticality: str | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
) -> Response:
    context = _equipment_list_context(
        request,
        db,
        site_id=site_id,
        location_id=location_id,
        equipment_type_id=equipment_type_id,
        status_filter=status_filter,
        criticality=criticality,
        search=search,
    )
    return render(request, "partials/equipment_table.html", context)


def _equipment_list_context(
    request: Request,
    db: Session,
    *,
    site_id: int | None,
    location_id: int | None,
    equipment_type_id: int | None,
    status_filter: str | None,
    criticality: str | None,
    search: str | None,
) -> dict:
    service = EquipmentService(db)
    page = service.list(
        site_id=site_id,
        location_id=location_id,
        include_descendants=True,
        equipment_type_id=equipment_type_id,
        status=status_filter or None,
        criticality=criticality or None,
        search=search or None,
        page=1,
        size=100,
    )
    site_service = SiteService(db)
    location_service = LocationService(db)
    sites = site_service.list()
    locations = [location_service.enrich(location) for location in location_service.list_all()]
    return {
        "equipments": page.items,
        "total": page.total,
        "sites": sites,
        "locations": locations,
        "equipment_types": EquipmentTypeService(db).list(),
        "statuses": list(EquipmentStatus),
        "filters": {
            "site_id": site_id,
            "location_id": location_id,
            "equipment_type_id": equipment_type_id,
            "status": status_filter,
            "criticality": criticality,
            "search": search,
        },
    }


@router.get("/equipments/new")
def new_equipment_form(
    request: Request,
    site_id: OptionalInt = None,
    location_id: OptionalInt = None,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    sites = SiteService(db).list()
    selected_site = site_id or (sites[0].id if sites else None)
    # Tous les emplacements sont envoyés : le filtre « usine » de la page
    # restreint la liste côté navigateur (attribut data-site).
    location_service = LocationService(db)
    locations = [location_service.enrich(item) for item in location_service.list_all()]
    return render(
        request,
        "equipments/form.html",
        {
            "mode": "create",
            "equipment": None,
            "sites": sites,
            "locations": locations,
            "selected_site": selected_site,
            "equipment_types": EquipmentTypeService(db).list(),
            "statuses": list(EquipmentStatus),
            "users": UserService(db).list_active(),
            "current_user": actor,
            "page_title": "Nouvel équipement",
        },
    )


@router.get("/equipments/{equipment_id}/edit")
def edit_equipment_form(
    equipment_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    service = EquipmentService(db)
    equipment = service.get(equipment_id)
    sites = SiteService(db).list()
    locations = LocationService(db).list_by_site(equipment.site_id)
    return render(
        request,
        "equipments/form.html",
        {
            "mode": "edit",
            "equipment": equipment,
            "sites": sites,
            "locations": locations,
            "selected_site": equipment.site_id,
            "equipment_types": EquipmentTypeService(db).list(),
            "statuses": list(EquipmentStatus),
            "users": UserService(db).list_active(),
            "current_user": actor,
            "page_title": f"Modifier {equipment.code}",
        },
    )


@router.post("/equipments")
async def create_equipment(
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    data = await ft.form_data(request)
    try:
        payload = EquipmentCreate(
            code=ft.text(data, "code", "") or "",
            name=ft.text(data, "name", "") or "",
            description=ft.optional_text(data, "description"),
            equipment_type_id=ft.as_int(data, "equipment_type_id"),
            location_id=ft.as_int(data, "location_id") or 0,
            status=EquipmentStatus(ft.text(data, "status", "operational") or "operational"),
            criticality=ft.optional_text(data, "criticality"),
            manufacturer=ft.optional_text(data, "manufacturer"),
            model=ft.optional_text(data, "model"),
            serial_number=ft.optional_text(data, "serial_number"),
            purchase_date=ft.as_date(data, "purchase_date"),
            commissioning_date=ft.as_date(data, "commissioning_date"),
            acquisition_cost=ft.as_decimal(data, "acquisition_cost"),
            warranty_end_date=ft.as_date(data, "warranty_end_date"),
            is_critical=ft.as_bool(data, "is_critical", False),
            operating_hours=ft.as_int(data, "operating_hours"),
            initial_operating_hours=ft.as_int(data, "initial_operating_hours") or 0,
            effective_from=ft.as_date(data, "effective_from"),
            derogation_reason=ft.optional_text(data, "derogation_reason"),
        )
        equipment = EquipmentService(db).create(payload, actor=actor)
    except (DomainError, ValueError) as exc:
        message = exc.message if isinstance(exc, DomainError) else str(exc)
        return _redirect("/equipments/new", err=message)
    return _redirect(
        f"/equipments/{equipment.id}", msg=f"Équipement {equipment.code} enregistré."
    )


@router.post("/equipments/{equipment_id}/update")
async def update_equipment(
    equipment_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    data = await ft.form_data(request)
    try:
        payload = EquipmentUpdate(
            code=ft.optional_text(data, "code"),
            name=ft.optional_text(data, "name"),
            description=ft.optional_text(data, "description"),
            equipment_type_id=ft.as_int(data, "equipment_type_id"),
            status=EquipmentStatus(ft.text(data, "status", "operational") or "operational"),
            criticality=ft.optional_text(data, "criticality"),
            manufacturer=ft.optional_text(data, "manufacturer"),
            model=ft.optional_text(data, "model"),
            serial_number=ft.optional_text(data, "serial_number"),
            purchase_date=ft.as_date(data, "purchase_date"),
            commissioning_date=ft.as_date(data, "commissioning_date"),
            acquisition_cost=ft.as_decimal(data, "acquisition_cost"),
            warranty_end_date=ft.as_date(data, "warranty_end_date"),
            is_critical=ft.as_bool(data, "is_critical", False),
            operating_hours=ft.as_int(data, "operating_hours"),
            initial_operating_hours=ft.as_int(data, "initial_operating_hours"),
        )
        service = EquipmentService(db)
        equipment = service.update(service.get(equipment_id), payload, actor=actor)
    except (DomainError, ValueError) as exc:
        message = exc.message if isinstance(exc, DomainError) else str(exc)
        return _redirect(f"/equipments/{equipment_id}/edit", err=message)
    return _redirect(
        f"/equipments/{equipment.id}", msg=f"Équipement {equipment.code} mis à jour."
    )


@router.get("/equipments/{equipment_id}")
def equipment_detail(
    equipment_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    service = EquipmentService(db)
    equipment = service.get(equipment_id)
    placements = PlacementService(db)
    history = [placements.enrich(item) for item in placements.history(equipment_id)]
    site_service = SiteService(db)
    schedule_rows = MaintenanceScheduleService(db).for_equipment(equipment)
    executions = MaintenanceExecutionService(db).list_for_equipment(equipment_id)
    analytics = AnalyticsService(db).kpi_for(equipment_id, days=365)
    return render(
        request,
        "equipments/detail.html",
        {
            "equipment": equipment,
            "history": history,
            "schedule_rows": schedule_rows,
            "maintenance_executions": executions,
            "analytics": analytics,
            "sites": site_service.list(),
            "locations": LocationService(db).list_by_site(equipment.site_id),
            "users": UserService(db).list_active(),
            "current_user": actor,
            "page_title": f"Équipement {equipment.code}",
        },
    )


@router.post("/equipments/{equipment_id}/placements")
async def move_equipment(
    equipment_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    data = await ft.form_data(request)
    try:
        payload = PlacementCreate(
            location_id=ft.as_int(data, "location_id") or 0,
            effective_from=ft.as_date(data, "effective_from"),
            movement_type=MovementType(
                ft.text(data, "movement_type", MovementType.DEPLACEMENT.value)
                or MovementType.DEPLACEMENT.value
            ),
            reason=ft.optional_text(data, "reason"),
            derogation_reason=ft.optional_text(data, "derogation_reason"),
        )
        equipment = EquipmentService(db).get(equipment_id)
        deja_implante = PlacementService(db).current(equipment_id) is not None
        PlacementService(db).move(equipment, payload, actor=actor)
    except (DomainError, ValueError) as exc:
        message = exc.message if isinstance(exc, DomainError) else str(exc)
        return _redirect(f"/equipments/{equipment_id}", err=message)
    message = (
        "Déplacement enregistré." if deja_implante else "Implantation enregistrée."
    )
    return _redirect(f"/equipments/{equipment_id}", msg=message)


@router.post("/equipments/{equipment_id}/maintenance-executions")
async def create_maintenance_execution(
    equipment_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    data = await ft.form_data(request)
    try:
        payload = MaintenanceExecutionCreate(
            periodic_maintenance_id=ft.as_int(data, "periodic_maintenance_id") or 0,
            performed_on=ft.as_date(data, "performed_on"),
            performed_by_id=ft.as_int(data, "performed_by_id"),
            notes=ft.optional_text(data, "notes"),
            operating_hours=ft.as_int(data, "operating_hours"),
        )
        equipment = EquipmentService(db).get(equipment_id)
        rule = PeriodicMaintenanceService(db).get(payload.periodic_maintenance_id)
        execution = MaintenanceExecutionService(db).create(
            equipment, rule, payload, actor=actor
        )
    except (DomainError, ValueError) as exc:
        message = exc.message if isinstance(exc, DomainError) else str(exc)
        return _redirect(_safe_next(request), err=message)
    if execution.theoretical_due_date is not None and execution.delay_label:
        message = (
            f"Réalisation enregistrée : {execution.delay_label} "
            f"(échéance du {execution.theoretical_due_date.strftime('%d/%m/%Y')})."
        )
    else:
        message = (
            "Réalisation enregistrée : relevé du compteur "
            f"{execution.operating_hours} h."
        )
    return _redirect(_safe_next(request), msg=message)


@router.post("/equipments/{equipment_id}/delete")
def delete_equipment(
    equipment_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    try:
        service = EquipmentService(db)
        service.delete(service.get(equipment_id), actor=actor)
    except DomainError as exc:
        return _redirect(f"/equipments/{equipment_id}", err=exc.message)
    return _redirect("/equipments", msg="Équipement supprimé.")


# ------------------------------------------------------------------- utilisateurs
@router.get("/users")
def users_list(
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    from app.errors import DomainError

    if actor is None or actor.role != "admin":
        raise DomainError("Accès réservé aux administrateurs.", 403)
    users = UserService(db).list_all()
    return render(
        request,
        "users/list.html",
        {"users": users, "current_user": actor, "page_title": "Gestion des utilisateurs"},
    )


@router.get("/users/new")
def users_new(
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    from app.errors import DomainError
    from app.models.enums import UserRole

    if actor is None or actor.role != "admin":
        raise DomainError("Accès réservé aux administrateurs.", 403)
    return render(
        request,
        "users/form.html",
        {
            "user": None,
            "roles": list(UserRole),
            "current_user": actor,
            "page_title": "Nouvel utilisateur",
        },
    )


@router.post("/users")
async def users_create(
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    from app.errors import DomainError
    from app.schemas.user import UserCreate

    if actor is None or actor.role != "admin":
        raise DomainError("Accès réservé aux administrateurs.", 403)
    data = await ft.form_data(request)
    try:
        payload = UserCreate(
            username=ft.text(data, "username", "") or "",
            display_name=ft.text(data, "display_name", "") or "",
            role=ft.text(data, "role", "technicien") or "technicien",
            password=ft.text(data, "password", "") or None,
            is_active=ft.as_bool(data, "is_active", True),
        )
        UserService(db).create(payload, actor=actor)
    except DomainError as exc:
        return _redirect("/users/new", err=exc.message)
    return _redirect("/users", msg="Utilisateur créé.")


@router.get("/users/{user_id}/edit")
def users_edit(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    from app.errors import DomainError
    from app.models.enums import UserRole

    if actor is None or actor.role != "admin":
        raise DomainError("Accès réservé aux administrateurs.", 403)
    user = UserService(db).get(user_id)
    return render(
        request,
        "users/form.html",
        {
            "user": user,
            "roles": list(UserRole),
            "current_user": actor,
            "page_title": "Modifier l'utilisateur",
        },
    )


@router.post("/users/{user_id}")
async def users_update(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    from app.errors import DomainError
    from app.schemas.user import UserUpdate

    if actor is None or actor.role != "admin":
        raise DomainError("Accès réservé aux administrateurs.", 403)
    data = await ft.form_data(request)
    try:
        service = UserService(db)
        user = service.get(user_id)
        payload = UserUpdate(
            username=ft.text(data, "username", "") or None,
            display_name=ft.text(data, "display_name", "") or None,
            role=ft.text(data, "role", "") or None,
            password=ft.text(data, "password", "") or None,
            is_active=ft.as_bool(data, "is_active", True),
        )
        service.update(user, payload, actor=actor, current_user=actor)
    except DomainError as exc:
        return _redirect(f"/users/{user_id}/edit", err=exc.message)
    return _redirect("/users", msg="Utilisateur mis à jour.")


# ------------------------------------------------------------------- ordres de travail
@router.get("/work-orders")
def work_orders_page(
    request: Request,
    status: str | None = None,
    assigned_to_id: OptionalInt = None,
    search: str | None = None,
    mine: str | None = None,
    overdue: str | None = None,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    service = WorkOrderService(db)
    if mine == "1" and actor is not None and assigned_to_id is None:
        assigned_to_id = actor.id
    if actor is not None and actor.role == "technicien" and assigned_to_id is None and mine != "0":
        assigned_to_id = actor.id
    filters = {
        "status": status,
        "assigned_to_id": assigned_to_id,
        "search": search,
        "overdue": overdue == "1",
    }
    work_orders = service.list(
        status=status or None,
        assigned_to_id=assigned_to_id,
        search=search or None,
        open_only=False,
        corrective=False,
    )
    current_date = today()
    if filters["overdue"]:
        work_orders = [
            work_order
            for work_order in work_orders
            if work_order.due_date is not None
            and work_order.due_date < current_date
            and work_order.status
            not in (WorkOrderStatus.DONE.value, WorkOrderStatus.CANCELLED.value)
        ]
    technicians = UserService(db).list_active()
    from app.models.enums import WorkOrderStatus

    preventive_orders = service.list(corrective=False)
    counts = {
        "all": len(preventive_orders),
        "open": len(service.list(status=WorkOrderStatus.OPEN.value, corrective=False)),
        "assigned": len(
            service.list(status=WorkOrderStatus.ASSIGNED.value, corrective=False)
        ),
        "in_progress": len(
            service.list(status=WorkOrderStatus.IN_PROGRESS.value, corrective=False)
        ),
        "done": len(service.list(status=WorkOrderStatus.DONE.value, corrective=False)),
        "overdue": len(
            [
                work_order
                for work_order in preventive_orders
                if work_order.due_date is not None
                and work_order.due_date < current_date
                and work_order.status
                not in (WorkOrderStatus.DONE.value, WorkOrderStatus.CANCELLED.value)
            ]
        ),
    }
    return render(
        request,
        "work_orders/list.html",
        {
            "work_orders": work_orders,
            "technicians": technicians,
            "statuses": list(WorkOrderStatus),
            "filters": filters,
            "counts": counts,
            "current_user": actor,
            "page_title": "Ordres de travail",
            "mine": mine == "1" or (actor is not None and actor.role == "technicien" and mine != "0"),
        },
    )


@router.post("/work-orders/generate")
async def work_orders_generate(
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    from app.errors import DomainError

    if actor is None or actor.role not in ("responsable", "admin"):
        raise DomainError("Seul un responsable ou un administrateur peut générer des OT.", 403)
    data = await ft.form_data(request)
    try:
        assigned_to_id = ft.as_int(data, "assigned_to_id")
        created, _skipped = WorkOrderService(db).generate_from_schedule(
            assigned_to_id=assigned_to_id, actor=actor
        )
    except DomainError as exc:
        return _redirect("/work-orders", err=exc.message)
    return _redirect("/work-orders", msg=f"{len(created)} OT généré(s) depuis l'échéancier.")


@router.post("/work-orders/{work_order_id}/assign")
async def work_orders_assign(
    work_order_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    from app.errors import DomainError
    from app.schemas.work_order import WorkOrderAssignment

    if actor is None or actor.role not in ("responsable", "admin"):
        raise DomainError("Affectation réservée aux responsables/administrateurs.", 403)
    data = await ft.form_data(request)
    try:
        service = WorkOrderService(db)
        payload = WorkOrderAssignment(assigned_to_id=ft.as_int(data, "assigned_to_id"))
        service.assign(service.get(work_order_id), payload, actor=actor)
    except DomainError as exc:
        return _redirect("/work-orders", err=exc.message)
    return _redirect("/work-orders", msg="OT affecté.")


@router.post("/work-orders/{work_order_id}/take")
async def work_orders_take(
    work_order_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    from app.errors import DomainError

    if actor is None:
        raise DomainError("Connexion requise.", 401)
    try:
        service = WorkOrderService(db)
        service.take(service.get(work_order_id), actor=actor)
    except DomainError as exc:
        return _redirect("/work-orders", err=exc.message)
    return _redirect("/work-orders", msg="OT affecté à vous.")


@router.post("/work-orders/{work_order_id}/status")
async def work_orders_status(
    work_order_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    from app.errors import DomainError
    from app.models.enums import WorkOrderStatus
    from app.schemas.work_order import WorkOrderStatusUpdate

    if actor is None:
        raise DomainError("Connexion requise.", 401)
    data = await ft.form_data(request)
    try:
        service = WorkOrderService(db)
        status_value = ft.text(data, "status", "in_progress") or "in_progress"
        payload = WorkOrderStatusUpdate(status=WorkOrderStatus(status_value))
        service.update_status(service.get(work_order_id), payload, actor=actor)
    except DomainError as exc:
        return _redirect("/work-orders", err=exc.message)
    return _redirect("/work-orders", msg="Statut de l'OT mis à jour.")


# ------------------------------------------------------- maintenance corrective
def _intervention_technicians(db: Session) -> list[User]:
    return [
        user
        for user in UserService(db).list_active()
        if user.role in ("technicien", "responsable", "admin")
    ]


def _intervention_detail_context(
    db: Session, actor: User | None, work_order
) -> dict:
    can_manage = actor is not None and actor.role in ("responsable", "admin")
    can_intervene = actor is not None and (
        can_manage or work_order.assigned_to_id == actor.id
    )
    stock_service = SparePartService(db)
    parts = InterventionService(db).parts(work_order.id)
    replacement_options = {
        item.id: stock_service.replacement_candidates(item.spare_part)
        for item in parts
    }
    return {
        "intervention": work_order,
        "parts": parts,
        "replacement_options": replacement_options,
        "parts_cost": AnalyticsService(db).parts_cost(work_order.id),
        "spare_parts": stock_service.list(active_only=True),
        "technicians": _intervention_technicians(db),
        "can_manage": can_manage,
        "can_intervene": can_intervene,
        "current_user": actor,
        "page_title": f"Intervention {work_order.code}",
    }


@router.get("/interventions")
def interventions_page(
    request: Request,
    status: str | None = None,
    assigned_to_id: OptionalInt = None,
    search: str | None = None,
    mine: str | None = None,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    service = InterventionService(db)
    if mine == "1" and actor is not None and assigned_to_id is None:
        assigned_to_id = actor.id
    interventions = service.list(
        status=status or None,
        assigned_to_id=assigned_to_id,
        search=search or None,
    )
    return render(
        request,
        "interventions/list.html",
        {
            "interventions": interventions,
            "summary": service.summary(),
            "statuses": list(WorkOrderStatus),
            "filters": {
                "status": status or "",
                "assigned_to_id": assigned_to_id,
                "search": search or "",
            },
            "mine": mine == "1",
            "technicians": _intervention_technicians(db),
            "current_user": actor,
            "page_title": "Maintenance corrective",
        },
    )


@router.get("/interventions/new")
def new_intervention_page(
    request: Request,
    equipment_id: OptionalInt = None,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    return render(
        request,
        "interventions/form.html",
        {
            "equipments": EquipmentService(db).list(size=200).items,
            "priorities": list(WorkOrderPriority),
            "selected_equipment_id": equipment_id,
            "current_user": actor,
            "page_title": "Nouvelle demande d'intervention",
        },
    )


@router.post("/interventions")
async def create_intervention_request(
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    data = await ft.form_data(request)
    try:
        equipment_id = ft.as_int(data, "equipment_id")
        if equipment_id is None:
            raise ValueError("L'équipement est obligatoire.")
        payload = InterventionRequestCreate(
            equipment_id=equipment_id,
            description=ft.text(data, "description", "") or "",
            priority=WorkOrderPriority(
                ft.text(data, "priority", WorkOrderPriority.NORMAL.value)
                or WorkOrderPriority.NORMAL.value
            ),
            due_date=ft.as_date(data, "due_date"),
            notes=ft.optional_text(data, "notes"),
        )
        intervention = InterventionService(db).create_request(payload, actor=actor)
    except (DomainError, ValueError) as exc:
        message = exc.message if isinstance(exc, DomainError) else str(exc)
        return _redirect("/interventions/new", err=message)
    return _redirect(
        f"/interventions/{intervention.id}", msg="Demande d'intervention créée."
    )


@router.get("/interventions/{intervention_id}")
def intervention_detail_page(
    intervention_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    work_order = InterventionService(db).get(intervention_id)
    return render(
        request,
        "interventions/detail.html",
        _intervention_detail_context(db, actor, work_order),
    )


@router.post("/interventions/{intervention_id}/assign")
async def assign_intervention(
    intervention_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    data = await ft.form_data(request)
    try:
        service = InterventionService(db)
        service.assign(
            service.get(intervention_id),
            ft.as_int(data, "assigned_to_id"),
            actor=actor,
        )
    except (DomainError, ValueError) as exc:
        message = exc.message if isinstance(exc, DomainError) else str(exc)
        return _redirect(f"/interventions/{intervention_id}", err=message)
    return _redirect(f"/interventions/{intervention_id}", msg="Intervention affectée.")


@router.post("/interventions/{intervention_id}/start")
async def start_intervention(
    intervention_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    data = await ft.form_data(request)
    try:
        service = InterventionService(db)
        service.start(
            service.get(intervention_id),
            InterventionStart(
                started_at=ft.as_datetime(data, "started_at"),
                notes=ft.optional_text(data, "notes"),
            ),
            actor=actor,
        )
    except (DomainError, ValueError) as exc:
        message = exc.message if isinstance(exc, DomainError) else str(exc)
        return _redirect(f"/interventions/{intervention_id}", err=message)
    return _redirect(
        f"/interventions/{intervention_id}", msg="Début d'intervention enregistré."
    )


@router.post("/interventions/{intervention_id}/finish")
async def finish_intervention(
    intervention_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    data = await ft.form_data(request)
    try:
        service = InterventionService(db)
        service.finish(
            service.get(intervention_id),
            InterventionFinish(
                ended_at=ft.as_datetime(data, "ended_at"),
                work_done=ft.text(data, "work_done", "") or "",
                notes=ft.optional_text(data, "notes"),
            ),
            actor=actor,
        )
    except (DomainError, ValueError) as exc:
        message = exc.message if isinstance(exc, DomainError) else str(exc)
        return _redirect(f"/interventions/{intervention_id}", err=message)
    return _redirect(
        f"/interventions/{intervention_id}", msg="Intervention terminée."
    )


@router.post("/interventions/{intervention_id}/cancel")
async def cancel_intervention(
    intervention_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    data = await ft.form_data(request)
    try:
        service = InterventionService(db)
        service.cancel(
            service.get(intervention_id),
            InterventionCancel(reason=ft.optional_text(data, "reason")),
            actor=actor,
        )
    except (DomainError, ValueError) as exc:
        message = exc.message if isinstance(exc, DomainError) else str(exc)
        return _redirect(f"/interventions/{intervention_id}", err=message)
    return _redirect(f"/interventions/{intervention_id}", msg="Intervention annulée.")


@router.post("/interventions/{intervention_id}/parts")
async def request_intervention_part(
    intervention_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    data = await ft.form_data(request)
    try:
        spare_part_id = ft.as_int(data, "spare_part_id")
        if spare_part_id is None:
            raise ValueError("La pièce de rechange est obligatoire.")
        service = InterventionService(db)
        service.request_part(
            service.get(intervention_id),
            InterventionPartCreate(
                spare_part_id=spare_part_id,
                quantity=ft.as_decimal(data, "quantity") or Decimal("0"),
                notes=ft.optional_text(data, "notes"),
            ),
            actor=actor,
        )
    except (DomainError, ValueError) as exc:
        message = exc.message if isinstance(exc, DomainError) else str(exc)
        return _redirect(f"/interventions/{intervention_id}", err=message)
    return _redirect(
        f"/interventions/{intervention_id}", msg="Pièce demandée pour l'intervention."
    )


@router.post("/interventions/{intervention_id}/parts/{part_id}/use")
async def use_intervention_part(
    intervention_id: int,
    part_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    data = await ft.form_data(request)
    try:
        service = InterventionService(db)
        work_order = service.get(intervention_id)
        service.use_part(
            work_order,
            service.get_part(work_order, part_id),
            InterventionPartUse(
                quantity=ft.as_decimal(data, "quantity"),
                replacement_part_id=ft.as_int(data, "replacement_part_id"),
                notes=ft.optional_text(data, "notes"),
            ),
            actor=actor,
        )
    except (DomainError, ValueError) as exc:
        message = exc.message if isinstance(exc, DomainError) else str(exc)
        return _redirect(f"/interventions/{intervention_id}", err=message)
    return _redirect(
        f"/interventions/{intervention_id}", msg="Pièce consommée et sortie du stock."
    )


@router.post("/interventions/{intervention_id}/parts/{part_id}/cancel")
async def cancel_intervention_part(
    intervention_id: int,
    part_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    try:
        service = InterventionService(db)
        work_order = service.get(intervention_id)
        service.cancel_part(
            work_order, service.get_part(work_order, part_id), actor=actor
        )
    except (DomainError, ValueError) as exc:
        message = exc.message if isinstance(exc, DomainError) else str(exc)
        return _redirect(f"/interventions/{intervention_id}", err=message)
    return _redirect(
        f"/interventions/{intervention_id}", msg="Demande de pièce annulée."
    )


# ------------------------------------------------------------------- échéancier
@router.get("/maintenance-schedule")
def maintenance_schedule_page(
    request: Request,
    site_id: OptionalInt = None,
    equipment_type_id: OptionalInt = None,
    supplier_id: OptionalInt = None,
    horizon_days: OptionalInt = None,
    search: str | None = None,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    horizon = horizon_days if horizon_days and horizon_days > 0 else None
    service = MaintenanceScheduleService(db)
    summary = service.summary(
        site_id=site_id,
        equipment_type_id=equipment_type_id,
        supplier_id=supplier_id,
        horizon_days=horizon,
        search=search,
    )
    return render(
        request,
        "maintenance_schedule/list.html",
        {
            "summary": summary,
            "rows": summary.rows,
            "sites": SiteService(db).list(),
            "equipment_types": EquipmentTypeService(db).list(),
            "suppliers": MaintenanceSupplierService(db).list(),
            "users": UserService(db).list_active(),
            "filters": {
                "site_id": site_id,
                "equipment_type_id": equipment_type_id,
                "supplier_id": supplier_id,
                "horizon_days": horizon_days,
                "search": search,
            },
            "current_user": actor,
            "page_title": "Échéancier de maintenance",
        },
    )


# ------------------------------------------------------------------------ audit
@router.get("/audit")
def audit_page(
    request: Request,
    action: str | None = None,
    entity_type: str | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    from app.repositories.audit import AuditRepository

    page = AuditRepository(db).list(
        action=action or None,
        entity_type=entity_type or None,
        search=search or None,
        page=1,
        size=200,
    )
    return render(
        request,
        "audit/list.html",
        {
            "logs": page.items,
            "total": page.total,
            "users": UserService(db).list_active(),
            "current_user": actor,
            "page_title": "Journal d'audit",
        },
    )


# ------------------------------------------------------------------- authentification
@router.get("/login")
def login_page(
    request: Request,
    next: str | None = None,
    db: Session = Depends(get_db),
) -> Response:
    from app.web.templating import render

    users = UserService(db).list_active()
    return render(
        request,
        "auth/login.html",
        {
            "users": users,
            "next": next or "/",
            "page_title": "Connexion",
        },
    )


@router.post("/login")
async def login_submit(
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    from app.services.auth_service import AuthService

    data = await ft.form_data(request)
    username = ft.text(data, "username", "") or ""
    password = ft.text(data, "password", "") or ""
    next_url = ft.text(data, "next", "/") or "/"
    if not next_url.startswith("/"):
        next_url = "/"

    auth = AuthService(db)
    user = auth.verify(username, password)
    if user is None:
        users = UserService(db).list_active()
        return render(
            request,
            "auth/login.html",
            {
                "users": users,
                "next": next_url,
                "page_title": "Connexion",
                "err": "Identifiant ou mot de passe incorrect.",
            },
            status_code=401,
        )

    from app.models.enums import AuditAction
    from app.services.audit_service import AuditService

    AuditService(db).record(
        AuditAction.LOGIN,
        "user",
        user.id,
        actor=user,
        payload={"username": user.username},
    )

    response = _redirect(next_url, msg=f"Connecté : {user.display_name}")
    response.set_cookie(
        cookie_name(),
        encode_user(user.id),
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
    )
    return response


@router.get("/logout")
@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db), actor: User | None = Depends(get_current_user)) -> Response:
    from app.models.enums import AuditAction
    from app.services.audit_service import AuditService

    if actor is not None:
        AuditService(db).record(AuditAction.LOGOUT, "user", actor.id, actor=actor, payload={"username": actor.username})
    response = _redirect("/login", msg="Session fermée.")
    response.delete_cookie(cookie_name())
    return response


# ------------------------------------------------------------------ utilisateur
@router.post("/user/switch")
async def switch_user(request: Request, db: Session = Depends(get_db), actor: User | None = Depends(get_current_user)) -> Response:
    data = await ft.form_data(request)
    username = ft.text(data, "username", "") or ""
    user = UserService(db).resolve(username)
    if user is None:
        return _redirect(_safe_next(request), err="Utilisateur inconnu.")
    from app.models.enums import AuditAction
    from app.services.audit_service import AuditService

    AuditService(db).record(AuditAction.LOGIN, "user", user.id, actor=user, payload={"mode": "switch", "username": user.username})
    response = _redirect(_safe_next(request), msg=f"Utilisateur courant : {user.display_name}")
    response.set_cookie(
        cookie_name(),
        encode_user(user.id),
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
    )
    return response
