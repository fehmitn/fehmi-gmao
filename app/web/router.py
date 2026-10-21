"""Routes web (Jinja2 + HTMX)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.config import CURRENT_USER_COOKIE
from app.database import get_db
from app.errors import DomainError
from app.models.enums import EquipmentStatus, MovementType
from app.models.user import User
from app.repositories.location_type import LocationTypeRepository
from app.schemas.equipment import EquipmentCreate, EquipmentUpdate, PlacementCreate
from app.schemas.equipment_type import EquipmentTypeCreate, EquipmentTypeUpdate
from app.schemas.location import LocationCreate, LocationUpdate
from app.schemas.site import SiteCreate, SiteUpdate
from app.services.dashboard_service import DashboardService
from app.services.equipment_service import EquipmentService
from app.services.equipment_type_service import EquipmentTypeService
from app.services.location_service import LocationService
from app.services.placement_service import PlacementService
from app.services.site_service import SiteService
from app.services.user_service import UserService
from app.web import formtools as ft
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
    users = UserService(db).list_active()
    return render(
        request,
        "dashboard.html",
        {
            "stats": stats,
            "backdates": backdates,
            "users": users,
            "current_user": actor,
            "page_title": "Tableau de bord",
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
    site_id: int | None = None,
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
    site_id: int | None = None,
    location_id: int | None = None,
    equipment_type_id: int | None = None,
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
    site_id: int | None = None,
    location_id: int | None = None,
    equipment_type_id: int | None = None,
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
    site_id: int | None = None,
    location_id: int | None = None,
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
    return render(
        request,
        "equipments/detail.html",
        {
            "equipment": equipment,
            "history": history,
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
        PlacementService(db).move(equipment, payload, actor=actor)
    except (DomainError, ValueError) as exc:
        message = exc.message if isinstance(exc, DomainError) else str(exc)
        return _redirect(f"/equipments/{equipment_id}", err=message)
    return _redirect(f"/equipments/{equipment_id}", msg="Déplacement enregistré.")


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


# ------------------------------------------------------------------ utilisateur
@router.post("/user/switch")
async def switch_user(request: Request, db: Session = Depends(get_db)) -> Response:
    data = await ft.form_data(request)
    username = ft.text(data, "username", "") or ""
    user = UserService(db).resolve(username)
    if user is None:
        return _redirect(_safe_next(request), err="Utilisateur inconnu.")
    response = _redirect(_safe_next(request), msg=f"Utilisateur courant : {user.display_name}")
    response.set_cookie(
        CURRENT_USER_COOKIE,
        user.username,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 30,
    )
    return response
