"""Dépendances partagées par les routes API."""

from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.config import CURRENT_USER_COOKIE
from app.database import get_db
from app.models.user import User
from app.services.user_service import UserService
from app.web.session import decode_user


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User | None:
    """Utilisateur courant (session web signée ou en-tête X-GMAO-User pour l'API)."""
    cached = getattr(request.state, "current_user", None)
    if cached is not None:
        return cached
    user_id = decode_user(request.cookies.get(CURRENT_USER_COOKIE))
    if user_id is not None:
        user = UserService(db).repository.get(user_id)
        if user is not None and user.is_active:
            request.state.current_user = user
            return user
    username = request.headers.get("X-GMAO-User")
    user = UserService(db).resolve(username)
    if user is not None and user.is_active:
        request.state.current_user = user
    return user if user and user.is_active else None
