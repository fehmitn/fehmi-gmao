"""Hachage de mot de passe (pédagogique, sans dépendance externe)."""

from __future__ import annotations

import hashlib


def hash_password(password: str) -> str:
    # SHA-256 suffit pour ce support pédagogique; en production, utiliser
    # Argon2/bcrypt avec un sel et un facteur de coût.
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    return hash_password(password) == password_hash
