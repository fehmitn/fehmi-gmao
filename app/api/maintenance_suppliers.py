"""Routes API : fournisseurs de maintenance."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.maintenance_supplier import (
    MaintenanceSupplierCreate,
    MaintenanceSupplierRead,
    MaintenanceSupplierUpdate,
)
from app.services.maintenance_supplier_service import MaintenanceSupplierService

router = APIRouter(prefix="/api/maintenance-suppliers", tags=["maintenance-suppliers"])


@router.get("", response_model=list[MaintenanceSupplierRead])
def list_suppliers(
    active_only: bool = False,
    db: Session = Depends(get_db),
) -> list[MaintenanceSupplierRead]:
    service = MaintenanceSupplierService(db)
    return [
        MaintenanceSupplierRead.model_validate(item)
        for item in service.list(active_only=active_only)
    ]


@router.post("", response_model=MaintenanceSupplierRead, status_code=status.HTTP_201_CREATED)
def create_supplier(
    payload: MaintenanceSupplierCreate,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> MaintenanceSupplierRead:
    service = MaintenanceSupplierService(db)
    return MaintenanceSupplierRead.model_validate(service.create(payload, actor=actor))


@router.get("/{supplier_id}", response_model=MaintenanceSupplierRead)
def get_supplier(
    supplier_id: int,
    db: Session = Depends(get_db),
) -> MaintenanceSupplierRead:
    service = MaintenanceSupplierService(db)
    return MaintenanceSupplierRead.model_validate(service.get(supplier_id))


@router.put("/{supplier_id}", response_model=MaintenanceSupplierRead)
def update_supplier(
    supplier_id: int,
    payload: MaintenanceSupplierUpdate,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> MaintenanceSupplierRead:
    service = MaintenanceSupplierService(db)
    supplier = service.update(service.get(supplier_id), payload, actor=actor)
    return MaintenanceSupplierRead.model_validate(supplier)


@router.delete("/{supplier_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_supplier(
    supplier_id: int,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
) -> Response:
    service = MaintenanceSupplierService(db)
    service.delete(service.get(supplier_id), actor=actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
