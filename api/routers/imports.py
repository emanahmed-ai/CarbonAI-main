"""CSV / Excel import endpoints.

Two import paths coexist:
  * legacy  POST /preview + /commit        - fixed template headers (backward compatible);
  * smart   POST /analyze -> /preview-mapped -> /commit-mapped - intelligent column mapping
    (Arabic/English synonyms, fuzzy matching, data-type evidence), with the emission factor
    that WOULD be applied shown per row before committing.

Duplicate protection: every uploaded file is SHA-256 hashed; a previously committed identical
file is rejected with 409 and the original batch info unless force=true.
Factory-scoped users always have rows attributed to their own facility.
"""
from __future__ import annotations

import hashlib
import json

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from api.deps import Auth, current_user, get_con, require
from api.util import rows_list
from services import column_mapper as CM
from services import factor_library as FL
from services import importer as I
from services import jobs as J

router = APIRouter(prefix="/api/imports", tags=["imports"])


def _read(name: str, data: bytes, sheet: str | None = None) -> pd.DataFrame:
    try:
        return I.read_upload(name, data, sheet_name=sheet)
    except ValueError as e:
        raise HTTPException(400, str(e))


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hash_duplicate(con, file_hash: str):
    row = con.execute("SELECT batch_id, file_name, imported_at, rows_accepted FROM import_batches "
                      "WHERE file_hash=? ORDER BY batch_id DESC LIMIT 1", (file_hash,)).fetchone()
    return None if row is None else dict(row)


def _preview_json(pv: I.Preview, *, override_facility: str | None = None,
                  factor_preview: list | None = None) -> dict:
    return {
        "missing_columns": pv.missing_columns,
        "accepted": [{"row_number": a["row_number"], "activity": a["activity"], "quantity": a["quantity"],
                      "unit": a["unit"], "date": a["date"].isoformat() if a["date"] else None,
                      "scope": a["scope"], "factor": a["factor"], "source": a["source"],
                      "country": a["country"], "company": a["company"], "facility": a["facility"],
                      "category": a["category"], "fuel": a["fuel"]}
                     for a in pv.accepted],
        "rejected": [{"row_number": n, "reason": why} for n, why, _raw in pv.rejected],
        "warnings": [{"row_number": n, "text": t} for n, t in pv.warnings],
        "facility_override": override_facility,
        "factor_preview": factor_preview or [],
    }


def _factor_previews(con, accepted: list, limit: int = 60) -> list[dict]:
    """For each prospective row, what factor WOULD apply (auto-selected only if exactly one
    verified national factor fits; otherwise the row needs an explicit choice). Cached per key."""
    cache: dict = {}
    out = []
    for a in accepted[:limit]:
        year = a["date"].year if a["date"] else None
        key = (a["country"], a["category"], year, a["unit"], a["fuel"])
        if key not in cache:
            if a["factor"] is not None:
                cache[key] = {"status": "from_file", "message": "factor supplied in the file (user-supplied, unverified)"}
            elif not (a["country"] and a["category"] and year):
                cache[key] = {"status": "needs_input",
                              "message": "country/category/date required to look up a factor"}
            else:
                try:
                    sg = FL.suggest(con, country=a["country"], category=a["category"], year=year,
                                    unit=a["unit"], fuel=a["fuel"])
                    if sg.chosen is not None:
                        f = sg.chosen.factor
                        cache[key] = {"status": "auto", "message": sg.message,
                                      "chosen": {"factor_id": f.factor_id, "version": f.version,
                                                 "value": str(f.total_co2e), "unit": f.denominator_unit,
                                                 "source": f.source_org, "status": f.status.value}}
                    else:
                        cache[key] = {"status": "needs_selection", "message": sg.message,
                                      "candidates": len(sg.candidates)}
                except Exception as e:  # never fail a preview because of factor lookup
                    cache[key] = {"status": "error", "message": str(e)}
        out.append({"row_number": a["row_number"], **cache[key]})
    return out


def _apply_tenancy(con, user: Auth, pv: I.Preview) -> str | None:
    if not user.is_factory_scoped:
        return None
    name = _facility_name(con, user)
    company = _user_company(con, user)
    for a in pv.accepted:
        a["company"], a["facility"] = company, name
    return name


# ---------------- smart mapping ----------------

@router.post("/analyze")
def analyze_import(file: UploadFile = File(...), sheet: str | None = Form(None), con=Depends(get_con),
                   user: Auth = Depends(require("admin", "head_office", "factory_manager"))):
    data = file.file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(413, "file too large (max 10 MB)")
    df = _read(file.filename or "upload.csv", data, sheet)
    info = CM.analyze(df)
    h = _sha256(data)
    dup = _hash_duplicate(con, h)
    return {"file_name": file.filename, "file_hash": h, "duplicate_file": dup,
            "sheets": I.list_sheets(file.filename or "upload.csv", data),
            "sheet": sheet, "total_rows": int(len(df)), "preview_page_size": 100, **info}


@router.post("/raw-preview")
def raw_preview(file: UploadFile = File(...), sheet: str | None = Form(None),
                page: int = Form(1), page_size: int = Form(100), con=Depends(get_con),
                user: Auth = Depends(require("admin", "head_office", "factory_manager"))):
    """The uploaded file exactly as-is (original columns/values), paginated for the UI."""
    data = file.file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(413, "file too large (max 10 MB)")
    df = _read(file.filename or "upload.csv", data, sheet)
    page = max(1, int(page))
    page_size = min(100, max(10, int(page_size)))
    total = len(df)
    start = (page - 1) * page_size
    rows = df.iloc[start:start + page_size].fillna("").astype(str).to_dict(orient="records")
    return {"columns": [str(c) for c in df.columns], "rows": rows, "total": total,
            "page": page, "page_size": page_size,
            "sheets": I.list_sheets(file.filename or "upload.csv", data)}


@router.post("/jobs", status_code=202)
def start_job(file: UploadFile = File(...), mapping: str = Form("{}"),
              default_country: str | None = Form(None), default_date: str | None = Form(None),
              keep_duplicates: bool = Form(False), force: bool = Form(False),
              sheet: str | None = Form(None), con=Depends(get_con),
              user: Auth = Depends(require("admin", "head_office", "factory_manager"))):
    """Start a background import; the response returns immediately with a job id."""
    data = file.file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(413, "file too large (max 10 MB)")
    try:
        mp = json.loads(mapping or "{}")
    except json.JSONDecodeError:
        raise HTTPException(400, "mapping must be valid JSON")
    h = _sha256(data)
    dup = _hash_duplicate(con, h)
    if dup and not force:
        raise HTTPException(409, {"detail": "This exact file was already imported",
                                  "previous_batch": dup, "force_hint": "send force=true to import anyway"})
    facility_id = user.facility_id if user.is_factory_scoped else None
    options = {"default_country": default_country, "default_date": default_date,
               "keep_duplicates": keep_duplicates, "user": user.username,
               "file_hash": h, "sheet": sheet}
    if user.is_factory_scoped:
        options["facility_override"] = _facility_name(con, user)
        options["company_name"] = _user_company(con, user)
    job_id = J.start_import_job(file_name=file.filename or "upload.csv", data=data, mapping=mp,
                                options=options, file_hash=h, facility_id=facility_id)
    return {"job_id": job_id, "status": "queued"}


@router.get("/jobs/{job_id}")
def job_status(job_id: str, con=Depends(get_con),
               user: Auth = Depends(require("admin", "head_office", "factory_manager"))):
    job = J.get(job_id)
    if job is None:
        raise HTTPException(404, "job not found or expired")
    return job


@router.post("/preview-mapped")
def preview_mapped(file: UploadFile = File(...), mapping: str = Form("{}"),
                   default_country: str | None = Form(None), default_date: str | None = Form(None),
                   con=Depends(get_con),
                   user: Auth = Depends(require("admin", "head_office", "factory_manager"))):
    try:
        mp = json.loads(mapping or "{}")
    except json.JSONDecodeError:
        raise HTTPException(400, "mapping must be valid JSON")
    data = file.file.read()
    df = _read(file.filename or "upload.csv", data)
    renamed, problems = CM.apply_mapping(df, mp)
    if problems:
        raise HTTPException(400, "; ".join(problems))
    pv = I.preview(renamed, default_date=default_date, default_country=default_country)
    override = _apply_tenancy(con, user, pv)
    previews = _factor_previews(con, pv.accepted)
    return _preview_json(pv, override_facility=override, factor_preview=previews)


@router.post("/commit-mapped")
def commit_mapped(file: UploadFile = File(...), mapping: str = Form("{}"),
                  default_country: str | None = Form(None), default_date: str | None = Form(None),
                  keep_duplicates: bool = Form(False), force: bool = Form(False),
                  con=Depends(get_con),
                  user: Auth = Depends(require("admin", "head_office", "factory_manager"))):
    try:
        mp = json.loads(mapping or "{}")
    except json.JSONDecodeError:
        raise HTTPException(400, "mapping must be valid JSON")
    data = file.file.read()
    h = _sha256(data)
    dup = _hash_duplicate(con, h)
    if dup and not force:
        raise HTTPException(409, {"detail": "This exact file was already imported",
                                  "previous_batch": dup, "force_hint": "send force=true to import anyway"})
    df = _read(file.filename or "upload.csv", data)
    renamed, problems = CM.apply_mapping(df, mp)
    if problems:
        raise HTTPException(400, "; ".join(problems))
    pv = I.preview(renamed, default_date=default_date, default_country=default_country)
    if pv.missing_columns:
        raise HTTPException(400, f"missing required columns: {', '.join(pv.missing_columns)}")
    _apply_tenancy(con, user, pv)
    try:
        res = I.commit(con, pv, file_name=file.filename or "upload.csv",
                       keep_duplicates=keep_duplicates, user=user.username)
    except Exception as e:
        raise HTTPException(500, f"import failed: {e}")
    con.execute("UPDATE import_batches SET file_hash=? WHERE batch_id=?", (h, res["batch_id"]))
    con.commit()
    return {**res, "file_hash": h}


# ---------------- legacy fixed-template path ----------------

@router.post("/preview")
def preview_import(file: UploadFile = File(...), default_country: str | None = None,
                   default_date: str | None = None, con=Depends(get_con),
                   user: Auth = Depends(require("admin", "head_office", "factory_manager"))):
    data = file.file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(413, "file too large (max 10 MB)")
    df = _read(file.filename or "upload.csv", data)
    pv = I.preview(df, default_date=default_date, default_country=default_country)
    override = _apply_tenancy(con, user, pv)
    return _preview_json(pv, override_facility=override, factor_preview=_factor_previews(con, pv.accepted))


@router.post("/commit")
def commit_import(file: UploadFile = File(...), default_country: str | None = None,
                  default_date: str | None = None, keep_duplicates: bool = False,
                  force: bool = False,
                  con=Depends(get_con), user: Auth = Depends(require("admin", "head_office", "factory_manager"))):
    data = file.file.read()
    h = _sha256(data)
    dup = _hash_duplicate(con, h)
    if dup and not force:
        raise HTTPException(409, {"detail": "This exact file was already imported",
                                  "previous_batch": dup, "force_hint": "send force=true to import anyway"})
    df = _read(file.filename or "upload.csv", data)
    pv = I.preview(df, default_date=default_date, default_country=default_country)
    if pv.missing_columns:
        raise HTTPException(400, f"missing required columns: {', '.join(pv.missing_columns)}")
    _apply_tenancy(con, user, pv)
    try:
        res = I.commit(con, pv, file_name=file.filename or "upload.csv",
                       keep_duplicates=keep_duplicates, user=user.username)
    except Exception as e:
        raise HTTPException(500, f"import failed: {e}")
    con.execute("UPDATE import_batches SET file_hash=? WHERE batch_id=?", (h, res["batch_id"]))
    con.commit()
    return {**res, "file_hash": h}


@router.get("/batches")
def batches(con=Depends(get_con), user: Auth = Depends(require("admin", "head_office", "factory_manager"))):
    rows = con.execute("SELECT * FROM import_batches ORDER BY batch_id DESC LIMIT 100").fetchall()
    return rows_list(rows)


@router.get("/template.csv")
def template(user: Auth = Depends(current_user)):
    csv = (",".join(I.TEMPLATE_COLUMNS) + "\n" + ",".join(
        ["diesel generator", "Scope 1", "1200", "litre", "2.68", "supplier invoice",
         "2024-03-15", "EG", "", "", "generators fuel", "diesel", "stationary_fuel",
         "owned_controlled", "no", "own_fleet"])).encode("utf-8-sig")
    from fastapi.responses import Response
    return Response(content=csv, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="carbonai_import_template.csv"'})


def _facility_name(con, user: Auth) -> str:
    r = con.execute("SELECT name FROM facilities WHERE facility_id=?", (user.facility_id,)).fetchone()
    return r["name"] if r else ""


def _user_company(con, user: Auth) -> str:
    if user.company_id is None:
        return ""
    r = con.execute("SELECT name FROM companies WHERE company_id=?", (user.company_id,)).fetchone()
    return r["name"] if r else ""
