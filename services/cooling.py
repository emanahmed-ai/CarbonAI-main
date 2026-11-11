"""References library + refrigerants & cooling module.

Reference library: searchable catalogue of international standards and Egyptian sources with
official URLs only where verified (null otherwise). Standards/methodologies are explicitly NOT
treated as emission-factor databases.

Refrigerants: GWP-100 per IPCC basis (AR4/AR5/AR6), blends computed by mass fraction when the
report publishes individual gases, equipment inventory, maintenance/leakage records and
calculations through the existing engine. Recovery is subtracted; the full charge is never
assumed leaked; no leakage rate is invented.
"""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from db.connection import now_iso, transaction
from schemas.domain import D
from services import calculations as calc
from services import factor_library as FL
from services import ledger as L

SEED_DIR = Path(__file__).resolve().parent.parent / "database" / "seed"
REF_LIB_PATH = SEED_DIR / "reference_library.json"
REFRIG_PATH = SEED_DIR / "refrigerants.json"

BASES = ("AR4", "AR5", "AR6")
BASIS_SOURCE = {"AR4": "IPCC-AR4-GWP100", "AR5": "IPCC-AR5-GWP100", "AR6": "IPCC-AR6-GWP100"}
BASIS_LABEL = {"AR4": "IPCC AR4 (2007) GWP-100", "AR5": "IPCC AR5 (2014) GWP-100",
               "AR6": "IPCC AR6 (2021) GWP-100"}
BASIS_URL = {"AR4": "https://www.ipcc.ch/report/ar4/syr/",
             "AR5": "https://www.ipcc.ch/report/ar5/syr/",
             "AR6": "https://www.ipcc.ch/report/ar6/syr/"}


class CoolingError(ValueError):
    pass


# ---------------- reference library ----------------

def seed_reference_library(con) -> int:
    if not REF_LIB_PATH.exists():
        return 0
    doc = json.loads(REF_LIB_PATH.read_text(encoding="utf-8"))
    n = 0
    with transaction(con):
        for e in doc["entries"]:
            n += con.execute(
                "INSERT OR IGNORE INTO reference_library(ref_key,title,organization,edition,"
                "publication_year,url,kind,country_applicability,sectors,methodology_support,"
                "chapter_section,access_date,notes,verification_status) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'unverified')",
                (e["ref_key"], e["title"], e["organization"], e.get("edition"),
                 e.get("publication_year"), e.get("url"), e["kind"],
                 e.get("country_applicability") or "GLOBAL", e.get("sectors"),
                 e.get("methodology_support"), e.get("chapter_section"),
                 e.get("access_date"), e.get("notes"))).rowcount
    return n


def list_references(con, *, kind=None, country=None, q=None) -> list[dict]:
    sql = "SELECT * FROM reference_library WHERE 1=1"
    p: list = []
    if kind:
        sql += " AND kind=?"; p.append(kind)
    if country:
        sql += " AND country_applicability=?"; p.append(country)
    if q:
        sql += " AND (title LIKE ? OR organization LIKE ? OR sectors LIKE ?)"
        p += [f"%{q}%"] * 3
    return [dict(r) for r in con.execute(sql + " ORDER BY kind, organization, ref_key", p).fetchall()]


# ---------------- refrigerants ----------------

def _load_refrigerants() -> dict:
    return json.loads(REFRIG_PATH.read_text(encoding="utf-8"))


def refrigerant_rows() -> list[dict]:
    """Resolve GWP values per basis; blends compute from component mass fractions when the
    report value is not available. Computed values are flagged in basis_notes."""
    doc = _load_refrigerants()
    rows = []
    for r in doc["refrigerants"]:
        gwps = {b: (None, None) for b in BASES}
        notes = []
        comps = r.get("components")
        for basis, (val, how) in r["gwp"].items():
            if val is not None:
                gwps[basis] = (val, how)
            elif comps:
                total = Decimal(0)
                ok = True
                for comp_key, frac in comps:
                    comp = next((x for x in doc["refrigerants"] if x["key"] == comp_key), None)
                    if not comp or comp["gwp"].get(basis, [None])[0] is None:
                        ok = False
                        break
                    total += D(comp["gwp"][basis][0]) * D(str(frac))
                if ok:
                    gwps[basis] = (str(total.quantize(Decimal("1"))), "computed")
                    notes.append(f"{basis} blend GWP computed by mass fraction from component values")
        rows.append({
            "key": r["key"], "designation": r["designation"], "chemical_name": r["chemical_name"],
            "formula": r["formula"], "family": r["family"], "components": comps,
            "gwp": {b: gwps[b][0] for b in BASES},
            "gwp_method": {b: gwps[b][1] for b in BASES},
            "applications": r.get("applications"),
            "basis_notes": "; ".join(notes) if notes else
            "GWP-20/GWP-500 not recorded in this build; GWP-100 is the calculation basis.",
        })
    return rows


def seed_refrigerants(con) -> dict:
    rows = refrigerant_rows()
    n_ref = n_fac = n_src = 0
    with transaction(con):
        for b, label in BASIS_SOURCE.items():
            n_src += con.execute(
                "INSERT OR IGNORE INTO sources(reference_id,organization_name,organization_type,"
                "document_title,publication_year,source_url,methodology_description,geographic_scope,"
                "license_or_usage_notes,last_checked_at,verification_status) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,'unverified')",
                (label, "IPCC", "international", f"{BASIS_LABEL[b]} values",
                 2007 if b == "AR4" else 2014 if b == "AR5" else 2021, BASIS_URL[b],
                 f"GWP-100 values per IPCC {b}; applied to refrigerant leakage.",
                 "GLOBAL", "IPCC assessment report, free with attribution.", "2026-11-03")).rowcount
        for r in rows:
            n_ref += con.execute(
                "INSERT OR IGNORE INTO refrigerants(refrigerant_key,designation,chemical_name,formula,"
                "family,components_json,gwp_100_ar4,gwp_100_ar5,gwp_100_ar6,gwp_20_ar5,gwp_500_ar5,"
                "basis_notes,source_ref,verification_status,is_active) "
                "VALUES (?,?,?,?,?,?,?,?,?,NULL,NULL,?,?,'unverified',1)",
                (r["key"], r["designation"], r["chemical_name"], r["formula"], r["family"],
                 json.dumps(r["components"]) if r["components"] else None,
                 r["gwp"]["AR4"], r["gwp"]["AR5"], r["gwp"]["AR6"],
                 r["basis_notes"] + (f" Applications: {r['applications']}." if r.get("applications") else ""),
                 BASIS_SOURCE["AR5"])).rowcount
            for basis in BASES:
                val = r["gwp"][basis]
                if val is None:
                    continue
                fid = f"REF-{r['key']}-{basis}"
                year = 2007 if basis == "AR4" else 2014 if basis == "AR5" else 2021
                cols = {
                    "factor_id": fid, "version": 1,
                    "factor_name_en": f"refrigerant / {r['designation']}",
                    "country_code": "GLOBAL", "factor_class": "global_default",
                    "activity_category": "refrigerant", "activity": r["key"],
                    "activity_unit": "kg", "factor_unit": "kg CO2e/kg",
                    "co2e_factor_value": val, "components_json": "[]", "gwp_set_id": None,
                    "reference_id": BASIS_SOURCE[basis], "source_organization": "IPCC",
                    "source_document": BASIS_LABEL[basis], "source_url": BASIS_URL[basis],
                    "source_locator": f"{BASIS_LABEL[basis]} - refrigerant table",
                    "publication_year": year, "year_from": 2006, "year_to": 2026,
                    "geographic_coverage": "GLOBAL",
                    "methodology": f"Direct leakage emissions = leaked kg x GWP-100 ({basis}).",
                    "boundary_note": f"Fugitive leakage only. GWP basis {basis} recorded; never mixed.",
                    "verification_status": "unverified", "notes": r["basis_notes"],
                    "created_at": now_iso(), "gas_type": r["designation"],
                    "sector": "Refrigerants", "fuel_type": None, "technology": r["designation"],
                    "gas": r["designation"], "country_scope": "international_default",
                    "quality_level": "IPCC GWP-100", "uncertainty": None,
                    "data_year": year, "source_page": None, "source_table": f"GWP-100 ({basis})",
                }
                names = ", ".join(cols)
                marks = ", ".join("?" for _ in cols)
                n_fac += con.execute(
                    f"INSERT OR IGNORE INTO emission_factors({names}) VALUES ({marks})",
                    tuple(cols.values())).rowcount
    return {"refrigerants": n_ref, "factors": n_fac, "sources": n_src}


def list_refrigerants(con) -> list[dict]:
    rows = [dict(r) for r in con.execute(
        "SELECT * FROM refrigerants WHERE is_active=1 ORDER BY family, designation").fetchall()]
    for r in rows:
        r["components"] = json.loads(r["components_json"] or "null")
    return rows


def get_refrigerant(con, key: str) -> dict | None:
    r = con.execute("SELECT * FROM refrigerants WHERE refrigerant_key=?", (key,)).fetchone()
    return None if r is None else dict(r)


def gwp_for(con, key: str, basis: str) -> tuple[Decimal, dict]:
    if basis not in BASES:
        raise CoolingError(f"gwp_basis must be one of {BASES}")
    ref = get_refrigerant(con, key)
    if ref is None:
        raise CoolingError(f"unknown refrigerant {key}")
    col = f"gwp_100_{basis.lower()}"
    val = ref[col]
    if val is None:
        raise CoolingError(f"No authoritative GWP-100 ({basis}) recorded for {ref['designation']}. "
                           f"Choose another basis or add the value with a cited source.")
    return D(str(val)), ref


# ---------------- equipment & service records ----------------

EQUIPMENT_TYPES = ("commercial_ac", "central_hvac", "chiller", "refrigerator_freezer",
                   "industrial_refrigeration", "cold_storage", "other")


def add_equipment(con, *, facility_id: int, company_id: int, identifier: str, equipment_type: str,
                  refrigerant_key: str | None, charge_kg: str | None, installed_year: int | None,
                  notes: str = "", user: str) -> dict:
    if not (identifier or "").strip():
        raise CoolingError("equipment identifier is required")
    if equipment_type not in EQUIPMENT_TYPES:
        raise CoolingError(f"equipment_type must be one of {', '.join(EQUIPMENT_TYPES)}")
    if refrigerant_key and get_refrigerant(con, refrigerant_key) is None:
        raise CoolingError("unknown refrigerant")
    if charge_kg is not None and D(charge_kg) < 0:
        raise CoolingError("charge_kg must be >= 0")
    with transaction(con):
        cur = con.execute(
            "INSERT OR IGNORE INTO cooling_equipment(facility_id,company_id,identifier,equipment_type,"
            "refrigerant_key,charge_kg,installed_year,notes,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (facility_id, company_id, identifier.strip(), equipment_type, refrigerant_key,
             charge_kg, installed_year, notes, now_iso()))
        row = con.execute("SELECT * FROM cooling_equipment WHERE facility_id=? AND identifier=?",
                          (facility_id, identifier.strip())).fetchone()
    if cur.rowcount == 0:
        raise CoolingError(f"equipment '{identifier}' already exists for this facility")
    return dict(row)


def list_equipment(con, *, company_id=None, facility_id=None) -> list[dict]:
    sql = ("SELECT e.*, f.name AS facility_name, "
           "(SELECT COUNT(*) FROM refrigerant_service_records r WHERE r.equipment_id=e.equipment_id) "
           "AS services, (SELECT COALESCE(SUM(CAST(r2.kg_co2e AS REAL)),0) FROM refrigerant_service_records r2 "
           "WHERE r2.equipment_id=e.equipment_id) AS total_kg FROM cooling_equipment e "
           "JOIN facilities f ON f.facility_id=e.facility_id WHERE 1=1")
    p: list = []
    if facility_id:
        sql += " AND e.facility_id=?"; p.append(facility_id)
    elif company_id:
        sql += " AND e.company_id=?"; p.append(company_id)
    return [dict(r) for r in con.execute(sql + " ORDER BY e.equipment_id DESC", p).fetchall()]


def add_service_record(con, *, equipment_id: int, service_date: str, gwp_basis: str,
                       added_kg: str | None = None, recovered_kg: str | None = None,
                       leaked_kg: str | None = None, ownership_control: str = "owned_controlled",
                       evidence_ref: str | None = None, notes: str = "",
                       user: str) -> dict:
    """Record a maintenance event and calculate fugitive emissions.

    Leakage rules (documented in the record's methodology):
      * explicit leaked_kg wins (measured/estimated by the technician, recorded as given);
      * otherwise leaked = max(0, added - recovered): gas added to top up = atmospheric loss,
        minus gas recovered (recovered refrigerant is not an atmospheric emission);
      * the full charge is NEVER assumed to have leaked;
      * no default leakage rate is applied - a missing quantity is an error, not a guess.
    """
    eq = con.execute("SELECT e.*, f.company_id AS f_company FROM cooling_equipment e "
                     "JOIN facilities f ON f.facility_id=e.facility_id WHERE e.equipment_id=?",
                     (equipment_id,)).fetchone()
    if eq is None:
        raise CoolingError("equipment not found")
    d = L.parse_date(service_date)
    if d is None:
        raise CoolingError("service_date is required (YYYY-MM-DD)")
    ref_key = eq["refrigerant_key"]
    if not ref_key:
        raise CoolingError("equipment has no refrigerant assigned; set it before recording service")
    if added_kg in (None, "") and recovered_kg in (None, "") and leaked_kg in (None, ""):
        raise CoolingError("provide at least one quantity: added_kg, recovered_kg or leaked_kg "
                           "(a missing quantity is never assumed to be zero leakage)")
    added = D(added_kg) if added_kg not in (None, "") else D(0)
    recovered = D(recovered_kg) if recovered_kg not in (None, "") else D(0)
    if added < 0 or recovered < 0:
        raise CoolingError("added/recovered quantities must be >= 0")
    if leaked_kg not in (None, ""):
        leaked = D(leaked_kg)
        if leaked < 0:
            raise CoolingError("leaked_kg must be >= 0")
        methodology = "Explicit leakage quantity recorded by the technician."
    else:
        leaked = added - recovered if added > recovered else D(0)
        methodology = ("Leakage = added - recovered (recovered gas is not an atmospheric emission); "
                       "full charge is never assumed leaked.")
    gwp, ref_row = gwp_for(con, ref_key, gwp_basis)
    kg = calc.refrigerant_leakage(leaked, gwp, refrigerant=ref_row["designation"],
                                  gwp_source=BASIS_LABEL[gwp_basis])
    t = calc.kg_to_tonnes(kg)
    factor = FL.get_factor(con, f"REF-{ref_key}-{gwp_basis}")
    if factor is None:
        raise CoolingError(f"library factor REF-{ref_key}-{gwp_basis} is missing; reseed refrigerants")
    res = L.add_record(
        con, activity_name=f"{ref_row['designation']} leakage - {eq['identifier']}",
        quantity=str(leaked), unit="kg", country_code="EG", activity_date=service_date,
        description=f"Refrigerant service record (equipment {eq['identifier']})",
        company_id=eq["f_company"], facility_id=eq["facility_id"], category_key="refrigerant",
        factor=factor, factor_selection_reason=f"Refrigerant DB GWP basis {gwp_basis}",
        proxy_confirmed=True, ownership_control=ownership_control,
        energy_purchased="unknown", value_chain_relation="on_site_controlled",
        notes=methodology, evidence_ref=evidence_ref, origin="cooling_service", user=user)
    if res.get("duplicate"):
        raise CoolingError(f"an identical refrigerant record already exists (#{res['record_id']})")
    with transaction(con):
        cur = con.execute(
            "INSERT INTO refrigerant_service_records(equipment_id,facility_id,service_date,"
            "refrigerant_key,added_kg,recovered_kg,leaked_kg,gwp_basis,gwp_value,leaked_calculated_kg,"
            "kg_co2e,t_co2e,record_id,methodology,evidence_ref,notes,created_by,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (equipment_id, eq["facility_id"], d.isoformat(), ref_key,
             str(added), str(recovered), None if leaked_kg in (None, "") else str(D(leaked_kg)),
             gwp_basis, str(gwp), str(leaked), str(kg), str(t), res["record_id"], methodology,
             evidence_ref, notes, user, now_iso()))
    return {"service_id": cur.lastrowid, "record_id": res["record_id"], "status": res["status"],
            "refrigerant": ref_row["designation"], "gwp_basis": gwp_basis, "gwp": str(gwp),
            "added_kg": str(added), "recovered_kg": str(recovered), "leaked_kg": str(leaked),
            "kg_co2e": str(kg), "t_co2e": str(t), "methodology": methodology}


def list_service_records(con, *, company_id=None, facility_id=None, equipment_id=None,
                         year=None) -> list[dict]:
    sql = ("SELECT r.*, e.identifier, e.equipment_type, e.company_id, f.name AS facility_name "
           "FROM refrigerant_service_records r JOIN cooling_equipment e ON e.equipment_id=r.equipment_id "
           "JOIN facilities f ON f.facility_id=e.facility_id WHERE 1=1")
    p: list = []
    for col, val in (("e.company_id", company_id), ("e.facility_id", facility_id),
                     ("r.equipment_id", equipment_id)):
        if val:
            sql += f" AND {col}=?"; p.append(val)
    if year:
        sql += " AND substr(r.service_date,1,4)=?"; p.append(str(year))
    return [dict(r) for r in con.execute(sql + " ORDER BY r.service_date DESC, r.service_id DESC", p).fetchall()]


def kpi(con, *, company_id=None, facility_id=None, year=None) -> dict:
    """Refrigerant Scope 1 KPI from the ledger (calculated records only), plus equipment breakdown."""
    df = L.fetch_records(con, company_id=company_id, facility_id=facility_id, year=year,
                         category_key="refrigerant")
    total = Decimal(0)
    by_equipment: dict[str, Decimal] = {}
    records = 0
    if not df.empty:
        calc_df = df[df["calc_status"] == "calculated"]
        records = int(len(df))
        total = L._sum(calc_df["kg"])
        for _, r in calc_df.iterrows():
            by_equipment[r["activity_name"]] = by_equipment.get(r["activity_name"], Decimal(0)) + r["kg"]
    scope1 = L.summarize(df).get("by_scope_kg", {}).get("Scope 1", Decimal(0))
    scope1_all = Decimal(0)
    all_df = L.fetch_records(con, company_id=company_id, facility_id=facility_id, year=year)
    if not all_df.empty:
        s = L.summarize(all_df)
        scope1_all = s["by_scope_kg"]["Scope 1"]
    return {
        "refrigerant_kg": str(total), "refrigerant_t": str(total / 1000),
        "share_of_scope1_pct": None if scope1_all <= 0 else round(float(total / scope1_all * 100), 1),
        "records": records,
        "by_equipment": sorted([{"equipment": k, "kg": str(v)} for k, v in by_equipment.items()],
                               key=lambda x: -float(x["kg"]))[:10],
        "note": "Only calculated records count. Refrigerant leakage is Scope 1; electricity for "
                "cooling is entered separately as Scope 2 and is never double counted here.",
    }
