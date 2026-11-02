"""Énumérations métier partagées entre les modèles, schémas et services."""

from enum import StrEnum


class EquipmentStatus(StrEnum):
    """État opérationnel d'un équipement (traduit de la notion WinMaint d'article installé)."""

    OPERATIONAL = "operational"
    MAINTENANCE = "maintenance"
    DOWN = "down"
    RETIRED = "retired"
    SCRAPPED = "scrapped"


class MovementType(StrEnum):
    """Nature d'un mouvement d'implantation d'un équipement."""

    INSTALLATION = "installation"
    DEPLACEMENT = "deplacement"
    TRANSFERT = "transfert"
    RETRAIT = "retrait"


class UserRole(StrEnum):
    """Rôles applicatifs (gestion des permissions façon WinMaint)."""

    ADMIN = "admin"
    RESPONSABLE = "responsable"
    TECHNICIEN = "technicien"
    LECTURE = "lecture"


class AuditAction(StrEnum):
    """Actions journalisées dans la piste d'audit."""

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    MOVE = "move"
    BACKDATE = "backdate"
    EXECUTE = "execute"
    SEED = "seed"
    LOGIN = "login"
    LOGOUT = "logout"


class MaintenanceIntervalUnit(StrEnum):
    """Unité de la périodicité d'une opération de maintenance préventive."""

    DAYS = "days"
    WEEKS = "weeks"
    MONTHS = "months"
    YEARS = "years"
    HOURS = "hours"

    @property
    def label(self) -> str:
        return {
            MaintenanceIntervalUnit.DAYS: "jour(s)",
            MaintenanceIntervalUnit.WEEKS: "semaine(s)",
            MaintenanceIntervalUnit.MONTHS: "mois",
            MaintenanceIntervalUnit.YEARS: "année(s)",
            MaintenanceIntervalUnit.HOURS: "heure(s) de fonctionnement",
        }[self]


class MaintenanceType(StrEnum):
    """Nature d'une opération de maintenance périodique."""

    PREVENTIVE_SYSTEMATIC = "preventive_systematic"
    PREVENTIVE_CONDITIONAL = "preventive_conditional"
    REGULATORY = "regulatory"
    INSPECTION = "inspection"

    @property
    def label(self) -> str:
        return {
            MaintenanceType.PREVENTIVE_SYSTEMATIC: "Préventive systématique",
            MaintenanceType.PREVENTIVE_CONDITIONAL: "Préventive conditionnelle",
            MaintenanceType.REGULATORY: "Réglementaire",
            MaintenanceType.INSPECTION: "Inspection",
        }[self]


class MaintenanceAnchor(StrEnum):
    """Point de départ du calcul des échéances d'une opération."""

    COMMISSIONING = "commissioning"
    FIRST_PLACEMENT = "first_placement"
    FIXED_DATE = "fixed_date"

    @property
    def label(self) -> str:
        return {
            MaintenanceAnchor.COMMISSIONING: "Mise en service de l'équipement",
            MaintenanceAnchor.FIRST_PLACEMENT: "Première implantation",
            MaintenanceAnchor.FIXED_DATE: "Date fixe (première échéance)",
        }[self]


class Criticality(StrEnum):
    """Criticité d'un équipement (ABC maintenance)."""

    A = "A"
    B = "B"
    C = "C"


class WorkOrderStatus(StrEnum):
    """État d'un ordre de travail."""

    OPEN = "open"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"

    @property
    def label(self) -> str:
        return {
            WorkOrderStatus.OPEN: "Ouvert",
            WorkOrderStatus.ASSIGNED: "Affecté",
            WorkOrderStatus.IN_PROGRESS: "En cours",
            WorkOrderStatus.DONE: "Terminé",
            WorkOrderStatus.CANCELLED: "Annulé",
        }[self]

    @property
    def css(self) -> str:
        return {
            WorkOrderStatus.OPEN: "text-bg-danger",
            WorkOrderStatus.ASSIGNED: "text-bg-warning",
            WorkOrderStatus.IN_PROGRESS: "text-bg-info",
            WorkOrderStatus.DONE: "text-bg-success",
            WorkOrderStatus.CANCELLED: "text-bg-secondary",
        }[self]


class WorkOrderPriority(StrEnum):
    """Priorité d'un ordre de travail."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"

    @property
    def label(self) -> str:
        return {
            WorkOrderPriority.LOW: "Basse",
            WorkOrderPriority.NORMAL: "Normale",
            WorkOrderPriority.HIGH: "Haute",
            WorkOrderPriority.URGENT: "Urgente",
        }[self]


class InterventionPartStatus(StrEnum):
    """État d'une pièce demandée pour une intervention corrective."""

    REQUESTED = "requested"
    USED = "used"
    CANCELLED = "cancelled"

    @property
    def label(self) -> str:
        return {
            InterventionPartStatus.REQUESTED: "Demandée",
            InterventionPartStatus.USED: "Utilisée",
            InterventionPartStatus.CANCELLED: "Annulée",
        }[self]

    @property
    def css(self) -> str:
        return {
            InterventionPartStatus.REQUESTED: "text-bg-warning",
            InterventionPartStatus.USED: "text-bg-success",
            InterventionPartStatus.CANCELLED: "text-bg-secondary",
        }[self]


class StockMovementType(StrEnum):
    """Nature d'un mouvement de stock d'une pièce de rechange."""

    ENTRY = "entry"
    EXIT = "exit"
    INVENTORY = "inventory"

    @property
    def label(self) -> str:
        return {
            StockMovementType.ENTRY: "Entrée",
            StockMovementType.EXIT: "Sortie",
            StockMovementType.INVENTORY: "Inventaire",
        }[self]

    @property
    def css(self) -> str:
        return {
            StockMovementType.ENTRY: "text-bg-success",
            StockMovementType.EXIT: "text-bg-danger",
            StockMovementType.INVENTORY: "text-bg-info",
        }[self]


class ToolStatus(StrEnum):
    """Disponibilité d'un équipement de maintenance / outil."""

    AVAILABLE = "available"
    IN_USE = "in_use"
    MAINTENANCE = "maintenance"
    OUT_OF_SERVICE = "out_of_service"
    RETIRED = "retired"

    @property
    def label(self) -> str:
        return {
            ToolStatus.AVAILABLE: "Disponible",
            ToolStatus.IN_USE: "En utilisation",
            ToolStatus.MAINTENANCE: "En maintenance",
            ToolStatus.OUT_OF_SERVICE: "Hors service",
            ToolStatus.RETIRED: "Réformé",
        }[self]

    @property
    def css(self) -> str:
        return {
            ToolStatus.AVAILABLE: "text-bg-success",
            ToolStatus.IN_USE: "text-bg-info",
            ToolStatus.MAINTENANCE: "text-bg-warning",
            ToolStatus.OUT_OF_SERVICE: "text-bg-danger",
            ToolStatus.RETIRED: "text-bg-secondary",
        }[self]


class CalibrationResult(StrEnum):
    """Résultat d'un étalonnage / vérification."""

    PASSED = "passed"
    ADJUSTED = "adjusted"
    FAILED = "failed"

    @property
    def label(self) -> str:
        return {
            CalibrationResult.PASSED: "Conforme",
            CalibrationResult.ADJUSTED: "Ajusté",
            CalibrationResult.FAILED: "Non conforme",
        }[self]

    @property
    def css(self) -> str:
        return {
            CalibrationResult.PASSED: "text-bg-success",
            CalibrationResult.ADJUSTED: "text-bg-warning",
            CalibrationResult.FAILED: "text-bg-danger",
        }[self]


class CalibrationStatus(StrEnum):
    """État calculé de la contrainte légale d'étalonnage."""

    NOT_REQUIRED = "not_required"
    MISSING = "missing"
    VALID = "valid"
    DUE_SOON = "due_soon"
    OVERDUE = "overdue"

    @property
    def label(self) -> str:
        return {
            CalibrationStatus.NOT_REQUIRED: "Non soumis",
            CalibrationStatus.MISSING: "À étalonner",
            CalibrationStatus.VALID: "À jour",
            CalibrationStatus.DUE_SOON: "À prévoir",
            CalibrationStatus.OVERDUE: "En retard",
        }[self]

    @property
    def css(self) -> str:
        return {
            CalibrationStatus.NOT_REQUIRED: "text-bg-secondary",
            CalibrationStatus.MISSING: "text-bg-warning",
            CalibrationStatus.VALID: "text-bg-success",
            CalibrationStatus.DUE_SOON: "text-bg-warning",
            CalibrationStatus.OVERDUE: "text-bg-danger",
        }[self]
