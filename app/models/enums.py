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
    SEED = "seed"


class Criticality(StrEnum):
    """Criticité d'un équipement (ABC maintenance)."""

    A = "A"
    B = "B"
    C = "C"
