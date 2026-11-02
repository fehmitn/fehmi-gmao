"""Service de gestion des pièces de rechange et de leur stock."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.errors import ConflictError, NotFoundError, ValidationError
from app.models.enums import AuditAction, StockMovementType
from app.models.maintenance_supplier import MaintenanceSupplier
from app.models.site import Site
from app.models.spare_part import SparePart, StockMovement
from app.models.spare_part_interchange import SparePartInterchange
from app.models.user import User
from app.models.work_order import WorkOrder
from app.repositories.spare_part import SparePartRepository
from app.schemas.spare_part import (
    SparePartCreate,
    SparePartUpdate,
    StockMovementCreate,
)
from app.services.audit_service import AuditService
from app.services.clock import today


class SparePartService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = SparePartRepository(db)
        self.audit = AuditService(db)

    # ------------------------------------------------------------------ lecture
    def list(
        self,
        *,
        search: str | None = None,
        category: str | None = None,
        low_stock_only: bool = False,
        active_only: bool = False,
    ) -> list[SparePart]:
        parts = self.repository.list(
            search=search,
            category=category,
            low_stock_only=low_stock_only,
            active_only=active_only,
        )
        counts = self.repository.movement_counts()
        for part in parts:
            part.movement_count = counts.get(part.id, 0)
        return parts

    def get(self, spare_part_id: int) -> SparePart:
        part = self.repository.get(spare_part_id)
        if part is None:
            raise NotFoundError(f"Pièce de rechange {spare_part_id} introuvable.")
        part.movement_count = self.repository.movement_counts().get(part.id, 0)
        return part

    def movements(self, spare_part_id: int, limit: int | None = None) -> list[StockMovement]:
        return self.repository.list_movements(spare_part_id, limit=limit)

    def categories(self) -> list[str]:
        return self.repository.categories()

    def summary(self) -> dict[str, object]:
        return {
            "total": len(self.repository.list(active_only=True)),
            "low_stock": self.repository.low_stock_count(),
            "out_of_stock": self.repository.out_of_stock_count(),
            "stock_value": self.repository.total_value(),
        }

    # -------------------------------------------------------------- compatibilités
    def interchanges(self, part: SparePart) -> list[SparePartInterchange]:
        """Pièces que celle-ci peut remplacer."""
        return self.repository.list_interchanges(part.id)

    def replacements(self, part: SparePart) -> list[SparePartInterchange]:
        """Pièces qui peuvent remplacer celle-ci."""
        return self.repository.list_replacements(part.id)

    def replacement_candidates(self, part: SparePart) -> list[SparePart]:
        """Pièces actives autorisées à remplacer ``part`` au moment de l'usage."""
        candidates = []
        for interchange in self.repository.list_replacements(part.id):
            candidate = interchange.part
            if candidate is None or not candidate.is_active:
                continue
            if candidate.id == part.id:
                continue
            candidates.append(candidate)
        candidates.sort(key=lambda item: item.code)
        return candidates

    def add_interchange(
        self,
        part: SparePart,
        replaces_id: int,
        *,
        note: str | None = None,
        actor: User | None = None,
    ) -> SparePartInterchange:
        replaces = self.repository.get(replaces_id)
        if replaces is None:
            raise NotFoundError(f"Pièce de rechange {replaces_id} introuvable.")
        if replaces.id == part.id:
            raise ValidationError("Une pièce ne peut pas se remplacer elle-même.")
        if replaces.unit.strip().casefold() != part.unit.strip().casefold():
            raise ValidationError(
                "La pièce de remplacement et la pièce remplacée doivent avoir "
                f"la même unité ({part.unit} ≠ {replaces.unit})."
            )
        if self.repository.find_interchange(part.id, replaces.id) is not None:
            raise ConflictError(
                f"La compatibilité '{part.code} remplace {replaces.code}' existe déjà."
            )

        interchange = SparePartInterchange(
            part_id=part.id,
            replaces_id=replaces.id,
            note=note,
        )
        interchange = self.repository.add_interchange(interchange)
        self.audit.record(
            AuditAction.CREATE,
            "spare_part_interchange",
            interchange.id,
            actor=actor,
            payload={
                "part": part.code,
                "replaces": replaces.code,
                "note": note or "",
            },
        )
        return interchange

    def remove_interchange(
        self,
        part: SparePart,
        interchange_id: int,
        actor: User | None = None,
    ) -> None:
        interchange = self.repository.get_interchange(interchange_id)
        if interchange is None or part.id not in (
            interchange.part_id,
            interchange.replaces_id,
        ):
            raise NotFoundError(
                f"Compatibilité {interchange_id} introuvable pour '{part.code}'."
            )
        payload = {
            "part": interchange.part_code,
            "replaces": interchange.replaces_code,
        }
        self.repository.delete_interchange(interchange)
        self.audit.record(
            AuditAction.DELETE,
            "spare_part_interchange",
            interchange_id,
            actor=actor,
            payload=payload,
        )

    def is_compatible_replacement(
        self, candidate: SparePart, requested: SparePart
    ) -> bool:
        """True si ``candidate`` peut remplacer ``requested``."""
        if candidate.id == requested.id:
            return True
        return (
            self.repository.find_interchange(candidate.id, requested.id) is not None
        )

    # ----------------------------------------------------------------- écriture
    def create(
        self, payload: SparePartCreate, actor: User | None = None
    ) -> SparePart:
        code = payload.code.strip()
        if self.repository.get_by_code(code):
            raise ConflictError(f"Une pièce avec le code '{code}' existe déjà.")
        self._check_references(payload.supplier_id, payload.site_id)
        self._check_thresholds(payload.min_quantity, payload.max_quantity)

        part = SparePart(
            code=code,
            name=payload.name.strip(),
            description=payload.description,
            category=payload.category,
            unit=payload.unit.strip() or "pièce",
            manufacturer=payload.manufacturer,
            manufacturer_reference=payload.manufacturer_reference,
            supplier_id=payload.supplier_id,
            site_id=payload.site_id,
            storage_location=payload.storage_location,
            quantity=Decimal("0"),
            min_quantity=payload.min_quantity,
            max_quantity=payload.max_quantity,
            unit_cost=payload.unit_cost,
            is_active=payload.is_active,
            notes=payload.notes,
        )
        part = self.repository.add(part)
        self.audit.record(
            AuditAction.CREATE,
            "spare_part",
            part.id,
            actor=actor,
            payload={"code": part.code, "name": part.name},
        )
        if payload.quantity and payload.quantity > 0:
            self.record_movement(
                part,
                StockMovementCreate(
                    movement_type=StockMovementType.ENTRY,
                    quantity=payload.quantity,
                    reference="Stock initial",
                    notes="Quantité constatée à la création de la fiche.",
                ),
                actor=actor,
            )
        return self.get(part.id)

    def update(
        self,
        part: SparePart,
        payload: SparePartUpdate,
        actor: User | None = None,
    ) -> SparePart:
        data = payload.model_dump(exclude_unset=True)
        if "code" in data and data["code"]:
            code = str(data["code"]).strip()
            existing = self.repository.get_by_code(code)
            if existing is not None and existing.id != part.id:
                raise ConflictError(f"Une pièce avec le code '{code}' existe déjà.")
            part.code = code
        if "name" in data and data["name"]:
            part.name = str(data["name"]).strip()
        if "unit" in data and data["unit"]:
            part.unit = str(data["unit"]).strip() or "pièce"
        for field in (
            "description",
            "category",
            "manufacturer",
            "manufacturer_reference",
            "storage_location",
            "notes",
        ):
            if field in data:
                value = data[field]
                setattr(
                    part,
                    field,
                    value.strip() if isinstance(value, str) else value,
                )
        if "supplier_id" in data or "site_id" in data:
            supplier_id = data.get("supplier_id", part.supplier_id)
            site_id = data.get("site_id", part.site_id)
            self._check_references(supplier_id, site_id)
            part.supplier_id = supplier_id
            part.site_id = site_id
        if "min_quantity" in data and data["min_quantity"] is not None:
            part.min_quantity = data["min_quantity"]
        if "max_quantity" in data:
            part.max_quantity = data["max_quantity"]
        if "unit_cost" in data:
            part.unit_cost = data["unit_cost"]
        if "is_active" in data and data["is_active"] is not None:
            part.is_active = bool(data["is_active"])
        self._check_thresholds(part.min_quantity, part.max_quantity)

        part = self.repository.save(part)
        self.audit.record(
            AuditAction.UPDATE,
            "spare_part",
            part.id,
            actor=actor,
            payload={key: str(value) for key, value in data.items()},
        )
        return part

    def record_movement(
        self,
        part: SparePart,
        payload: StockMovementCreate,
        actor: User | None = None,
    ) -> StockMovement:
        movement_type = StockMovementType(payload.movement_type)
        movement_date = payload.movement_date or today()
        if movement_date > today():
            raise ValidationError("La date d'un mouvement de stock ne peut pas être future.")

        quantity = Decimal(payload.quantity)
        if quantity < 0:
            raise ValidationError("La quantité doit être positive ou nulle.")
        if movement_type in (StockMovementType.ENTRY, StockMovementType.EXIT) and quantity <= 0:
            raise ValidationError("La quantité d'une entrée ou d'une sortie doit être positive.")

        current = part.quantity or Decimal("0")
        if movement_type is StockMovementType.ENTRY:
            resulting = current + quantity
            delta = quantity
        elif movement_type is StockMovementType.EXIT:
            if quantity > current:
                raise ConflictError(
                    f"Stock insuffisant pour '{part.code}' : "
                    f"disponible {current:g} {part.unit}, demandé {quantity:g}."
                )
            resulting = current - quantity
            delta = -quantity
        else:  # inventaire
            resulting = quantity
            delta = quantity - current

        if payload.work_order_id is not None:
            work_order = self.db.get(WorkOrder, payload.work_order_id)
            if work_order is None:
                raise NotFoundError(f"Ordre de travail {payload.work_order_id} introuvable.")

        part.quantity = resulting
        movement = StockMovement(
            spare_part_id=part.id,
            movement_type=movement_type.value,
            quantity=quantity,
            quantity_delta=delta,
            resulting_quantity=resulting,
            movement_date=movement_date,
            unit_cost=part.unit_cost,
            reference=payload.reference,
            notes=payload.notes,
            work_order_id=payload.work_order_id,
            actor_id=actor.id if actor else None,
        )
        movement = self.repository.add_movement(movement)
        self.repository.save(part)
        self.audit.record(
            AuditAction.UPDATE,
            "stock_movement",
            movement.id,
            actor=actor,
            payload={
                "spare_part": part.code,
                "type": movement_type.value,
                "quantity": str(quantity),
                "resulting_quantity": str(resulting),
                "work_order_id": str(payload.work_order_id or ""),
            },
        )
        return movement

    def delete(self, part: SparePart, actor: User | None = None) -> None:
        count = self.repository.movement_counts().get(part.id, 0)
        if count:
            raise ConflictError(
                f"Impossible de supprimer la pièce '{part.code}' : "
                f"{count} mouvement(s) de stock sont enregistrés. "
                "Désactivez-la plutôt."
            )
        payload = {"code": part.code, "name": part.name}
        part_id = part.id
        self.repository.delete(part)
        self.audit.record(
            AuditAction.DELETE,
            "spare_part",
            part_id,
            actor=actor,
            payload=payload,
        )

    # ------------------------------------------------------------------ interne
    def _check_references(
        self, supplier_id: int | None, site_id: int | None
    ) -> None:
        if supplier_id is not None and self.db.get(MaintenanceSupplier, supplier_id) is None:
            raise NotFoundError(f"Fournisseur {supplier_id} introuvable.")
        if site_id is not None and self.db.get(Site, site_id) is None:
            raise NotFoundError(f"Usine {site_id} introuvable.")

    def _check_thresholds(
        self, min_quantity: Decimal | None, max_quantity: Decimal | None
    ) -> None:
        if (
            max_quantity is not None
            and min_quantity is not None
            and max_quantity < min_quantity
        ):
            raise ValidationError(
                "Le stock maximum doit être supérieur ou égal au seuil minimum."
            )
