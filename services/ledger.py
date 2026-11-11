"""Activity ledger: persist records, calculate with the existing engine, aggregate by period/scope.

Principles:
* A record stores a SNAPSHOT of the factor + result at calculation time. Library updates never
  recompute stored rows (use recalculate_record explicitly, which writes a NEW record and keeps the old).
* No date is ever invented. Missing date -> record kept with calc_status 'needs_date' (no month/year bucket).
* Missing factor -> 'needs_factor' (never 0). Incompatible units -> 'rejected_unit' stored with the reason.
* Dashboard, Reports and exports all use `fetch_records(filters)` + `summarize()`, so numbers match.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import pandas as pd

from db.connection import now_iso, transaction
from schemas.domain import (ActivityInput, D, EmissionFactor, FactorClass, GasComponent,
                            ValueBasis, VerificationStatus)
from services import calculations as calc
from services import unit_conversion as uc
from services.scope_classifier import ScopeSuggestion, classify

COLS_TO_AR = {  # original demo column names are preserved for compatibility
    "activity_name": "النشاط", "scope": "النطاق", "quantity": "الكمية", "unit": "الوحدة",
    "factor_value": "معامل الانبعاث", "factor_source": "المصدر",
}


def fingerprint(*parts) -> str:
    norm = "|".join("" if p is None else str(p).strip().lower() for p in parts)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def parse_date(v) -> date | None:
    """Strict parse. Returns None when absent/invalid - callers must NOT substitute today's date."""
    if v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() in ("", "nan", "NaT", "None"):
        return None
    if isinstance(v, (datetime, pd.Timestamp)):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognised date: {s!r}")


def _fmt(d: Decimal | None) -> str | None:
    return None if d is None else format(d.normalize(), "f") if d != 0 else "0"


def _calc(*, quantity: Decimal, unit: str, country: str, year: int | None, category: str, activity: str,
          factor: EmissionFactor | None, proxy_confirmed: bool, gwp_set=None,
          nearest_year_ok: bool = False):
    """Returns (status, result|None, notes)."""
    if factor is None:
        return "needs_factor", None, "No factor selected / none matched in the library."
    undated_note = ""
    if year is None:
        if factor.classification == FactorClass.USER_SUPPLIED:
            year = factor.year_from  # user-entered factors carry no validity period to violate
            undated_note = "Undated record: excluded from monthly/annual views. "
        else:
            return "needs_date", None, "Activity date missing: factor validity year cannot be checked."
    act = ActivityInput(quantity, unit, country, year, factor.category, factor.activity)
    try:
        res = calc.calculate(act, factor, gwp_set=gwp_set, proxy_confirmed=proxy_confirmed,
                             allow_superseded=False, allow_year_mismatch=nearest_year_ok)
    except calc.ProxyNotConfirmedError as e:
        return "needs_review", None, str(e)
    except calc.CalculationError as e:
        msg = str(e)
        return ("rejected_unit" if msg.startswith("Unit problem") else "needs_review"), None, msg
    return "calculated", res, undated_note + "; ".join(res.warnings + res.steps)


def user_factor(value, *, country: str, category: str, activity: str, unit: str, year: int,
                source: str, url: str | None = None) -> EmissionFactor:
    """Wrap a manually typed factor. Always UNVERIFIED / USER_SUPPLIED - never presented as official."""
    return EmissionFactor(
        factor_id=f"USER-{fingerprint(category, activity, unit, value, source)[:10]}", version=1, country=country,
        category=category, activity=activity, numerator_unit="kg CO2e", denominator_unit=unit,
        total_co2e=D(value), components=(), year_from=year, year_to=year, classification=FactorClass.USER_SUPPLIED,
        status=VerificationStatus.UNVERIFIED, source_org=source or "user supplied", source_title=source or "user supplied",
        source_url=url or None, source_locator="manual entry", gwp_set_id=None,
        methodology="user-entered value; not verified by the platform")


def add_record(con, *, activity_name: str, quantity, unit: str, country_code: str | None, activity_date=None,
               description: str = "", company_id=None, facility_id=None, industry_sector=None,
               fuel_or_material: str | None = None, category_key: str | None = None,
               factor: EmissionFactor | None = None, factor_selection_reason: str = "",
               proxy_confirmed: bool = False, ownership_control: str = "unknown",
               energy_purchased: str = "unknown", value_chain_relation: str = "unknown",
               scope_override: tuple[str, str | None, str] | None = None,   # (scope, subcat, reason)
               given_scope: str | None = None, scope2_method: str | None = None, notes: str = "",
               evidence_ref: str | None = None, origin: str = "manual", batch_id=None,
               allow_duplicate: bool = False, user: str | None = None, gwp_set=None,
               nearest_year_ok: bool = False) -> dict:
    """Insert one record. Returns {'record_id','duplicate','status',...}. Never raises on data problems that
    should instead be stored as review states; raises ValueError only for malformed required inputs."""
    if not str(activity_name or "").strip():
        raise ValueError("activity_name required")
    try:
        q = D(quantity)
    except (InvalidOperation, TypeError) as e:
        raise ValueError(f"invalid quantity: {quantity!r}") from e
    if q < 0:
        raise ValueError("quantity must be >= 0")
    d = parse_date(activity_date)
    year, month = (d.year, d.month) if d else (None, None)

    sug = classify(category_key=category_key, ownership_control=ownership_control, energy_purchased=energy_purchased,
                   value_chain_relation=value_chain_relation, description=description)
    scope, sub, s3, sstatus, sconf = sug.scope, sug.subcategory, sug.scope3_category, sug.status, sug.confidence
    sreason, smissing, override = sug.reason, ",".join(sug.missing), 0
    if given_scope and scope_override is None:
        # scope supplied by the file/user (e.g. legacy demo rows): keep it, mark as user-provided
        scope, sstatus, sconf, override = given_scope, "confirmed", "user_provided", 1
        sreason, smissing, sub = "Scope provided with the data (not derived by the platform)", "", sub or None
    if scope_override:
        scope, sub, reason = scope_override
        sstatus, sconf, override, sreason, smissing = "confirmed", "user_override", 1, f"Manual: {reason}", ""

    if scope2_method == "market" and (scope == "Scope 2") and factor is None:
        status, res, cnotes = "needs_factor", None, "Market-based Scope 2 requires supplier/contract-specific factor evidence."
    else:
        status, res, cnotes = _calc(quantity=q, unit=unit, country=country_code or "", year=year,
                                    category=(factor.category if factor else category_key or "other"),
                                    activity=(factor.activity if factor else "n/a"), factor=factor,
                                    proxy_confirmed=proxy_confirmed, gwp_set=gwp_set,
                                    nearest_year_ok=nearest_year_ok)

    fp = fingerprint(activity_name, d, q, unit, country_code, company_id, facility_id,
                     factor.factor_id if factor else None, fuel_or_material)
    dup = con.execute("SELECT record_id FROM activity_records WHERE fingerprint=?", (fp,)).fetchone()
    if dup and not allow_duplicate:
        return {"record_id": dup["record_id"], "duplicate": True, "status": "duplicate", "inserted": False}
    if dup:
        fp = f"{fp}:{now_iso()}:{hashlib.sha1(str(id(object())).encode()).hexdigest()[:6]}"

    snap = res.factor_snapshot if res else (factor.snapshot() if factor else None)
    with transaction(con):
        cur = con.execute(
            "INSERT INTO activity_records(fingerprint,activity_name,description,company_id,facility_id,country_code,"
            "industry_sector,activity_date,activity_year,activity_month,quantity,unit,fuel_or_material,category_key,"
            "scope,scope_subcategory,scope3_category,scope_status,scope_confidence,scope_reason,scope_missing_info,"
            "scope_manual_override,scope2_method,ownership_control,energy_purchased,value_chain_relation,factor_id,"
            "factor_version,factor_snapshot_json,factor_value,factor_unit,factor_source,factor_source_url,factor_class,"
            "factor_verification,factor_selection_reason,kg_co2e,t_co2e,calc_status,calc_notes,engine_version,"
            "data_verification,notes,evidence_ref,origin,imported_batch_id,created_at) "
            "VALUES (" + ",".join("?" * 47) + ")",
            (fp, activity_name.strip(), description, company_id, facility_id, country_code, industry_sector,
             d.isoformat() if d else None, year, month, str(q), unit, fuel_or_material, category_key, scope, sub, s3,
             sstatus, sconf, sreason, smissing, override, scope2_method, ownership_control, energy_purchased,
             value_chain_relation, factor.factor_id if factor else None, factor.version if factor else None,
             json.dumps(snap) if snap else None,
             _fmt(factor.total_co2e) if factor and factor.total_co2e is not None else None,
             f"kg CO2e/{factor.denominator_unit}" if factor else None, factor.source_org if factor else None,
             factor.source_url if factor else None, factor.classification.value if factor else None,
             factor.status.value if factor else None, factor_selection_reason, _fmt(res.kg_co2e) if res else None,
             _fmt(res.t_co2e) if res else None, status, cnotes, res.engine_version if res else None,
             "verified" if (res and not res.is_estimate) else "unverified", notes, evidence_ref, origin, batch_id,
             now_iso()))
    return {"record_id": cur.lastrowid, "duplicate": False, "status": status, "inserted": True, "scope": scope,
            "scope_status": sstatus, "notes": cnotes}


def override_scope(con, record_id: int, new_scope: str, new_sub: str | None, reason: str, user: str | None) -> None:
    """Manual scope correction. Logged; the calculation result and factor snapshot are NOT touched."""
    if new_scope not in ("Scope 1", "Scope 2", "Scope 3"):
        raise ValueError("invalid scope")
    if not reason or not reason.strip():
        raise ValueError("a reason is required")
    with transaction(con):
        r = con.execute("SELECT scope, scope_subcategory FROM activity_records WHERE record_id=?", (record_id,)).fetchone()
        if r is None:
            raise LookupError("record not found")
        con.execute("INSERT INTO scope_audit_log(record_id,old_scope,new_scope,old_subcategory,new_subcategory,"
                    "changed_at,changed_by,reason) VALUES (?,?,?,?,?,?,?,?)",
                    (record_id, r["scope"], new_scope, r["scope_subcategory"], new_sub, now_iso(), user, reason))
        con.execute("UPDATE activity_records SET scope=?, scope_subcategory=?, scope_status='confirmed', "
                    "scope_confidence='user_override', scope_manual_override=1, scope_reason=?, scope_missing_info='' "
                    "WHERE record_id=?", (new_scope, new_sub, f"Manual: {reason}", record_id))


# ---------------- querying / aggregation (single source for Dashboard, Reports, exports) ----------------

def fetch_records(con, *, country=None, company_id=None, facility_id=None, year=None, month=None,
                  date_from=None, date_to=None, scope=None, category_key=None, calc_status=None) -> pd.DataFrame:
    q = ("SELECT r.*, c.name AS company_name, f.name AS facility_name FROM activity_records r "
         "LEFT JOIN companies c ON c.company_id=r.company_id LEFT JOIN facilities f ON f.facility_id=r.facility_id WHERE 1=1")
    p: list = []
    for col, val in (("r.country_code", country), ("r.company_id", company_id), ("r.facility_id", facility_id),
                     ("r.activity_year", year), ("r.activity_month", month), ("r.scope", scope),
                     ("r.category_key", category_key), ("r.calc_status", calc_status)):
        if val not in (None, ""):
            q += f" AND {col}=?"; p.append(val)
    if date_from:
        q += " AND r.activity_date>=?"; p.append(str(date_from))
    if date_to:
        q += " AND r.activity_date<=?"; p.append(str(date_to))
    df = pd.read_sql_query(q + " ORDER BY r.activity_date, r.record_id", con, params=p)
    df["kg"] = df["kg_co2e"].apply(lambda v: Decimal(v) if v not in (None, "") else None)
    return df


def _sum(series) -> Decimal:
    return sum((v for v in series if isinstance(v, Decimal)), Decimal(0))


def summarize(df: pd.DataFrame, *, year: int | None = None) -> dict:
    """Totals use ONLY calculated rows. Rows that need a factor/date/review are counted separately and
    never contribute 0 silently."""
    calc_df = df[df["calc_status"] == "calculated"] if not df.empty else df
    total = _sum(calc_df["kg"]) if not calc_df.empty else Decimal(0)
    by_scope = {s: (_sum(calc_df.loc[calc_df["scope"] == s, "kg"]) if not calc_df.empty else Decimal(0))
                for s in ("Scope 1", "Scope 2", "Scope 3")}
    unscoped = _sum(calc_df.loc[calc_df["scope"].isna(), "kg"]) if not calc_df.empty else Decimal(0)
    monthly = {}
    if not calc_df.empty:
        for (y, m), g in calc_df.groupby(["activity_year", "activity_month"]):
            monthly[(int(y), int(m))] = _sum(g["kg"])
    months_with_data = len(monthly)
    avg_active = (total / months_with_data) if months_with_data else None
    avg_12 = (total / 12) if (year is not None and months_with_data) else None
    n = len(df)
    n_calc = 0 if df.empty else int((df["calc_status"] == "calculated").sum())
    n_verified_factor = 0 if df.empty else int(((df["calc_status"] == "calculated") & (df["factor_verification"] == "verified")).sum())
    undated = _sum(calc_df.loc[calc_df["activity_year"].isna(), "kg"]) if not calc_df.empty else Decimal(0)
    return {"undated_kg": undated, "total_kg": total, "total_t": total / 1000, "by_scope_kg": by_scope, "unscoped_kg": unscoped,
            "monthly_kg": dict(sorted(monthly.items())), "avg_monthly_active_kg": avg_active,
            "avg_monthly_12_kg": avg_12, "months_with_data": months_with_data, "records": n, "calculated": n_calc,
            "verified_factor_records": n_verified_factor,
            "needs_review": 0 if df.empty else int((df["calc_status"] != "calculated").sum()
                                                    + ((df["calc_status"] == "calculated") & (df["scope_status"] != "confirmed")
                                                       & (df["scope_status"] != "suggested")).sum()),
            "verified_pct_definition": "calculated records whose factor status is 'verified' / all records in the filter",
            "verified_pct": (100.0 * n_verified_factor / n) if n else None}


def yearly_totals(df: pd.DataFrame) -> dict:
    out: dict = {}
    if df.empty:
        return out
    c = df[df["calc_status"] == "calculated"]
    for y, g in c.groupby("activity_year"):
        out[int(y)] = _sum(g["kg"])
    return out


def top_sources(df: pd.DataFrame, n=5):
    c = df[df["calc_status"] == "calculated"] if not df.empty else df
    if c.empty:
        return []
    g = {name: _sum(grp["kg"]) for name, grp in c.groupby("activity_name")}
    return sorted(g.items(), key=lambda kv: kv[1], reverse=True)[:n]


# ---------------- companies / facilities ----------------

def upsert_company(con, name, country_code=None, sector=None, boundary_approach=None, boundary_notes=None) -> int:
    with transaction(con):
        con.execute("INSERT OR IGNORE INTO companies(name,country_code,industry_sector,boundary_approach,boundary_notes,"
                    "created_at) VALUES (?,?,?,?,?,?)", (name.strip(), country_code, sector, boundary_approach,
                                                         boundary_notes, now_iso()))
        return con.execute("SELECT company_id FROM companies WHERE name=? AND country_code IS ?",
                           (name.strip(), country_code)).fetchone()["company_id"]


def add_facility(con, company_id, name, country_code=None, internal_ref=None, control_status="unknown") -> int:
    with transaction(con):
        con.execute("INSERT OR IGNORE INTO facilities(company_id,name,country_code,internal_ref,control_status,created_at)"
                    " VALUES (?,?,?,?,?,?)", (company_id, name.strip(), country_code, internal_ref, control_status, now_iso()))
        return con.execute("SELECT facility_id FROM facilities WHERE company_id=? AND name=?",
                           (company_id, name.strip())).fetchone()["facility_id"]


# ---------------- legacy session-state rows -> database (explicit action only) ----------------

def migrate_session_rows(con, df: pd.DataFrame, *, origin="migrated_session") -> dict:
    """Copy the original demo/session rows (Arabic columns) into the DB WITHOUT dates (never invented),
    with the scope and factor they already carry, marked user-supplied/unverified. Duplicates skipped.
    Session values are floats; they are converted via str() (shortest repr) because the engine rejects floats."""
    added = skipped = 0
    errors = []
    for i, r in df.iterrows():
        try:
            fac = user_factor(str(r["معامل الانبعاث"]), country="", category="legacy", activity=str(r["النشاط"]),
                              unit=str(r["الوحدة"]), year=0, source=str(r.get("المصدر", "") or "legacy session row"))
            res = add_record(con, activity_name=str(r["النشاط"]), quantity=str(r["الكمية"]), unit=str(r["الوحدة"]),
                             country_code=None, activity_date=None, factor=fac, given_scope=str(r["النطاق"]),
                             origin=origin, notes="Migrated from session; no date available")
            if res["duplicate"]:
                skipped += 1
            else:
                added += 1
        except Exception as exc:
            errors.append((int(i), str(exc)))
    return {"added": added, "skipped_duplicates": skipped, "failed": len(errors), "errors": errors}
