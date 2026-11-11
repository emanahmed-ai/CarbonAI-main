"""Activity records: creation through the calculation engine, filtered/searchable listing,
and manual scope correction. All business rules live in services.ledger (unchanged)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.deps import Auth, current_user, get_con, require, resolve_scope
from api.util import df_records, rows_list
from db import auth_store
from services import factor_library as FL
from services import ledger as L
from services import unit_conversion as uc
from services.scope_classifier import classify

router = APIRouter(prefix="/api/records", tags=["records"])


class ManualFactor(BaseModel):
    value: str
    source: str
    url: str | None = None


class LibraryFactor(BaseModel):
    factor_id: str
    version: int | None = None
    proxy_confirmed: bool = False
    proxy_rationale: str = ""
    nearest_ok: bool = False          # documented nearest-year selection (marked ESTIMATED)


class RecordIn(BaseModel):
    activity_name: str
    quantity: str
    unit: str
    activity_date: str | None = None
    description: str = ""
    fuel_or_material: str | None = None
    category_key: str | None = None
    country_code: str | None = None
    facility_id: int | None = None
    ownership_control: str = "unknown"
    energy_purchased: str = "unknown"
    value_chain_relation: str = "unknown"
    scope2_method: str | None = None
    notes: str = ""
    evidence_ref: str | None = None
    allow_duplicate: bool = False
    scope_override_scope: str | None = None
    scope_override_subcategory: str | None = None
    scope_override_reason: str | None = None
    factor: LibraryFactor | None = None
    manual_factor: ManualFactor | None = None


class ScopeOverrideIn(BaseModel):
    scope: str
    subcategory: str | None = None
    reason: str


@router.get("")
def list_records(
    con=Depends(get_con), user: Auth = Depends(current_user),
    company_id: int | None = None, facility_id: int | None = None,
    year: int | None = None, month: int | None = None,
    date_from: str | None = None, date_to: str | None = None,
    scope: str | None = None, category_key: str | None = None,
    calc_status: str | None = None, search: str | None = None,
    sort: str = "activity_date", direction: str = "desc",
    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=500),
):
    cid, fid = resolve_scope(user, company_id, facility_id)
    df = L.fetch_records(con, company_id=cid, facility_id=fid, year=year, month=month,
                         date_from=date_from or None, date_to=date_to or None, scope=scope,
                         category_key=category_key, calc_status=calc_status)
    if search:
        s = search.lower()
        mask = (
            df["activity_name"].fillna("").str.lower().str.contains(s, regex=False)
            | df["description"].fillna("").str.lower().str.contains(s, regex=False)
            | df["facility_name"].fillna("").str.lower().str.contains(s, regex=False)
            | df["company_name"].fillna("").str.lower().str.contains(s, regex=False)
        )
        df = df[mask]
    sortable = [c for c in ("activity_date", "activity_name", "scope", "kg", "quantity",
                            "calc_status", "record_id", "facility_name") if c in df.columns]
    sort_col = sort if sort in sortable else "activity_date"
    if not df.empty:
        df = df.sort_values(sort_col, ascending=(direction != "desc"), na_position="last")
    total = len(df)
    start = (page - 1) * page_size
    rows = df.iloc[start:start + page_size]
    return {"total": total, "page": page, "page_size": page_size, "rows": df_records(rows)}


@router.get("/meta")
def record_meta(con=Depends(get_con), user: Auth = Depends(current_user)):
    categories = rows_list(con.execute("SELECT category_key, name_ar, name_en, compatible_units, "
                                       "expected_scope FROM activity_categories ORDER BY category_key").fetchall())
    countries = rows_list(con.execute("SELECT iso2_code, country_name_ar, country_name_en FROM countries "
                                      "WHERE is_active=1 ORDER BY country_name_en").fetchall())
    units = ["kWh", "MWh", "GJ", "MJ", "litre", "m3", "kg", "tonne", "km", "tkm", "pkm", "room_night", "unit"]
    _, facilities = resolve_scope(user, None, None)
    return {"categories": categories, "countries": countries, "units": units,
            "unit_dimensions": {u: uc.dimension(u) for u in units},
            "scope3_categories": rows_list(con.execute(
                "SELECT * FROM (SELECT 1 n UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION SELECT 5 "
                "UNION SELECT 6 UNION SELECT 7 UNION SELECT 8 UNION SELECT 9 UNION SELECT 10 UNION SELECT 11 "
                "UNION SELECT 12 UNION SELECT 13 UNION SELECT 14 UNION SELECT 15)").fetchall())}


@router.get("/{record_id}")
def get_record(record_id: int, con=Depends(get_con), user: Auth = Depends(current_user)):
    row = con.execute("SELECT r.*, c.name AS company_name, f.name AS facility_name, f.company_id AS f_company_id "
                      "FROM activity_records r LEFT JOIN companies c ON c.company_id=r.company_id "
                      "LEFT JOIN facilities f ON f.facility_id=r.facility_id WHERE r.record_id=?",
                      (record_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "record not found")
    resolve_scope(user, row["f_company_id"] or row["company_id"], row["facility_id"])
    return _row(row)


def _row(row) -> dict:
    from api.util import jsonable
    return {k: jsonable(row[k]) for k in row.keys()}


@router.post("/scope-preview")
def scope_preview(body: RecordIn, user: Auth = Depends(current_user)):
    sug = classify(category_key=body.category_key, ownership_control=body.ownership_control,
                   energy_purchased=body.energy_purchased,
                   value_chain_relation=body.value_chain_relation, description=body.description)
    return {"scope": sug.scope, "subcategory": sug.subcategory, "scope3_category": sug.scope3_category,
            "status": sug.status, "confidence": sug.confidence, "reason_en": sug.reason_en,
            "reason_ar": sug.reason_ar, "reference": sug.reference, "missing": sug.missing}


@router.post("", status_code=201)
def create_record(body: RecordIn, con=Depends(get_con), user: Auth = Depends(require("admin", "head_office", "factory_manager"))):
    facility_id = body.facility_id if user.is_admin or user.role == "head_office" else user.facility_id
    if user.is_admin or user.role == "head_office":
        if facility_id is None:
            raise HTTPException(400, "facility_id is required (pick the branch/factory this activity belongs to)")
        fac = con.execute("SELECT company_id FROM facilities WHERE facility_id=?", (facility_id,)).fetchone()
        if fac is None:
            raise HTTPException(404, "facility not found")
        company_id = fac["company_id"]
    else:
        if facility_id is None:
            raise HTTPException(403, "your account has no facility assigned; contact the administrator")
        company_id = user.company_id

    factor, sel_reason, proxy = None, "", False
    nearest_ok = False
    if body.factor and body.factor.factor_id:
        f = FL.get_factor(con, body.factor.factor_id, body.factor.version)
        if f is None:
            raise HTTPException(404, f"factor {body.factor.factor_id} not found")
        factor = f
        proxy = bool(body.factor.proxy_confirmed)
        nearest_ok = bool(body.factor.nearest_ok)
        sel_reason = body.factor.proxy_rationale.strip()
        if f.country != (body.country_code or "") and not proxy:
            raise HTTPException(400, "This factor is not national for the selected country; explicit "
                                     "proxy confirmation with a rationale is required")
    elif body.manual_factor:
        if not body.manual_factor.source.strip():
            raise HTTPException(400, "A manual factor requires its source")
        year = 0
        if body.activity_date:
            d = L.parse_date(body.activity_date)
            year = d.year if d else 0
        factor = L.user_factor(body.manual_factor.value, country=body.country_code or "",
                               category=body.category_key or "other",
                               activity=body.fuel_or_material or body.activity_name,
                               unit=body.unit, year=year, source=body.manual_factor.source.strip(),
                               url=body.manual_factor.url)
        sel_reason = "User-supplied factor (unverified)"
        proxy = True

    override = None
    if body.scope_override_scope:
        if not (body.scope_override_reason or "").strip():
            raise HTTPException(400, "A scope override requires a reason")
        override = (body.scope_override_scope, body.scope_override_subcategory or None,
                    body.scope_override_reason.strip())
    try:
        res = L.add_record(
            con, activity_name=body.activity_name, quantity=body.quantity, unit=body.unit,
            country_code=body.country_code, activity_date=body.activity_date or None,
            description=body.description, company_id=company_id, facility_id=facility_id,
            fuel_or_material=body.fuel_or_material, category_key=body.category_key,
            factor=factor, factor_selection_reason=sel_reason, proxy_confirmed=proxy,
            ownership_control=body.ownership_control, energy_purchased=body.energy_purchased,
            value_chain_relation=body.value_chain_relation, scope_override=override,
            scope2_method=body.scope2_method, notes=body.notes, evidence_ref=body.evidence_ref,
            origin="manual", allow_duplicate=body.allow_duplicate, user=user.username,
            nearest_year_ok=nearest_ok)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if res.get("duplicate"):
        raise HTTPException(409, {"detail": "duplicate record exists", "record_id": res.get("record_id")})
    out = dict(res)
    if res.get("record_id"):
        row = con.execute("SELECT * FROM activity_records WHERE record_id=?", (res["record_id"],)).fetchone()
        out["record"] = _row(row)
    return out


@router.post("/{record_id}/scope-override")
def override_scope(record_id: int, body: ScopeOverrideIn, con=Depends(get_con),
                   user: Auth = Depends(require("admin", "head_office", "factory_manager"))):
    row = con.execute("SELECT facility_id FROM activity_records WHERE record_id=?", (record_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "record not found")
    if user.is_factory_scoped and row["facility_id"] != user.facility_id:
        raise HTTPException(403, "record belongs to another facility")
    try:
        L.override_scope(con, record_id, body.scope, body.subcategory, body.reason, user.username)
    except (ValueError, LookupError) as e:
        raise HTTPException(400 if isinstance(e, ValueError) else 404, str(e))
    updated = con.execute("SELECT * FROM activity_records WHERE record_id=?", (record_id,)).fetchone()
    return _row(updated)
