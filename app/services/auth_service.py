from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories.user import UserRepository
from app.services.passwords import hash_password, verify_password


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.users = UserRepository(db)

    def verify(self, username: str, password: str) -> Optional[User]:
        user = self.users.get_by_username(username.strip())
        if not user or not user.is_active:
            return None
        if not verify_password(password, user.password_hash):
            return None
        return user

    def set_password(self, user: User, password: str) -> User:
        user.password_hash = hash_password(password)
        return self.users.save(user)
