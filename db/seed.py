"""Idempotent seeding. Uses INSERT OR IGNORE only: never overwrites, never deletes."""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from db.connection import now_iso, transaction
from db.reference_data import CATEGORIES, COUNTRIES
from schemas.domain import EmissionFactor
from services.reference_loader import SEED_DIR, load_nz_mfe_2023

NZ_REF_ID = "NZ-MFE-2023-ME1764"


def seed_countries(con) -> int:
    n = 0
    with transaction(con):
        for iso2, iso3, en, ar, region in COUNTRIES:
            n += con.execute(
                "INSERT OR IGNORE INTO countries(country_name_ar,country_name_en,iso2_code,iso3_code,region,is_active)"
                " VALUES (?,?,?,?,?,1)", (ar, en, iso2, iso3, region)).rowcount
    return n


def seed_categories(con) -> int:
    n = 0
    with transaction(con):
        for key, ar, en, uni, sector, fuels, units, hint in CATEGORIES:
            n += con.execute(
                "INSERT OR IGNORE INTO activity_categories(category_key,name_ar,name_en,unified_classification,"
                "industry_sector,fuel_or_material_types,compatible_units,expected_scope) VALUES (?,?,?,?,?,?,?,?)",
                (key, ar, en, uni, sector, fuels, units, hint)).rowcount
    return n


def seed_sources(con, *, include_legacy_nz: bool = False) -> int:
    """Register the listed references. All start 'unverified' with last_checked_at NULL:
    this build had no network, so reachability was never checked.

    The legacy NZ source is only registered for explicit legacy-test seeding; production
    installs never insert it (client-authorised NZ removal, 2026-11-03)."""
    doc = json.loads((SEED_DIR / "reference_sources.json").read_text("utf-8"))
    n = 0
    with transaction(con):
        for i, s in enumerate(doc, 1):
            rid = f"SRC-{i:03d}"
            n += con.execute(
                "INSERT OR IGNORE INTO sources(reference_id,organization_name,document_title,source_url,"
                "geographic_scope,license_or_usage_notes,last_checked_at,verification_status)"
                " VALUES (?,?,?,?,?,?,NULL,'unverified')",
                (rid, s["title"].split(" ")[0], s["title"], s.get("url"), s.get("scope"),
                 "Not reviewed. " + str(s.get("reachability", "")))).rowcount
        if include_legacy_nz:
            nz = json.loads((Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "nz_mfe_2023_factors.json").read_text("utf-8"))["source"]
            n += con.execute(
                "INSERT OR IGNORE INTO sources(reference_id,organization_name,organization_type,document_title,"
                "publication_year,publication_date,source_url,methodology_description,geographic_scope,"
                "license_or_usage_notes,verification_status) VALUES (?,?,?,?,?,?,?,?,?,?,'unverified')",
                (NZ_REF_ID, nz["org"], "government", nz["title"], 2023, nz["published"], nz["direct_url"],
                 "Published national factors; GWP basis: " + nz["gwp_basis"], "NZ", nz["licence_note"])).rowcount
    return n


def insert_factor(con, f: EmissionFactor, *, reference_id: str | None, reason: str,
                  user: str | None = None, extra: dict | None = None) -> bool:
    """Insert one factor version + audit row. Returns False if (factor_id, version) already exists."""
    extra = extra or {}
    cur = con.execute(
        "INSERT OR IGNORE INTO emission_factors(factor_id,version,factor_name_en,country_code,factor_class,"
        "activity_category,activity,activity_description,gas_type,scope,activity_unit,factor_unit,"
        "co2e_factor_value,components_json,gwp_set_id,reference_id,source_organization,source_document,"
        "source_url,source_locator,publication_year,year_from,year_to,geographic_coverage,methodology,"
        "boundary_note,data_quality,verification_status,license_note,notes,created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,NULL,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (f.factor_id, f.version, f"{f.category} / {f.activity}", f.country, f.classification.value,
         f.category, f.activity, f.boundary_note, "CO2e", f.denominator_unit,
         f"{f.numerator_unit}/{f.denominator_unit}",
         None if f.total_co2e is None else str(f.total_co2e),
         json.dumps([[c.gas, str(c.value), c.basis.value] for c in f.components]),
         f.gwp_set_id, reference_id, f.source_org, f.source_title, f.source_url, f.source_locator,
         extra.get("publication_year"), f.year_from, f.year_to, f.country, f.methodology,
         f.boundary_note, extra.get("data_quality"), f.status.value, f.license_note,
         extra.get("notes"), now_iso()))
    if cur.rowcount:
        con.execute(
            "INSERT INTO factor_audit_log(factor_id,version,action,field_name,old_value,new_value,changed_at,"
            "changed_by,reason,reference_id) VALUES (?,?,?,?,NULL,?,?,?,?,?)",
            (f.factor_id, f.version, "created", "co2e_factor_value",
             None if f.total_co2e is None else str(f.total_co2e), now_iso(), user, reason, reference_id))
    return bool(cur.rowcount)


def seed_nz_factors(con) -> int:
    """Load the 37 NZ factors as UNVERIFIED. Existing (factor_id, version) rows are left untouched."""
    n = 0
    with transaction(con):
        for f in load_nz_mfe_2023():  # reviewer=None -> UNVERIFIED
            n += insert_factor(con, f, reference_id=NZ_REF_ID,
                               reason="Initial import from supplied NZ MfE 2023 guide seed",
                               extra={"publication_year": 2023,
                                      "data_quality": "published national factor (not yet reviewed)"})
    return n


def seed_all(con, *, include_legacy_nz: bool = False) -> dict:
    """Fresh installs seed the Egyptian dataset. New Zealand is legacy-only: it is loaded
    solely when a test fixture explicitly asks for it (include_legacy_nz=True) and is never
    part of a production seed. Existing NZ rows are removed by scripts/nz_removal_dry_run.py
    after backup + dry-run + explicit confirmation (see the implementation report)."""
    out = {"countries": seed_countries(con), "categories": seed_categories(con),
           "sources": seed_sources(con, include_legacy_nz=include_legacy_nz)}
    if include_legacy_nz:
        out["nz_factors"] = seed_nz_factors(con)
    else:
        from services.cooling import seed_reference_library, seed_refrigerants
        from services.egypt_seed import seed_egypt
        out["egypt"] = seed_egypt(con)
        out["reference_library"] = seed_reference_library(con)
        out["refrigerants"] = seed_refrigerants(con)
    out["auth"] = seed_auth(con)
    with transaction(con):
        con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES ('default_country','EG')")
    return out


def seed_auth(con) -> dict:
    """Bootstrap the organization + first admin. Idempotent (INSERT OR IGNORE / existence checks).
    The initial admin password comes from CARBONAI_ADMIN_PASSWORD, else 'admin123' with a
    force-change flag; the API logs a prominent warning either way."""
    import os
    from services.security import hash_password

    created = {"company": 0, "admin": 0, "password_source": ""}
    with transaction(con):
        n = con.execute(
            "INSERT OR IGNORE INTO companies(name,country_code,industry_sector,boundary_approach,created_at) "
            "VALUES ('Head Office (الإدارة العامة)','EG','Organization','operational_control',?)",
            (now_iso(),)).rowcount
        created["company"] = n
        n_users = con.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
        if n_users == 0:
            pw = os.environ.get("CARBONAI_ADMIN_PASSWORD", "")
            created["password_source"] = "env" if pw else "default"
            if not pw:
                pw = "admin123"
            con.execute(
                "INSERT INTO users(username,password_hash,full_name,role,locale,is_active,must_change_password,"
                "created_at) VALUES ('admin',?, 'System Administrator','admin','ar','1',?,?)",
                (hash_password(pw), 0 if pw != "admin123" else 1, now_iso()))
            created["admin"] = 1
    return created


def add_country(con, iso2, iso3, name_en, name_ar, region=None) -> bool:
    if not (re.fullmatch(r"[A-Z]{2}", iso2) and re.fullmatch(r"[A-Z]{3}", iso3)):
        raise ValueError("ISO codes must be upper-case alpha-2 / alpha-3")
    with transaction(con):
        return bool(con.execute(
            "INSERT OR IGNORE INTO countries(country_name_ar,country_name_en,iso2_code,iso3_code,region,is_active)"
            " VALUES (?,?,?,?,?,1)", (name_ar, name_en, iso2, iso3, region)).rowcount)
