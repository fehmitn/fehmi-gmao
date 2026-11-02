"""Service de gestion des utilisateurs et des mots de passe."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.errors import ConflictError, NotFoundError, ValidationError
from app.models.enums import AuditAction, UserRole
from app.models.user import User
from app.repositories.user import UserRepository
from app.repositories.work_order import WorkOrderRepository
from app.schemas.user import UserCreate, UserUpdate
from app.services.audit_service import AuditService
from app.services.passwords import hash_password


class UserService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = UserRepository(db)
        self.work_orders = WorkOrderRepository(db)
        self.audit = AuditService(db)

    def list_active(self) -> list[User]:
        return self.repository.list_active()

    def list_all(self) -> list[User]:
        counts = self.work_orders.open_counts_by_user()
        users = self.repository.list_all()
        for user in users:
            user.open_work_order_count = counts.get(user.id, 0)
        return users

    def get(self, user_id: int) -> User:
        user = self.repository.get(user_id)
        if user is None:
            raise NotFoundError(f"Utilisateur {user_id} introuvable.")
        user.open_work_order_count = self.work_orders.open_counts_by_user().get(user.id, 0)
        return user

    def get_by_username(self, username: str) -> User | None:
        return self.repository.get_by_username(username)

    def resolve(self, username: str | None) -> User | None:
        """Utilisateur courant : par identifiant, sinon None (système)."""
        if not username:
            return None
        return self.repository.get_by_username(username)

    def create(
        self,
        payload: UserCreate,
        actor: User | None = None,
    ) -> User:
        username = payload.username.strip()
        if self.repository.get_by_username(username):
            raise ConflictError(f"L'identifiant '{username}' est déjà utilisé.")
        if not payload.password:
            raise ValidationError("Un mot de passe est requis pour un nouvel utilisateur.")
        user = User(
            username=username,
            display_name=payload.display_name.strip(),
            role=UserRole(payload.role).value,
            is_active=payload.is_active,
            password_hash=hash_password(payload.password),
        )
        user = self.repository.add(user)
        self.audit.record(
            AuditAction.CREATE,
            "user",
            user.id,
            actor=actor,
            payload={"username": user.username, "role": user.role},
        )
        return user

    def update(
        self,
        user: User,
        payload: UserUpdate,
        *,
        actor: User | None = None,
        current_user: User | None = None,
    ) -> User:
        data = payload.model_dump(exclude_unset=True)
        if "username" in data and data["username"]:
            username = str(data["username"]).strip()
            existing = self.repository.get_by_username(username)
            if existing is not None and existing.id != user.id:
                raise ConflictError(f"L'identifiant '{username}' est déjà utilisé.")
            user.username = username
        if "display_name" in data and data["display_name"]:
            user.display_name = str(data["display_name"]).strip()
        if "role" in data and data["role"] is not None:
            new_role = UserRole(data["role"])
            if (
                user.role == UserRole.ADMIN.value
                and new_role is not UserRole.ADMIN
                and self._active_admin_count() <= 1
            ):
                raise ValidationError(
                    "Impossible de retirer le dernier administrateur actif."
                )
            user.role = new_role.value
        password = data.pop("password", None)
        if password:
            user.password_hash = hash_password(str(password))
        if "is_active" in data and data["is_active"] is not None:
            if (
                current_user is not None
                and current_user.id == user.id
                and not data["is_active"]
            ):
                raise ValidationError("Vous ne pouvez pas désactiver votre propre compte.")
            if (
                user.role == UserRole.ADMIN.value
                and not data["is_active"]
                and self._active_admin_count() <= 1
            ):
                raise ValidationError(
                    "Impossible de désactiver le dernier administrateur actif."
                )
            user.is_active = bool(data["is_active"])

        user = self.repository.save(user)
        self.audit.record(
            AuditAction.UPDATE,
            "user",
            user.id,
            actor=actor,
            payload={"username": user.username, "role": user.role},
        )
        return user

    def delete(
        self,
        user: User,
        *,
        actor: User | None = None,
        current_user: User | None = None,
    ) -> None:
        if current_user is not None and current_user.id == user.id:
            raise ValidationError("Vous ne pouvez pas supprimer votre propre compte.")
        if user.role == UserRole.ADMIN.value and self._active_admin_count() <= 1:
            raise ValidationError("Impossible de supprimer le dernier administrateur.")
        payload = {"username": user.username}
        user_id = user.id
        self.repository.delete(user)
        self.audit.record(
            AuditAction.DELETE,
            "user",
            user_id,
            actor=actor,
            payload=payload,
        )

    def _active_admin_count(self) -> int:
        return sum(
            1
            for user in self.repository.list_all()
            if user.role == UserRole.ADMIN.value and user.is_active
        )
