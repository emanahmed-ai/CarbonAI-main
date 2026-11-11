"""User management (admins and head-office staff)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import Auth, get_con, require, resolve_scope
from db import auth_store
from api.util import rows_list

router = APIRouter(prefix="/api/users", tags=["users"])


class UserIn(BaseModel):
    username: str
    password: str = Field(min_length=8)
    role: str
    full_name: str | None = None
    email: str | None = None
    company_id: int | None = None
    facility_id: int | None = None
    locale: str = "ar"


class UserPatch(BaseModel):
    role: str | None = None
    full_name: str | None = None
    email: str | None = None
    facility_id: int | None = None
    locale: str | None = None
    is_active: bool | None = None


class ResetPasswordIn(BaseModel):
    new_password: str = Field(min_length=8)
    must_change_password: bool = True


@router.get("")
def list_users(company_id: int | None = None, con=Depends(get_con),
               user: Auth = Depends(require("admin", "head_office"))):
    cid, _ = resolve_scope(user, company_id, None)
    return rows_list(auth_store.list_users(con, company_id=cid))


@router.post("", status_code=201)
def create_user(body: UserIn, con=Depends(get_con),
                user: Auth = Depends(require("admin", "head_office"))):
    if user.role == "head_office":
        if body.role not in ("factory_manager", "viewer", "head_office"):
            raise HTTPException(403, "Head office can only create factory users")
        body.company_id = user.company_id  # type: ignore[assignment]
    elif body.company_id is None:
        # default to the organisation when it is unambiguous (single company seeded)
        only = con.execute("SELECT company_id FROM companies").fetchall()
        if len(only) == 1:
            body.company_id = only[0]["company_id"]  # type: ignore[assignment]
        elif body.role in ("factory_manager", "viewer") and body.facility_id is None:
            raise HTTPException(400, "company_id or facility_id is required for factory users")
    try:
        uid = auth_store.create_user(
            con, username=body.username, password=body.password, role=body.role,
            full_name=body.full_name, email=body.email, company_id=body.company_id,
            facility_id=body.facility_id, locale=body.locale, must_change_password=True,
            created_by=user.username)
    except auth_store.UserError as e:
        raise HTTPException(400, str(e))
    row = auth_store.get_user_by_id(con, uid)
    return {k: row[k] for k in ("user_id", "username", "role", "company_id", "facility_id",
                                "full_name", "must_change_password")}


@router.patch("/{user_id}")
def patch_user(user_id: int, body: UserPatch, con=Depends(get_con),
               user: Auth = Depends(require("admin", "head_office"))):
    row = auth_store.get_user_by_id(con, user_id)
    if row is None:
        raise HTTPException(404, "user not found")
    if user.role == "head_office" and row["company_id"] != user.company_id:
        raise HTTPException(403, "user belongs to another company")
    if user.role == "head_office" and body.role == "admin":
        raise HTTPException(403, "head office cannot create admins")
    try:
        auth_store.update_user(con, user_id, role=body.role, full_name=body.full_name,
                               email=body.email, facility_id=body.facility_id, locale=body.locale)
        if body.is_active is not None:
            if user_id == user.user_id and not body.is_active:
                raise HTTPException(400, "you cannot deactivate your own account")
            auth_store.set_active(con, user_id, body.is_active)
    except auth_store.UserError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@router.post("/{user_id}/password")
def reset_password(user_id: int, body: ResetPasswordIn, con=Depends(get_con),
                   user: Auth = Depends(require("admin"))):
    row = auth_store.get_user_by_id(con, user_id)
    if row is None:
        raise HTTPException(404, "user not found")
    auth_store.set_password(con, user_id, body.new_password)
    return {"ok": True}
