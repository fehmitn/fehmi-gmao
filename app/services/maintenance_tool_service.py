"""Service des équipements de maintenance (outils et moyens de contrôle).

La fiche d'utilisation d'un outil suit deux contraintes essentielles :

* les **étalonnages périodiques** (registre append-only) qui fixent la
  prochaine échéance légale ;
* les **prêts / utilisation** sur un OT, avec blocage si l'étalonnage est
  manquant ou en retard.

Les unités d'intervalle sont nécessairement calendaires (jours, semaines,
mois, années) : un étalonnage ne peut pas être déclenché par des heures de
fonctionnement.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.errors import ConflictError, NotFoundError, ValidationError
from app.models.enums import (
    AuditAction,
    CalibrationResult,
    CalibrationStatus,
    MaintenanceIntervalUnit,
    ToolStatus,
)
from app.models.maintenance_supplier import MaintenanceSupplier
from app.models.maintenance_tool import (
    MaintenanceTool,
    ToolCalibration,
    ToolUsage,
)
from app.models.site import Site
from app.models.user import User
from app.models.work_order import WorkOrder
from app.repositories.maintenance_tool import MaintenanceToolRepository
from app.schemas.maintenance_tool import (
    CalibrationCreate,
    MaintenanceToolCreate,
    MaintenanceToolUpdate,
    ToolUsageCreate,
    ToolUsageReturn,
)
from app.services.audit_service import AuditService
from app.services.clock import today
from app.services.periodicity import add_interval

CALENDAR_UNITS = (
    MaintenanceIntervalUnit.DAYS,
    MaintenanceIntervalUnit.WEEKS,
    MaintenanceIntervalUnit.MONTHS,
    MaintenanceIntervalUnit.YEARS,
)


class MaintenanceToolService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = MaintenanceToolRepository(db)
        self.audit = AuditService(db)

    # ------------------------------------------------------------------ lecture
    def list(
        self,
        *,
        search: str | None = None,
        status: ToolStatus | str | None = None,
        category: str | None = None,
        active_only: bool = False,
        calibration_status: CalibrationStatus | str | None = None,
    ) -> list[MaintenanceTool]:
        status_value = ToolStatus(status).value if status else None
        tools = self.repository.list(
            search=search,
            status=status_value,
            category=category,
            active_only=active_only,
        )
        if calibration_status:
            target = CalibrationStatus(calibration_status)
            tools = [tool for tool in tools if tool.calibration_status is target]
        return tools

    def get(self, tool_id: int) -> MaintenanceTool:
        tool = self.repository.get(tool_id)
        if tool is None:
            raise NotFoundError(f"Équipement de maintenance {tool_id} introuvable.")
        return tool

    def calibrations(self, tool_id: int) -> list[ToolCalibration]:
        return self.repository.list_calibrations(tool_id)

    def usages(self, tool_id: int) -> list[ToolUsage]:
        return self.repository.list_usages(tool_id)

    def categories(self) -> list[str]:
        return self.repository.categories()

    def summary(self) -> dict[str, int]:
        tools = self.repository.list(active_only=True)
        requires = [tool for tool in tools if tool.requires_calibration]
        return {
            "total": len(tools),
            "requires_calibration": len(requires),
            "valid": sum(
                1 for tool in requires if tool.calibration_status is CalibrationStatus.VALID
            ),
            "due_soon": sum(
                1
                for tool in requires
                if tool.calibration_status is CalibrationStatus.DUE_SOON
            ),
            "overdue": sum(
                1
                for tool in requires
                if tool.calibration_status is CalibrationStatus.OVERDUE
            ),
            "missing": sum(
                1
                for tool in requires
                if tool.calibration_status is CalibrationStatus.MISSING
            ),
            "in_use": sum(
                1 for tool in tools if tool.status == ToolStatus.IN_USE.value
            ),
            "out_of_service": sum(
                1
                for tool in tools
                if tool.status == ToolStatus.OUT_OF_SERVICE.value
            ),
        }

    # ----------------------------------------------------------------- écriture
    def create(
        self, payload: MaintenanceToolCreate, actor: User | None = None
    ) -> MaintenanceTool:
        code = payload.code.strip()
        if self.repository.get_by_code(code):
            raise ConflictError(
                f"Un équipement de maintenance avec le code '{code}' existe déjà."
            )
        unit = self._calendar_unit(payload.calibration_interval_unit)
        self._validate_calibration_configuration(
            payload.requires_calibration,
            payload.calibration_interval_value,
            unit,
        )
        self._check_references(payload.site_id, payload.calibration_provider_id)
        self._check_not_future(payload.last_calibration_date, "date du dernier étalonnage")
        status = ToolStatus(payload.status)
        if status is ToolStatus.IN_USE:
            raise ValidationError(
                "Le statut « En utilisation » est réservé au formulaire de prêt."
            )

        tool = MaintenanceTool(
            code=code,
            name=payload.name.strip(),
            description=payload.description,
            category=payload.category,
            manufacturer=payload.manufacturer,
            model=payload.model,
            serial_number=payload.serial_number,
            site_id=payload.site_id,
            storage_location=payload.storage_location,
            status=status.value,
            requires_calibration=payload.requires_calibration,
            calibration_interval_value=payload.calibration_interval_value,
            calibration_interval_unit=unit.value,
            last_calibration_date=payload.last_calibration_date,
            next_calibration_date=payload.next_calibration_date,
            calibration_provider_id=payload.calibration_provider_id,
            legal_reference=payload.legal_reference,
            purchase_date=payload.purchase_date,
            commissioning_date=payload.commissioning_date,
            is_active=payload.is_active,
            notes=payload.notes,
        )
        if (
            tool.requires_calibration
            and tool.last_calibration_date
            and tool.next_calibration_date is None
        ):
            tool.next_calibration_date = self._compute_next_date(tool)
        tool = self.repository.add(tool)
        self.audit.record(
            AuditAction.CREATE,
            "maintenance_tool",
            tool.id,
            actor=actor,
            payload={"code": tool.code, "name": tool.name},
        )
        return tool

    def update(
        self,
        tool: MaintenanceTool,
        payload: MaintenanceToolUpdate,
        actor: User | None = None,
    ) -> MaintenanceTool:
        data = payload.model_dump(exclude_unset=True)
        calibration_changed = any(
            field in data
            for field in (
                "requires_calibration",
                "calibration_interval_value",
                "calibration_interval_unit",
                "last_calibration_date",
                "next_calibration_date",
            )
        )

        if "code" in data and data["code"]:
            code = str(data["code"]).strip()
            existing = self.repository.get_by_code(code)
            if existing is not None and existing.id != tool.id:
                raise ConflictError(
                    f"Un équipement de maintenance avec le code '{code}' existe déjà."
                )
            tool.code = code
        if "name" in data and data["name"]:
            tool.name = str(data["name"]).strip()

        for field in (
            "description",
            "category",
            "manufacturer",
            "model",
            "serial_number",
            "storage_location",
            "legal_reference",
            "notes",
        ):
            if field in data:
                value = data[field]
                setattr(
                    tool,
                    field,
                    value.strip() if isinstance(value, str) else value,
                )

        if "site_id" in data or "calibration_provider_id" in data:
            site_id = data.get("site_id", tool.site_id)
            provider_id = data.get(
                "calibration_provider_id", tool.calibration_provider_id
            )
            self._check_references(site_id, provider_id)
            tool.site_id = site_id
            tool.calibration_provider_id = provider_id

        if "status" in data and data["status"] is not None:
            new_status = ToolStatus(data["status"])
            self._validate_status_target(tool, new_status)
            tool.status = new_status.value
        if "purchase_date" in data:
            tool.purchase_date = data["purchase_date"]
        if "commissioning_date" in data:
            tool.commissioning_date = data["commissioning_date"]
        if "is_active" in data and data["is_active"] is not None:
            tool.is_active = bool(data["is_active"])
        if "requires_calibration" in data and data["requires_calibration"] is not None:
            tool.requires_calibration = bool(data["requires_calibration"])

        unit = self._calendar_unit(
            data.get("calibration_interval_unit", tool.calibration_interval_unit)
        )
        if "calibration_interval_unit" in data:
            tool.calibration_interval_unit = unit.value
        if "calibration_interval_value" in data:
            tool.calibration_interval_value = data["calibration_interval_value"]
        if "last_calibration_date" in data:
            self._check_not_future(
                data["last_calibration_date"], "date du dernier étalonnage"
            )
            tool.last_calibration_date = data["last_calibration_date"]

        self._validate_calibration_configuration(
            tool.requires_calibration,
            tool.calibration_interval_value,
            unit,
        )

        if calibration_changed:
            explicit_next = data.get("next_calibration_date")
            if explicit_next is not None:
                tool.next_calibration_date = explicit_next
            elif tool.requires_calibration and tool.last_calibration_date:
                tool.next_calibration_date = self._compute_next_date(tool)
            else:
                tool.next_calibration_date = None

        tool = self.repository.save(tool)
        self.audit.record(
            AuditAction.UPDATE,
            "maintenance_tool",
            tool.id,
            actor=actor,
            payload={key: str(value) for key, value in data.items()},
        )
        return tool

    def add_calibration(
        self,
        tool: MaintenanceTool,
        payload: CalibrationCreate,
        actor: User | None = None,
    ) -> ToolCalibration:
        if payload.calibrated_on > today():
            raise ValidationError("La date d'étalonnage ne peut pas être future.")
        self._check_references(tool.site_id, payload.provider_id)

        if tool.requires_calibration:
            unit = self._calendar_unit(tool.calibration_interval_unit)
            self._validate_calibration_configuration(
                True, tool.calibration_interval_value, unit
            )
        else:
            unit = self._calendar_unit(tool.calibration_interval_unit)

        next_due: date | None = None
        if payload.next_due_date is not None:
            if payload.next_due_date <= payload.calibrated_on:
                raise ValidationError(
                    "La prochaine échéance doit être postérieure à la date d'étalonnage."
                )
            next_due = payload.next_due_date
        elif tool.calibration_interval_value:
            try:
                next_due = add_interval(
                    payload.calibrated_on,
                    tool.calibration_interval_value,
                    unit,
                )
            except ValueError as exc:
                raise ValidationError(str(exc)) from exc

        result = CalibrationResult(payload.result)
        calibration = ToolCalibration(
            tool_id=tool.id,
            calibrated_on=payload.calibrated_on,
            next_due_date=next_due,
            provider_id=payload.provider_id,
            certificate_number=payload.certificate_number,
            result=result.value,
            cost=payload.cost,
            notes=payload.notes,
            actor_id=actor.id if actor else None,
        )
        calibration = self.repository.add_calibration(calibration)

        tool.last_calibration_date = payload.calibrated_on
        tool.next_calibration_date = next_due
        if result is CalibrationResult.FAILED:
            tool.status = ToolStatus.OUT_OF_SERVICE.value
        tool = self.repository.save(tool)

        self.audit.record(
            AuditAction.CREATE,
            "tool_calibration",
            calibration.id,
            actor=actor,
            payload={
                "tool": tool.code,
                "calibrated_on": str(calibration.calibrated_on),
                "next_due_date": str(calibration.next_due_date or ""),
                "result": calibration.result,
            },
        )
        return calibration

    def start_usage(
        self,
        tool: MaintenanceTool,
        payload: ToolUsageCreate,
        actor: User | None = None,
    ) -> ToolUsage:
        reason = tool.checkout_block_reason
        if reason:
            raise ConflictError(reason)
        if ToolStatus(tool.status) is ToolStatus.IN_USE or tool.open_usage is not None:
            raise ConflictError(
                f"L'outil '{tool.code}' est déjà en utilisation et n'a pas été restitué."
            )

        started_on = payload.started_on or today()
        if started_on > today():
            raise ValidationError("La date de début d'utilisation ne peut pas être future.")

        if payload.work_order_id is not None:
            work_order = self.db.get(WorkOrder, payload.work_order_id)
            if work_order is None:
                raise NotFoundError(f"Ordre de travail {payload.work_order_id} introuvable.")

        used_by_id = payload.used_by_id if payload.used_by_id is not None else (
            actor.id if actor else None
        )
        if used_by_id is not None:
            user = self.db.get(User, used_by_id)
            if user is None:
                raise NotFoundError(f"Utilisateur {used_by_id} introuvable.")
            if not user.is_active:
                raise ValidationError("Un utilisateur inactif ne peut pas emprunter un outil.")

        usage = ToolUsage(
            tool_id=tool.id,
            work_order_id=payload.work_order_id,
            used_by_id=used_by_id,
            started_on=started_on,
            notes=payload.notes,
        )
        usage = self.repository.add_usage(usage)

        tool.status = ToolStatus.IN_USE.value
        tool = self.repository.save(tool)

        self.audit.record(
            AuditAction.CREATE,
            "tool_usage",
            usage.id,
            actor=actor,
            payload={
                "tool": tool.code,
                "work_order_id": str(usage.work_order_id or ""),
                "started_on": str(usage.started_on),
            },
        )
        return usage

    def end_usage(
        self,
        tool: MaintenanceTool,
        usage: ToolUsage,
        payload: ToolUsageReturn,
        actor: User | None = None,
    ) -> ToolUsage:
        if usage.ended_on is not None:
            raise ConflictError("Cette utilisation est déjà clôturée.")
        ended_on = payload.ended_on or today()
        if ended_on > today():
            raise ValidationError("La date de restitution ne peut pas être future.")
        if ended_on < usage.started_on:
            raise ValidationError(
                "La date de restitution doit être postérieure à la date de début."
            )

        usage.ended_on = ended_on
        if payload.return_notes is not None:
            usage.return_notes = payload.return_notes
        usage = self.repository.save_usage(usage)

        if ToolStatus(tool.status) is ToolStatus.IN_USE:
            tool.status = ToolStatus.AVAILABLE.value
            tool = self.repository.save(tool)
        else:
            tool = self.repository.save(tool)

        self.audit.record(
            AuditAction.UPDATE,
            "tool_usage",
            usage.id,
            actor=actor,
            payload={"tool": tool.code, "ended_on": str(usage.ended_on)},
        )
        return usage

    def set_status(
        self,
        tool: MaintenanceTool,
        status: ToolStatus | str,
        actor: User | None = None,
    ) -> MaintenanceTool:
        target = ToolStatus(status)
        self._validate_status_target(tool, target)
        tool.status = target.value
        tool = self.repository.save(tool)
        self.audit.record(
            AuditAction.UPDATE,
            "maintenance_tool",
            tool.id,
            actor=actor,
            payload={"code": tool.code, "status": target.value},
        )
        return tool

    def delete(self, tool: MaintenanceTool, actor: User | None = None) -> None:
        calibration_count = self.repository.calibration_count(tool.id)
        usage_count = self.repository.usage_count(tool.id)
        if calibration_count or usage_count:
            raise ConflictError(
                f"Impossible de supprimer l'outil '{tool.code}' : "
                f"{calibration_count} étalonnage(s) et {usage_count} utilisation(s) "
                "sont enregistrés. Désactivez-le ou réformez-le plutôt."
            )
        if tool.open_usage is not None:
            raise ConflictError("Impossible de supprimer un outil actuellement utilisé.")
        payload = {"code": tool.code, "name": tool.name}
        tool_id = tool.id
        self.repository.delete(tool)
        self.audit.record(
            AuditAction.DELETE,
            "maintenance_tool",
            tool_id,
            actor=actor,
            payload=payload,
        )

    # ------------------------------------------------------------------ interne
    def _calendar_unit(
        self, unit: MaintenanceIntervalUnit | str | None
    ) -> MaintenanceIntervalUnit:
        try:
            resolved = MaintenanceIntervalUnit(unit or MaintenanceIntervalUnit.MONTHS)
        except ValueError as exc:
            raise ValidationError(f"Unité de périodicité inconnue : {unit}") from exc
        if resolved not in CALENDAR_UNITS:
            raise ValidationError(
                "La périodicité d'étalonnage doit être calendaire : "
                "jours, semaines, mois ou années (les heures de fonctionnement "
                "ne sont pas autorisées)."
            )
        return resolved

    def _validate_calibration_configuration(
        self,
        requires_calibration: bool,
        interval_value: int | None,
        unit: MaintenanceIntervalUnit,
    ) -> None:
        if not requires_calibration:
            return
        if interval_value is None or interval_value <= 0:
            raise ValidationError(
                "Une périodicité d'étalonnage strictement positive est obligatoire "
                "pour un outil soumis à étalonnage."
            )
        if unit not in CALENDAR_UNITS:
            raise ValidationError(
                "La périodicité d'étalonnage doit être calendaire."
            )

    def _compute_next_date(self, tool: MaintenanceTool) -> date:
        if tool.last_calibration_date is None:
            raise ValidationError("La date du dernier étalonnage est obligatoire.")
        if not tool.calibration_interval_value:
            raise ValidationError("La périodicité d'étalonnage est obligatoire.")
        unit = self._calendar_unit(tool.calibration_interval_unit)
        try:
            return add_interval(
                tool.last_calibration_date,
                tool.calibration_interval_value,
                unit,
            )
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

    def _check_references(
        self, site_id: int | None, provider_id: int | None
    ) -> None:
        if site_id is not None and self.db.get(Site, site_id) is None:
            raise NotFoundError(f"Usine {site_id} introuvable.")
        if (
            provider_id is not None
            and self.db.get(MaintenanceSupplier, provider_id) is None
        ):
            raise NotFoundError(f"Fournisseur {provider_id} introuvable.")

    def _check_not_future(self, value: date | None, label: str) -> None:
        if value is not None and value > today():
            raise ValidationError(f"La {label} ne peut pas être future.")

    def _validate_status_target(
        self, tool: MaintenanceTool, target: ToolStatus
    ) -> None:
        if target is ToolStatus.IN_USE and tool.open_usage is None:
            raise ValidationError(
                "Le statut « En utilisation » est réservé au formulaire de prêt."
            )
        if target in (ToolStatus.AVAILABLE, ToolStatus.RETIRED) and tool.open_usage:
            raise ConflictError(
                "Un outil prêté doit d'abord être restitué avant de changer son statut."
            )
