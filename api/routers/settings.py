"""App settings + admin maintenance (backup / factory reset / db info)."""
from __future__ import annotations

import sqlite3
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from api.deps import Auth, get_con, require, resolve_scope
from api.util import rows_list
from db import auth_store
from db.connection import backup_file, db_path, transaction
from services import factory_admin
from services.security import verify_password

router = APIRouter(prefix="/api/settings", tags=["settings"])

EDITABLE_KEYS = {"default_country", "scope2_method", "display_unit", "org_name_ar", "org_name_en"}
READABLE_KEYS = EDITABLE_KEYS | {"created_at"}


class SettingIn(BaseModel):
    key: str
    value: str


@router.get("")
def get_settings(con: sqlite3.Connection = Depends(get_con), user: Auth = Depends(require("admin", "head_office", "factory_manager", "viewer"))):
    rows = con.execute("SELECT key, value FROM settings").fetchall()
    return {r["key"]: r["value"] for r in rows if r["key"] in READABLE_KEYS}


@router.put("")
def put_setting(body: SettingIn, con: sqlite3.Connection = Depends(get_con),
                user: Auth = Depends(require("admin"))):
    if body.key not in EDITABLE_KEYS:
        raise HTTPException(400, f"key must be one of: {', '.join(sorted(EDITABLE_KEYS))}")
    with transaction(con):
        con.execute("INSERT INTO settings(key,value) VALUES (?,?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (body.key, body.value))
    return {"ok": True}


@router.post("/backup")
def backup(con: sqlite3.Connection = Depends(get_con), user: Auth = Depends(require("admin"))):
    dest = backup_file(db_path(), label="api_backup")
    return {"ok": dest is not None, "path": str(dest) if dest else None}


@router.get("/db-info")
def db_info(con: sqlite3.Connection = Depends(get_con), user: Auth = Depends(require("admin", "head_office"))):
    counts = {}
    for t in ("activity_records", "companies", "facilities", "emission_factors", "users",
              "report_submissions", "import_batches"):
        counts[t] = con.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"]
    return {"path": str(db_path()), "counts": counts}


class ResetIn(BaseModel):
    password: str
    facility_id: int | None = None
    company_id: int | None = None
    reason: str = ""
    confirm: str = ""


@router.get("/backup.zip")
def backup_zip(company_id: int | None = None, facility_id: int | None = None,
               con: sqlite3.Connection = Depends(get_con),
               user: Auth = Depends(require("admin", "head_office"))):
    """Factory-level backup: ZIP containing JSON of the selected factory's operational data.
    Head-office users are pinned to their own company; admin may choose any company/facility."""
    cid, fid = resolve_scope(user, company_id, facility_id)
    if fid is None and cid is None:
        raise HTTPException(400, "select a facility (or company) to back up")
    try:
        data = factory_admin.export_zip(con, company_id=cid, facility_id=fid)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"carbonai_backup_{fid or cid}_{stamp}.zip"
    return Response(content=data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.post("/factory-reset")
def factory_reset(body: ResetIn, con: sqlite3.Connection = Depends(get_con),
                  user: Auth = Depends(require("admin", "head_office"))):
    """DESTRUCTIVE: clears operational data only, after password verification + automatic backup."""
    if body.confirm.strip().upper() != "DELETE":
        raise HTTPException(400, "type DELETE in the confirmation field to proceed")
    row = auth_store.get_user_by_id(con, user.user_id)
    if row is None or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(403, "current password is incorrect")
    cid, fid = resolve_scope(user, body.company_id, body.facility_id)
    if user.role == "head_office":
        if fid is None and cid is None:
            raise HTTPException(400, "facility_id is required")
    if fid is None and cid is None:
        raise HTTPException(400, "facility_id or company_id is required")
    try:
        return factory_admin.factory_reset(con, facility_id=fid, company_id=cid,
                                           user=user.username, reason=body.reason)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
