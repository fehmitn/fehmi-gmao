"""Service des implantations d'équipements (historique des déplacements).

C'est le service qui porte la notion de « où était l'équipement à telle
date » : indispensable pour rattacher une intervention saisie a posteriori
au bon emplacement.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.errors import NotFoundError, ValidationError
from app.models.equipment import Equipment
from app.models.equipment_location import EquipmentLocation
from app.models.enums import AuditAction, MovementType
from app.models.location import Location
from app.models.user import User
from app.repositories.equipment_location import EquipmentLocationRepository
from app.repositories.equipment import EquipmentRepository
from app.repositories.location import LocationRepository
from app.schemas.equipment import PlacementCreate
from app.services.audit_service import AuditService
from app.services.backdating import BackdatingPolicy
from app.services.clock import now, today


class PlacementService:
    def __init__(self, db: Session, policy: BackdatingPolicy | None = None) -> None:
        self.db = db
        self.repository = EquipmentLocationRepository(db)
        self.equipment_repository = EquipmentRepository(db)
        self.location_repository = LocationRepository(db)
        self.audit = AuditService(db)
        self.policy = policy or BackdatingPolicy()

    # ------------------------------------------------------------------ lecture
    def history(self, equipment_id: int) -> list[EquipmentLocation]:
        return self.repository.list_for_equipment(equipment_id)

    def current(self, equipment_id: int) -> EquipmentLocation | None:
        return self.repository.current(equipment_id)

    def at_date(self, equipment_id: int, day: date) -> EquipmentLocation | None:
        """Implantation effective au jour donné (réponse à la rétrodatation)."""
        return self.repository.at_date(equipment_id, day)

    def enrich(self, placement: EquipmentLocation) -> EquipmentLocation:
        location = self.location_repository.get(placement.location_id)
        placement.location_code = location.code if location else None
        placement.location_name = location.name if location else None
        placement.location_path = self.location_repository.path(placement.location_id)
        placement.is_current = placement.effective_to is None
        return placement

    # ------------------------------------------------------------------ écriture
    def install(
        self,
        equipment: Equipment,
        location: Location,
        *,
        effective_from: date | None = None,
        reason: str | None = None,
        derogation_reason: str | None = None,
        actor: User | None = None,
    ) -> EquipmentLocation:
        """Ouvre la première période d'implantation d'un équipement."""
        effective_from = effective_from or today()
        decision = self.policy.enforce(
            effective_from,
            derogation_reason,
            minimum_date=equipment.commissioning_date,
            minimum_label="la mise en service",
        )
        placement = EquipmentLocation(
            equipment_id=equipment.id,
            location_id=location.id,
            effective_from=effective_from,
            effective_to=None,
            movement_type=MovementType.INSTALLATION.value,
            reason=reason,
            recorded_at=now(),
            entry_delay_days=decision.delay_days or None,
            derogation_reason=decision.derogation_reason,
            created_by=actor.id if actor is not None else None,
        )
        self.repository.add(placement)
        self._audit_backdating(decision, equipment, "installation", actor)
        return placement

    def move(
        self,
        equipment: Equipment,
        payload: PlacementCreate,
        actor: User | None = None,
    ) -> EquipmentLocation:
        """Déplace un équipement vers un nouvel emplacement à une date d'effet.

        Cas particulier : si l'équipement n'a encore aucune implantation (par
        exemple un équipement hérité de la version 0.1), le déplacement joue
        le rôle de l'installation initiale.
        """
        current = self.current(equipment.id)
        location = self.location_repository.get(payload.location_id)
        if location is None:
            raise NotFoundError(f"Emplacement {payload.location_id} introuvable.")
        if current is not None and location.id == current.location_id:
            raise ValidationError(
                "L'équipement est déjà implanté dans cet emplacement."
            )

        effective_from = payload.effective_from or today()
        if current is not None:
            if effective_from < current.effective_from:
                raise ValidationError(
                    "La date d'effet du déplacement doit être postérieure à la date "
                    f"d'implantation en cours ({current.effective_from.isoformat()}). "
                    "Les déplacements s'enchaînent chronologiquement."
                )

            decision = self.policy.enforce(
                effective_from,
                payload.derogation_reason,
                minimum_date=current.effective_from,
                minimum_label="l'implantation en cours",
            )

            # On ferme la période en cours la veille du déplacement (le jour même
            # si le déplacement est daté du jour de l'implantation).
            current.effective_to = (
                effective_from
                if effective_from == current.effective_from
                else effective_from - timedelta(days=1)
            )
            self.repository.save(current)
            movement_type = str(payload.movement_type)
        else:
            # Première implantation : la date d'effet ne peut pas précéder la
            # mise en service de l'équipement.
            decision = self.policy.enforce(
                effective_from,
                payload.derogation_reason,
                minimum_date=equipment.commissioning_date,
                minimum_label="la mise en service",
            )
            movement_type = MovementType.INSTALLATION.value

        placement = EquipmentLocation(
            equipment_id=equipment.id,
            location_id=location.id,
            effective_from=effective_from,
            effective_to=None,
            movement_type=movement_type,
            reason=payload.reason,
            recorded_at=now(),
            entry_delay_days=decision.delay_days or None,
            derogation_reason=decision.derogation_reason,
            created_by=actor.id if actor is not None else None,
        )
        self.repository.add(placement)

        # L'équipement change d'usine si l'emplacement est dans une autre usine.
        if equipment.site_id != location.site_id:
            equipment.site_id = location.site_id
            self.equipment_repository.save(equipment)

        self.audit.record(
            AuditAction.MOVE,
            "equipment",
            equipment.id,
            actor=actor,
            reason=payload.reason,
            payload={
                "code": equipment.code,
                "from_location_id": str(current.location_id) if current else None,
                "to_location_id": str(location.id),
                "to_location": self.location_repository.path(location.id),
                "effective_from": effective_from.isoformat(),
                "entry_delay_days": str(decision.delay_days),
                "movement_type": movement_type,
            },
        )
        self._audit_backdating(decision, equipment, "déplacement", actor)
        return placement

    # ------------------------------------------------------------------ interne
    def _audit_backdating(
        self,
        decision,
        equipment: Equipment,
        context: str,
        actor: User | None,
    ) -> None:
        if not decision.is_backdated:
            return
        self.audit.record(
            AuditAction.BACKDATE,
            "equipment",
            equipment.id,
            actor=actor,
            reason=decision.derogation_reason,
            payload={
                "context": context,
                "code": equipment.code,
                **decision.fingerprint,
            },
        )
