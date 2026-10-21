"""Service utilisateurs (authentification légère par simple sélection)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories.user import UserRepository


class UserService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = UserRepository(db)

    def list_active(self) -> list[User]:
        return self.repository.list_active()

    def get_by_username(self, username: str) -> User | None:
        return self.repository.get_by_username(username)

    def resolve(self, username: str | None) -> User | None:
        """Utilisateur courant : par identifiant, sinon None (système)."""
        if not username:
            return None
        return self.repository.get_by_username(username)
