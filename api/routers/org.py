"""Organisation structure: companies (organisations) and facilities (branches / factories)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import Auth, get_con, require, resolve_scope
from api.util import rows_list
from db.connection import now_iso, transaction
from services import ledger as L

router = APIRouter(prefix="/api/org", tags=["org"])


class CompanyIn(BaseModel):
    name: str
    country_code: str | None = None
    industry_sector: str | None = None
    boundary_approach: str | None = None
    boundary_notes: str | None = None


class FacilityIn(BaseModel):
    company_id: int | None = None
    name: str
    country_code: str | None = None
    internal_ref: str | None = None
    control_status: str = "unknown"


@router.get("/companies")
def list_companies(con=Depends(get_con), user: Auth = Depends(require("admin", "head_office", "viewer", "factory_manager"))):
    cid, _ = resolve_scope(user, None, None)
    q = "SELECT c.*, (SELECT COUNT(*) FROM facilities f WHERE f.company_id=c.company_id) AS n_facilities FROM companies c"
    p: list = []
    if cid is not None:
        q += " WHERE c.company_id=?"; p.append(cid)
    return rows_list(con.execute(q + " ORDER BY c.name", p).fetchall())


@router.post("/companies", status_code=201)
def create_company(body: CompanyIn, con=Depends(get_con), user: Auth = Depends(require("admin", "head_office"))):
    if not body.name.strip():
        raise HTTPException(400, "name is required")
    cid = L.upsert_company(con, body.name, body.country_code, body.industry_sector,
                           body.boundary_approach, body.boundary_notes)
    return con.execute("SELECT * FROM companies WHERE company_id=?", (cid,)).fetchone()


@router.get("/facilities")
def list_facilities(company_id: int | None = None, con=Depends(get_con),
                    user: Auth = Depends(require("admin", "head_office", "viewer", "factory_manager"))):
    cid, fid = resolve_scope(user, company_id, None)
    q = ("SELECT f.*, c.name AS company_name, "
         "(SELECT COUNT(*) FROM activity_records r WHERE r.facility_id=f.facility_id) AS n_records "
         "FROM facilities f JOIN companies c ON c.company_id=f.company_id")
    p: list = []
    if fid is not None:
        q += " WHERE f.facility_id=?"; p.append(fid)
    elif cid is not None:
        q += " WHERE f.company_id=?"; p.append(cid)
    return rows_list(con.execute(q + " ORDER BY c.name, f.name", p).fetchall())


@router.post("/facilities", status_code=201)
def create_facility(body: FacilityIn, con=Depends(get_con), user: Auth = Depends(require("admin", "head_office"))):
    if not body.name.strip():
        raise HTTPException(400, "name is required")
    if user.is_admin and body.company_id is None:
        # default to the organisation when it is unambiguous (single company seeded)
        only = con.execute("SELECT company_id FROM companies").fetchall()
        if len(only) == 1:
            body.company_id = only[0]["company_id"]  # type: ignore[assignment]
    cid = body.company_id if user.is_admin else user.company_id
    if cid is None:
        raise HTTPException(400, "company_id is required")
    if body.company_id is not None and user.role == "head_office" and body.company_id != user.company_id:
        raise HTTPException(403, "cannot create facilities for another company")
    exists = con.execute("SELECT 1 FROM companies WHERE company_id=?", (cid,)).fetchone()
    if not exists:
        raise HTTPException(404, "company not found")
    fid = L.add_facility(con, cid, body.name, body.country_code, body.internal_ref, body.control_status)
    return con.execute("SELECT * FROM facilities WHERE facility_id=?", (fid,)).fetchone()


@router.patch("/facilities/{facility_id}")
def patch_facility(facility_id: int, body: FacilityIn, con=Depends(get_con),
                   user: Auth = Depends(require("admin", "head_office"))):
    row = con.execute("SELECT * FROM facilities WHERE facility_id=?", (facility_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "facility not found")
    if user.role == "head_office" and row["company_id"] != user.company_id:
        raise HTTPException(403, "facility belongs to another company")
    with transaction(con):
        con.execute("UPDATE facilities SET name=?, country_code=?, internal_ref=?, control_status=? "
                    "WHERE facility_id=?",
                    (body.name.strip() or row["name"], body.country_code or row["country_code"],
                     body.internal_ref or row["internal_ref"], body.control_status or row["control_status"],
                     facility_id))
    return con.execute("SELECT * FROM facilities WHERE facility_id=?", (facility_id,)).fetchone()
