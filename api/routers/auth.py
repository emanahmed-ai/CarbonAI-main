"""Authentication endpoints: login, session, password change."""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator

from api import security
from api.deps import Auth, current_user, get_con
from db import auth_store
from services.security import verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

# naive per-username lockout after repeated failures (brute-force slowdown; state resets on restart)
_failures: dict[str, tuple[int, float]] = {}
MAX_FAILURES, LOCK_SECONDS = 5, 30.0


class LoginIn(BaseModel):
    username: str
    password: str


class ChangePasswordIn(BaseModel):
    old_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def strong(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("new password must be at least 8 characters")
        return v


def _user_payload(u) -> dict:
    return {"user_id": u["user_id"], "username": u["username"], "full_name": u["full_name"],
            "role": u["role"], "company_id": u["company_id"], "facility_id": u["facility_id"],
            "locale": u["locale"], "must_change_password": bool(u["must_change_password"]),
            "last_login_at": u["last_login_at"]}


@router.post("/login")
def login(body: LoginIn, request: Request, con=Depends(get_con)):
    key = f"{body.username.lower()}|{request.client.host if request.client else '?'}"
    fails, ts = _failures.get(key, (0, 0.0))
    if fails >= MAX_FAILURES and time.time() - ts < LOCK_SECONDS:
        raise HTTPException(429, "Too many failed attempts; wait 30 seconds")
    u = auth_store.authenticate(con, body.username, body.password)
    if u is None:
        _failures[key] = (fails + 1, time.time())
        raise HTTPException(401, "Wrong username or password")
    _failures.pop(key, None)
    token = security.create_access_token(
        username=u["username"], role=u["role"], company_id=u["company_id"],
        facility_id=u["facility_id"], secret=security.jwt_secret(con))
    return {"token": token, "user": _user_payload(u)}


@router.get("/me")
def me(user: Auth = Depends(current_user)):
    return {"username": user.username, "role": user.role, "company_id": user.company_id,
            "facility_id": user.facility_id, "locale": user.locale,
            "must_change_password": user.must_change_password}


@router.post("/change-password")
def change_password(body: ChangePasswordIn, con=Depends(get_con), user: Auth = Depends(current_user)):
    row = auth_store.get_user_by_id(con, user.user_id)
    if row is None or not verify_password(body.old_password, row["password_hash"]):
        raise HTTPException(400, "Current password is wrong")
    auth_store.set_password(con, user.user_id, body.new_password)
    return {"ok": True}
