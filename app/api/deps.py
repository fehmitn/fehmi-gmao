"""Dépendances partagées par les routes API."""

from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.config import CURRENT_USER_COOKIE
from app.database import get_db
from app.models.user import User
from app.services.user_service import UserService


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User | None:
    """Utilisateur courant (cookie web ou en-tête X-GMAO-User pour l'API).

    L'itération 1 utilise une sélection d'utilisateur sans mot de passe :
    l'objectif est pédagogique (voir qui saisit quoi dans l'audit), pas
    d'authentification forte.
    """
    username = request.cookies.get(CURRENT_USER_COOKIE) or request.headers.get(
        "X-GMAO-User"
    )
    return UserService(db).resolve(username)
