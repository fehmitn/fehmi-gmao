"""Signature et lecture du cookie de session utilisateur."""

from __future__ import annotations

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import CURRENT_USER_COOKIE, SESSION_MAX_AGE_SECONDS, SESSION_SECRET

_serializer = URLSafeTimedSerializer(SESSION_SECRET, salt="gmao-session")


def encode_user(user_id: int) -> str:
    return _serializer.dumps({"user_id": user_id})


def decode_user(token: str | None) -> int | None:
    if not token:
        return None
    try:
        payload = _serializer.loads(token, max_age=SESSION_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(payload, dict):
        return None
    user_id = payload.get("user_id")
    return int(user_id) if isinstance(user_id, int) else None


def cookie_name() -> str:
    return CURRENT_USER_COOKIE
