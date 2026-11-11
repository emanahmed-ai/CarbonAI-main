"""Egypt emission factors: loader, idempotent seeder, and the 2006-2026 coverage matrix.

Rules enforced here (see the client specification):
* every factor has an explicit country_scope classification: egypt_official |
  egypt_research | international_egypt_specific | international_default;
* values are never invented - the seed file carries exact source locators;
* every year 2006-2026 gets an explicit coverage status for every catalogued activity;
* seeding is INSERT OR IGNORE only: re-running never overwrites and never deletes.
"""
from __future__ import annotations

import json
from pathlib import Path

from db.connection import now_iso, transaction

SEED_DIR = Path(__file__).resolve().parent.parent / "database" / "seed"
FACTORS_PATH = SEED_DIR / "egypt_factors_2006_2026.json"
COVERAGE_PATH = SEED_DIR / "egypt_coverage_2006_2026.json"

YEAR_FROM, YEAR_TO = 2006, 2026
STATUSES = ("available", "provisional", "estimated", "international_default",
            "pending", "unavailable", "not_applicable")


def load_seed() -> dict:
    return json.loads(FACTORS_PATH.read_text(encoding="utf-8"))


def build_coverage() -> list[dict]:
    """Expand the catalog into one explicit row per (year, activity). Written by
    scripts/build_egypt_seed.py to seed/egypt_coverage_2006_2026.json."""
    doc = load_seed()
    rows = []
    for year in range(YEAR_FROM, YEAR_TO + 1):
        for item in doc["coverage_catalog"]:
            status = item["status"]
            reason = item["reason"]
            source = item["source"]
            if status == "covered_from_2024":
                if year == 2024:
                    status, reason = "available", "EEHC Annual Report 2023/2024 (380.3 ton CO2/GWh, FY2023/2024)."
                elif year < 2024:
                    status = "pending"
                    reason = ("EEHC annual report for this year has not been inspected in this build; "
                              "the FY2023/24 figure must not be reused for earlier years.")
                else:  # 2025, 2026
                    status = "pending"
                    reason = ("No published EEHC report has been verified for this reporting year yet "
                              "(FY2024/25+). Do not treat FY2023/24 data as actual data for this year.")
            rows.append({
                "country_code": "EG", "year": year, "sector": item["sector"],
                "activity": item["activity"], "gas": "CO2e", "coverage_status": status,
                "available_source": source, "missing_reason": None if status in
                ("available", "international_default") else reason,
                "review_date": "2026-11-03", "reviewer": "system-audit",
            })
    return rows


def seed_sources(con) -> int:
    doc, n = load_seed(), 0
    with transaction(con):
        for s in doc["sources"]:
            n += con.execute(
                "INSERT OR IGNORE INTO sources(reference_id,organization_name,organization_type,"
                "document_title,document_version,publication_year,publication_date,source_url,"
                "methodology_description,geographic_scope,license_or_usage_notes,last_checked_at,"
                "verification_status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'unverified')",
                (s["reference_id"], s["organization_name"], s.get("organization_type"),
                 s["document_title"], s.get("document_version"), s.get("publication_year"),
                 s.get("publication_date"), s.get("source_url"), s.get("methodology_description"),
                 s.get("geographic_scope"), s.get("license_or_usage_notes"), "2026-11-03")).rowcount
    return n


def seed_factors(con) -> int:
    """Insert each seed factor as version 1, UNVERIFIED, with full source metadata."""
    doc, n = load_seed(), 0
    pub = doc["sources"][0]["publication_year"]
    with transaction(con):
        for f in doc["factors"]:
            cols: dict = {
                "version": 1, "factor_name_en": f"{f['category']} / {f['activity']}",
                "country_code": f["country"], "factor_class": f["classification"],
                "activity_category": f["category"], "activity": f["activity"],
                "activity_unit": f["denominator_unit"],
                "factor_unit": f"kg CO2e/{f['denominator_unit']}",
                "co2e_factor_value": f["value"], "components_json": "[]", "gwp_set_id": None,
                "reference_id": f["reference_id"], "source_organization": _org_for(f["reference_id"]),
                "source_document": _doc_for(f["reference_id"]), "source_url": _url_for(f["reference_id"]),
                "source_locator": f["source_locator"],
                "publication_year": pub if f["reference_id"].startswith("EG-") else 2006,
                "year_from": f["year_from"], "year_to": f["year_to"],
                "geographic_coverage": f["country"], "methodology": f["methodology"],
                "boundary_note": f.get("boundary_note") or "", "verification_status": "unverified",
                "notes": f.get("notes"), "created_at": now_iso(), "gas_type": f["gas"],
                "sector": f.get("sector"), "fuel_type": f.get("fuel_type"),
                "technology": f.get("technology"), "gas": f["gas"],
                "country_scope": f["country_scope"], "quality_level": f.get("quality_level"),
                "uncertainty": f.get("uncertainty"), "data_year": f.get("data_year"),
                "source_page": f.get("source_page"), "source_table": f.get("source_table"),
            }
            cols = {"factor_id": f["factor_id"], **cols}
            names = ", ".join(cols)
            marks = ", ".join("?" for _ in cols)
            cur = con.execute(
                f"INSERT OR IGNORE INTO emission_factors({names}) VALUES ({marks})",
                tuple(cols.values()))
            if cur.rowcount:
                n += 1
                con.execute(
                    "INSERT INTO factor_audit_log(factor_id,version,action,field_name,old_value,new_value,"
                    "changed_at,changed_by,reason,reference_id) VALUES (?,1,'created','co2e_factor_value',"
                    "NULL,?,?,'system-seed','Egypt seed import (source-backed)',?)",
                    (f["factor_id"], f["value"], now_iso(), f["reference_id"]))
    return n


def seed_coverage(con) -> int:
    rows = build_coverage() if not COVERAGE_PATH.exists() else json.loads(
        COVERAGE_PATH.read_text(encoding="utf-8"))
    n = 0
    with transaction(con):
        for r in rows:
            n += con.execute(
                "INSERT OR IGNORE INTO factor_coverage(country_code,year,sector,activity,gas,"
                "coverage_status,available_source,missing_reason,review_date,reviewer) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (r["country_code"], r["year"], r["sector"], r["activity"], r["gas"],
                 r["coverage_status"], r.get("available_source"), r.get("missing_reason"),
                 r.get("review_date"), r.get("reviewer"))).rowcount
    return n


def seed_egypt(con) -> dict:
    return {"sources": seed_sources(con), "factors": seed_factors(con), "coverage": seed_coverage(con)}


def _row(ref: str) -> dict:
    for s in load_seed()["sources"]:
        if s["reference_id"] == ref:
            return s
    return {}


def _org_for(ref): return _row(ref).get("organization_name")
def _doc_for(ref): return _row(ref).get("document_title")
def _url_for(ref): return _row(ref).get("source_url")


def coverage_summary(con, *, country="EG") -> dict:
    rows = con.execute("SELECT year, coverage_status, COUNT(*) n FROM factor_coverage "
                       "WHERE country_code=? GROUP BY year, coverage_status", (country,)).fetchall()
    by_year: dict[int, dict[str, int]] = {}
    for r in rows:
        by_year.setdefault(int(r["year"]), {})[r["coverage_status"]] = int(r["n"])
    return {"years": [{"year": y, "statuses": by_year.get(y, {})} for y in range(YEAR_FROM, YEAR_TO + 1)]}
