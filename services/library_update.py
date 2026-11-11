"""Library update from a downloaded official file (CSV/Excel). Manual, reviewable, additive.

NOT implemented: automatic downloading/scraping of official sites (no network in the build sandbox, and
scraping is fragile and licence-sensitive). The administrator downloads the official file, uploads it
here; every row is validated, inserted as UNVERIFIED (new version if the id exists), and the run is logged.
A failure rolls back the whole file and leaves the existing library untouched.
"""
from __future__ import annotations

import io

import pandas as pd

from db.connection import now_iso, transaction
from schemas.domain import FactorClass
from services import factor_library as FL
from services import unit_conversion as uc

REQUIRED = ["factor_id", "country_code", "factor_class", "activity_category", "activity", "unit", "value",
            "year_from", "year_to", "source_organization", "source_document", "source_locator"]
OPTIONAL = ["source_url", "boundary_note", "methodology", "notes", "gwp_set_id", "publication_year"]


def validate(df: pd.DataFrame) -> tuple[list, list]:
    """Returns (good_rows, problems). problems = [(row_number, reason)]"""
    problems = []
    miss = [c for c in REQUIRED if c not in df.columns]
    if miss:
        return [], [(0, f"missing columns: {', '.join(miss)}")]
    good, seen = [], set()
    for i, r in df.iterrows():
        n = i + 2
        try:
            FactorClass(str(r["factor_class"]).strip())
            val = float(str(r["value"]).replace(",", ""))
            if val < 0:
                raise ValueError("negative value")
            y0, y1 = int(r["year_from"]), int(r["year_to"])
            if y1 < y0:
                raise ValueError("year_to < year_from")
            uc.canon(str(r["unit"]))
            for c in ("source_organization", "source_document", "source_locator", "factor_id", "country_code"):
                if not str(r[c]).strip():
                    raise ValueError(f"{c} is empty (unsourced factors are not accepted)")
            key = (str(r["factor_id"]).strip(), y0, y1)
            if key in seen:
                raise ValueError("duplicate factor_id/year range inside the file")
            seen.add(key)
            good.append(r)
        except Exception as e:
            problems.append((n, str(e)))
    return good, problems


def apply_file(con, df: pd.DataFrame, *, reference_id: str | None, user: str, reason: str,
               source_label: str, allow_partial: bool = False) -> dict:
    good, problems = validate(df)
    if problems and not allow_partial:
        _log(con, source_label, "rejected", f"{len(problems)} problem(s); nothing imported: {problems[:5]}")
        return {"imported": 0, "problems": problems, "applied": False}
    n = 0
    try:
        with transaction(con):
            for r in good:
                con.execute("SAVEPOINT row")
                FL_add(con, r, reference_id, user, reason)
                con.execute("RELEASE row")
                n += 1
    except Exception as e:  # whole-file rollback
        _log(con, source_label, "failed", str(e))
        return {"imported": 0, "problems": [(0, str(e))], "applied": False}
    _log(con, source_label, "imported", f"{n} factor(s) added as unverified; {len(problems)} skipped")
    return {"imported": n, "problems": problems, "applied": True}


def FL_add(con, r, reference_id, user, reason):
    """add_factor opens its own transaction; inside an outer one we replicate the insert via a nested call."""
    # add_factor uses `transaction()` (BEGIN); SQLite forbids nesting, so call the inner logic directly.
    from db.connection import now_iso as _now  # noqa
    prev = con.execute("SELECT MAX(version) m FROM emission_factors WHERE factor_id=?", (str(r["factor_id"]).strip(),)).fetchone()["m"]
    ver = (prev or 0) + 1
    fid = str(r["factor_id"]).strip()
    g = lambda k: (str(r[k]).strip() if k in r.index and str(r[k]).strip() not in ("", "nan") else None)
    unit = str(r["unit"]).strip()
    con.execute(
        "INSERT INTO emission_factors(factor_id,version,factor_name_en,country_code,factor_class,activity_category,"
        "activity,activity_unit,factor_unit,co2e_factor_value,components_json,gwp_set_id,reference_id,"
        "source_organization,source_document,source_url,source_locator,publication_year,year_from,year_to,"
        "geographic_coverage,methodology,boundary_note,verification_status,notes,created_at,gas_type)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,'[]',?,?,?,?,?,?,?,?,?,?,?,?,'unverified',?,?,'CO2e')",
        (fid, ver, f"{r['activity_category']} / {r['activity']}", str(r["country_code"]).strip().upper(),
         str(r["factor_class"]).strip(), str(r["activity_category"]).strip(), str(r["activity"]).strip(), unit,
         f"kg CO2e/{unit}", str(r["value"]).replace(",", ""), g("gwp_set_id"), reference_id,
         str(r["source_organization"]).strip(), str(r["source_document"]).strip(), g("source_url"),
         str(r["source_locator"]).strip(), int(g("publication_year")) if g("publication_year") else None,
         int(r["year_from"]), int(r["year_to"]), str(r["country_code"]).strip().upper(), g("methodology"),
         g("boundary_note"), g("notes"), now_iso()))
    con.execute("INSERT INTO factor_audit_log(factor_id,version,action,field_name,old_value,new_value,changed_at,"
                "changed_by,reason,reference_id) VALUES (?,?,?,?,NULL,?,?,?,?,?)",
                (fid, ver, "created" if ver == 1 else "new_version", "co2e_factor_value",
                 str(r["value"]).replace(",", ""), now_iso(), user, reason, reference_id))
    if prev:
        con.execute("UPDATE emission_factors SET verification_status='superseded' WHERE factor_id=? AND version=?",
                    (fid, prev))
        con.execute("INSERT INTO factor_audit_log(factor_id,version,action,field_name,old_value,new_value,changed_at,"
                    "changed_by,reason,reference_id) VALUES (?,?,'superseded','verification_status',NULL,'superseded',?,?,?,?)",
                    (fid, prev, now_iso(), user, reason, reference_id))


def _log(con, source, outcome, detail):
    with transaction(con):
        con.execute("INSERT INTO update_log(at,source,outcome,detail) VALUES (?,?,?,?)", (now_iso(), source, outcome, detail))


def factor_file_template() -> pd.DataFrame:
    return pd.DataFrame([{c: "" for c in REQUIRED + OPTIONAL}])
