"""User account store on top of the additive schema. No DELETE anywhere: deactivation instead."""
from __future__ import annotations

import re
import sqlite3

from db.connection import now_iso, transaction
from services.security import hash_password

ROLES = ("admin", "head_office", "factory_manager", "viewer")


class UserError(ValueError):
    pass


def _validate_role(role: str) -> str:
    if role not in ROLES:
        raise UserError(f"role must be one of {', '.join(ROLES)}")
    return role


def create_user(con: sqlite3.Connection, *, username: str, password: str, role: str,
                full_name: str | None = None, email: str | None = None,
                company_id: int | None = None, facility_id: int | None = None,
                locale: str = "ar", must_change_password: bool = False,
                created_by: str | None = None) -> int:
    username = (username or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9_.-]{3,40}", username):
        raise UserError("username must be 3-40 chars: a-z 0-9 _ . -")
    _validate_role(role)
    if role in ("factory_manager", "viewer") and facility_id is None:
        raise UserError("factory users must be attached to a facility")
    pw_hash = hash_password(password)
    with transaction(con):
        dup = con.execute("SELECT user_id FROM users WHERE username=?", (username,)).fetchone()
        if dup:
            raise UserError(f"username '{username}' already exists")
        if facility_id is not None:
            fac = con.execute("SELECT company_id FROM facilities WHERE facility_id=?", (facility_id,)).fetchone()
            if fac is None:
                raise UserError("facility not found")
            company_id = company_id if company_id is not None else fac["company_id"]
        cur = con.execute(
            "INSERT INTO users(username,password_hash,full_name,email,role,company_id,facility_id,locale,"
            "is_active,must_change_password,created_at) VALUES (?,?,?,?,?,?,?,?,'1',?,?)",
            (username, pw_hash, full_name, email, role, company_id, facility_id, locale,
             1 if must_change_password else 0, now_iso()))
    return cur.lastrowid


def get_user(con: sqlite3.Connection, username: str) -> sqlite3.Row | None:
    return con.execute("SELECT * FROM users WHERE username=?", ((username or "").strip().lower(),)).fetchone()


def get_user_by_id(con: sqlite3.Connection, user_id: int) -> sqlite3.Row | None:
    return con.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()


def list_users(con: sqlite3.Connection, *, company_id: int | None = None,
               active_only: bool = False) -> list[sqlite3.Row]:
    q = ("SELECT u.user_id, u.username, u.full_name, u.email, u.role, u.company_id, u.facility_id, u.locale, "
         "u.is_active, u.must_change_password, u.created_at, u.last_login_at, "
         "c.name AS company_name, f.name AS facility_name "
         "FROM users u LEFT JOIN companies c ON c.company_id=u.company_id "
         "LEFT JOIN facilities f ON f.facility_id=u.facility_id WHERE 1=1")
    p: list = []
    if company_id is not None:
        q += " AND u.company_id=?"; p.append(company_id)
    if active_only:
        q += " AND u.is_active=1"
    return con.execute(q + " ORDER BY u.username", p).fetchall()


def authenticate(con: sqlite3.Connection, username: str, password: str) -> sqlite3.Row | None:
    """Returns the user row on success, None on wrong credentials. Inactive users never log in."""
    u = get_user(con, username)
    if u is None or not u["is_active"]:
        return None
    from services.security import verify_password
    if not verify_password(password, u["password_hash"]):
        return None
    con.execute("UPDATE users SET last_login_at=? WHERE user_id=?", (now_iso(), u["user_id"]))
    con.commit()
    return u


def set_password(con: sqlite3.Connection, user_id: int, new_password: str) -> None:
    pw_hash = hash_password(new_password)
    with transaction(con):
        con.execute("UPDATE users SET password_hash=?, must_change_password=0 WHERE user_id=?",
                    (pw_hash, user_id))


def set_active(con: sqlite3.Connection, user_id: int, active: bool) -> None:
    with transaction(con):
        con.execute("UPDATE users SET is_active=? WHERE user_id=?", (1 if active else 0, user_id))


def update_user(con: sqlite3.Connection, user_id: int, *, role: str | None = None,
                full_name: str | None = None, email: str | None = None,
                facility_id: int | None = None, locale: str | None = None) -> None:
    fields, params = [], []
    for col, val in (("role", _validate_role(role) if role else None),
                     ("full_name", full_name), ("email", email),
                     ("facility_id", facility_id), ("locale", locale)):
        if val is not None:
            fields.append(f"{col}=?"); params.append(val)
    if not fields:
        return
    with transaction(con):
        r = con.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,)).fetchone()
        if r is None:
            raise LookupError("user not found")
        con.execute(f"UPDATE users SET {', '.join(fields)} WHERE user_id=?", (*params, user_id))
