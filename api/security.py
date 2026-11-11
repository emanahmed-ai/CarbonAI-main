"""JWT token helpers. The signing secret comes from CARBONAI_JWT_SECRET, or is generated once and
persisted in the settings table so tokens survive restarts."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from api.config import JWT_ALGORITHM, TOKEN_MINUTES
from db.connection import now_iso, transaction
from services.security import new_token

_SECRET_CACHE: str | None = None


class AuthError(Exception):
    pass


def jwt_secret(con: sqlite3.Connection) -> str:
    global _SECRET_CACHE
    if _SECRET_CACHE:
        return _SECRET_CACHE
    import os
    env = os.environ.get("CARBONAI_JWT_SECRET", "")
    if env:
        _SECRET_CACHE = env
        return env
    row = con.execute("SELECT value FROM settings WHERE key='jwt_secret'").fetchone()
    if row and row["value"]:
        _SECRET_CACHE = row["value"]
        return _SECRET_CACHE
    _SECRET_CACHE = new_token(48)
    with transaction(con):
        con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES ('jwt_secret',?)",
                    (_SECRET_CACHE,))
    return _SECRET_CACHE


def reset_secret_cache() -> None:
    global _SECRET_CACHE
    _SECRET_CACHE = None


def create_access_token(*, username: str, role: str, company_id: int | None,
                        facility_id: int | None, secret: str,
                        minutes: int | None = None) -> str:
    payload = {
        "sub": username, "role": role,
        "company_id": company_id, "facility_id": facility_id,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=minutes or TOKEN_MINUTES),
    }
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


def decode_token(token: str, secret: str) -> dict:
    try:
        return jwt.decode(token, secret, algorithms=[JWT_ALGORITHM])
    except JWTError as e:
        raise AuthError(str(e)) from e
