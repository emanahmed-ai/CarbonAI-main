"""Shared FastAPI dependencies: DB connection per request, authenticated user, role guards,
and the data-scope resolver that isolates factories from each other."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Callable

from fastapi import Depends, Header, HTTPException, Query

from api import security
from db.connection import connect
from db import auth_store

ROLES = auth_store.ROLES


def get_con() -> sqlite3.Connection:
    con = connect()
    try:
        yield con
    finally:
        con.close()


@dataclass
class Auth:
    user_id: int
    username: str
    role: str
    company_id: int | None
    facility_id: int | None
    locale: str
    must_change_password: bool

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_head_office(self) -> bool:
        return self.role in ("admin", "head_office")

    @property
    def is_factory_scoped(self) -> bool:
        """Factory users are pinned to one facility and can never see another facility's data."""
        return self.role in ("factory_manager", "viewer")


def current_user(con: sqlite3.Connection = Depends(get_con),
                 authorization: str = Header(default="")) -> Auth:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing bearer token")
    token = authorization[7:].strip()
    try:
        payload = security.decode_token(token, security.jwt_secret(con))
    except security.AuthError:
        raise HTTPException(401, "Invalid or expired token")
    username = payload.get("sub")
    row = auth_store.get_user(con, username) if username else None
    if row is None or not row["is_active"]:
        raise HTTPException(401, "Account disabled or removed")
    return Auth(user_id=row["user_id"], username=row["username"], role=row["role"],
                company_id=row["company_id"], facility_id=row["facility_id"],
                locale=row["locale"], must_change_password=bool(row["must_change_password"]))


def require(*roles: str) -> Callable:
    allowed = set(roles)
    def guard(user: Auth = Depends(current_user)) -> Auth:
        if user.role not in allowed:
            raise HTTPException(403, f"Requires role: {' or '.join(sorted(allowed))}")
        return user
    return guard


def resolve_scope(user: Auth, company_id: int | None, facility_id: int | None) -> tuple[int | None, int | None]:
    """Apply the caller's tenancy to the requested filters.

    * admin: any company/facility (None = all).
    * head_office: pinned to their company; may pick any facility inside it.
    * factory_manager/viewer: pinned to their facility; company/facility arguments are ignored.
    """
    if user.is_admin:
        return company_id, facility_id
    if user.role == "head_office":
        if user.company_id is None:
            raise HTTPException(403, "Head-office account has no company assigned")
        if facility_id is not None:
            return user.company_id, facility_id
        return user.company_id, None
    # factory-scoped
    if facility_id is not None and facility_id != user.facility_id:
        raise HTTPException(403, "You can only access your own facility's data")
    return user.company_id, user.facility_id


def require_facility(user: Auth, facility_id: int | None) -> int:
    """For write operations: factory users always act on their own facility; staff must name one."""
    cid, fid = resolve_scope(user, None, facility_id)
    if fid is None:
        raise HTTPException(400, "facility_id is required for this operation")
    return fid
