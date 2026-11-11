"""Additive schema + migrations. No DROP / DELETE statements anywhere in this module."""
from __future__ import annotations

import sqlite3

from db.connection import backup_file, db_path, now_iso, transaction

SCHEMA_VERSION = 4

DDL = [
"""CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)""",

"""CREATE TABLE IF NOT EXISTS countries (
    country_id INTEGER PRIMARY KEY AUTOINCREMENT,
    country_name_ar TEXT NOT NULL,
    country_name_en TEXT NOT NULL,
    iso2_code TEXT NOT NULL UNIQUE,
    iso3_code TEXT NOT NULL UNIQUE,
    region TEXT,
    is_active INTEGER NOT NULL DEFAULT 1)""",

"""CREATE TABLE IF NOT EXISTS sources (
    reference_id TEXT PRIMARY KEY,
    organization_name TEXT NOT NULL,
    organization_type TEXT,
    country_id INTEGER REFERENCES countries(country_id),
    document_title TEXT NOT NULL,
    document_version TEXT,
    publication_year INTEGER,
    publication_date TEXT,
    source_url TEXT,
    document_url TEXT,
    methodology_description TEXT,
    geographic_scope TEXT,
    license_or_usage_notes TEXT,
    last_checked_at TEXT,
    verification_status TEXT NOT NULL DEFAULT 'unverified')""",

"""CREATE TABLE IF NOT EXISTS activity_categories (
    category_key TEXT PRIMARY KEY,
    name_ar TEXT NOT NULL,
    name_en TEXT NOT NULL,
    unified_classification TEXT,
    industry_sector TEXT,
    fuel_or_material_types TEXT,
    compatible_units TEXT,
    expected_scope TEXT,
    related_subcategories TEXT)""",

"""CREATE TABLE IF NOT EXISTS emission_factors (
    factor_id TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    factor_name_ar TEXT,
    factor_name_en TEXT,
    country_code TEXT NOT NULL,            -- ISO2, 'GLOBAL' or 'REGION:xx'
    factor_class TEXT NOT NULL,            -- official_national|regional|global_default|proxy|user_supplied|test_synthetic
    activity_category TEXT NOT NULL,
    activity TEXT NOT NULL,
    activity_description TEXT,
    industry_sector TEXT,
    gas_type TEXT,                         -- 'CO2e' when value is a published CO2e total
    scope TEXT,                            -- informational default only; real scope comes from classification
    scope_subcategory TEXT,
    activity_unit TEXT NOT NULL,           -- denominator unit
    factor_unit TEXT NOT NULL,             -- e.g. 'kg CO2e/kWh'
    co2e_factor_value TEXT,                -- Decimal as text
    components_json TEXT,                  -- [[gas, value, basis], ...]
    gwp_set_id TEXT,
    reference_id TEXT REFERENCES sources(reference_id),
    source_organization TEXT,
    source_document TEXT,
    source_url TEXT,
    source_locator TEXT,
    publication_year INTEGER,
    year_from INTEGER NOT NULL,
    year_to INTEGER NOT NULL,
    geographic_coverage TEXT,
    technology_or_fuel_type TEXT,
    methodology TEXT,
    boundary_note TEXT,
    data_quality TEXT,
    verification_status TEXT NOT NULL DEFAULT 'unverified',
    last_verified_at TEXT,
    verified_by TEXT,
    license_note TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (factor_id, version))""",

"""CREATE TABLE IF NOT EXISTS factor_audit_log (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    factor_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    action TEXT NOT NULL,
    field_name TEXT,
    old_value TEXT,
    new_value TEXT,
    changed_at TEXT NOT NULL,
    changed_by TEXT,
    reason TEXT,
    reference_id TEXT)""",

"""CREATE TABLE IF NOT EXISTS companies (
    company_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    country_code TEXT,
    industry_sector TEXT,
    boundary_approach TEXT,   -- operational_control|financial_control|equity_share (user-declared)
    boundary_notes TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (name, country_code))""",

"""CREATE TABLE IF NOT EXISTS facilities (
    facility_id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(company_id),
    name TEXT NOT NULL,
    country_code TEXT,
    internal_ref TEXT,
    control_status TEXT,      -- owned_controlled|leased_controlled|leased_not_controlled|not_controlled|unknown
    created_at TEXT NOT NULL,
    UNIQUE (company_id, name))""",

# One row per activity record. Original demo columns are kept verbatim (Arabic names
# live in the compat view/DataFrame layer); factor + result are SNAPSHOTS and are
# never recomputed when the library changes.
"""CREATE TABLE IF NOT EXISTS activity_records (
    record_id INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint TEXT NOT NULL UNIQUE,
    activity_name TEXT NOT NULL,
    description TEXT,
    company_id INTEGER REFERENCES companies(company_id),
    facility_id INTEGER REFERENCES facilities(facility_id),
    country_code TEXT,
    industry_sector TEXT,
    activity_date TEXT,                    -- ISO date or NULL (never invented)
    activity_year INTEGER,
    activity_month INTEGER,
    quantity TEXT NOT NULL,
    unit TEXT NOT NULL,
    fuel_or_material TEXT,
    category_key TEXT,
    scope TEXT,                            -- 'Scope 1'|'Scope 2'|'Scope 3'|NULL (undetermined)
    scope_subcategory TEXT,
    scope3_category INTEGER,
    scope_status TEXT NOT NULL DEFAULT 'needs_review',  -- suggested|confirmed|needs_review|undetermined
    scope_confidence TEXT,
    scope_reason TEXT,
    scope_missing_info TEXT,
    scope_manual_override INTEGER NOT NULL DEFAULT 0,
    scope2_method TEXT,                    -- location|market|NULL
    ownership_control TEXT,
    energy_purchased TEXT,                 -- yes|no|unknown
    value_chain_relation TEXT,
    factor_id TEXT,
    factor_version INTEGER,
    factor_snapshot_json TEXT,
    factor_value TEXT,
    factor_unit TEXT,
    factor_source TEXT,
    factor_source_url TEXT,
    factor_class TEXT,
    factor_verification TEXT,
    factor_selection_reason TEXT,
    kg_co2e TEXT,
    t_co2e TEXT,
    calc_status TEXT NOT NULL,             -- calculated|needs_factor|needs_date|needs_review|rejected_unit
    calc_notes TEXT,
    engine_version TEXT,
    data_verification TEXT NOT NULL DEFAULT 'unverified',
    notes TEXT,
    evidence_ref TEXT,
    origin TEXT,                           -- manual|import:<file>|migrated_session
    imported_batch_id INTEGER,
    created_at TEXT NOT NULL)""",

"""CREATE TABLE IF NOT EXISTS scope_audit_log (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id INTEGER NOT NULL REFERENCES activity_records(record_id),
    old_scope TEXT, new_scope TEXT,
    old_subcategory TEXT, new_subcategory TEXT,
    changed_at TEXT NOT NULL, changed_by TEXT, reason TEXT NOT NULL)""",

"""CREATE TABLE IF NOT EXISTS import_batches (
    batch_id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name TEXT, imported_at TEXT NOT NULL,
    rows_total INTEGER, rows_accepted INTEGER, rows_rejected INTEGER,
    rows_duplicate INTEGER, rows_needs_review INTEGER, notes TEXT)""",

"""CREATE TABLE IF NOT EXISTS import_rejections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER REFERENCES import_batches(batch_id),
    row_number INTEGER, reason TEXT, raw_json TEXT)""",

"""CREATE TABLE IF NOT EXISTS reduction_plans (
    plan_id INTEGER PRIMARY KEY AUTOINCREMENT,
    area TEXT NOT NULL, description TEXT, owner TEXT, target_date TEXT,
    status TEXT NOT NULL DEFAULT 'planned',
    linked_category_key TEXT, assumptions TEXT, created_at TEXT NOT NULL)""",

"""CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)""",

"""CREATE TABLE IF NOT EXISTS update_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, source TEXT,
    outcome TEXT NOT NULL, detail TEXT)""",

"""CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name TEXT,
    email TEXT,
    role TEXT NOT NULL,                    -- admin|head_office|factory_manager|viewer
    company_id INTEGER REFERENCES companies(company_id),
    facility_id INTEGER REFERENCES facilities(facility_id),
    locale TEXT NOT NULL DEFAULT 'ar',
    is_active INTEGER NOT NULL DEFAULT 1,
    must_change_password INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    last_login_at TEXT)""",

# One submission per facility per period while it is active (submitted/approved); a rejected
# submission frees the period for resubmission. Enforced with a partial unique index below.
"""CREATE TABLE IF NOT EXISTS report_submissions (
    submission_id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER REFERENCES companies(company_id),
    facility_id INTEGER NOT NULL REFERENCES facilities(facility_id),
    period_year INTEGER NOT NULL,
    period_month INTEGER,                  -- NULL = full year
    title TEXT,
    status TEXT NOT NULL DEFAULT 'submitted',   -- submitted|approved|rejected
    total_kg_co2e TEXT,
    by_scope_json TEXT,
    monthly_json TEXT,
    records_count INTEGER,
    calculated_count INTEGER,
    needs_review_count INTEGER,
    verified_factor_pct REAL,
    records_json TEXT,                     -- immutable snapshot of the submitted records
    submitted_by TEXT,
    submitted_at TEXT NOT NULL,
    reviewed_by TEXT,
    reviewed_at TEXT,
    review_note TEXT)""",

"""CREATE TABLE IF NOT EXISTS submission_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_id INTEGER NOT NULL REFERENCES report_submissions(submission_id),
    action TEXT NOT NULL,                  -- submitted|approved|rejected|review_note
    at TEXT NOT NULL,
    by TEXT,
    note TEXT)""",

"""CREATE TABLE IF NOT EXISTS invoices (
    invoice_id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER REFERENCES companies(company_id),
    facility_id INTEGER NOT NULL REFERENCES facilities(facility_id),
    invoice_name TEXT NOT NULL,
    invoice_number TEXT,
    supplier TEXT,
    invoice_date TEXT,
    period_year INTEGER,
    period_month INTEGER,
    category_key TEXT,
    quantity TEXT,
    unit TEXT,
    amount TEXT,
    currency TEXT,
    notes TEXT,
    record_id INTEGER REFERENCES activity_records(record_id),
    factor_id TEXT,
    factor_version INTEGER,
    factor_value TEXT,
    factor_source TEXT,
    file_name TEXT,
    file_hash TEXT,
    file_path TEXT,
    file_mime TEXT,
    extraction_status TEXT NOT NULL DEFAULT 'none',   -- none|text_extracted|unavailable|reviewed
    extraction_json TEXT,
    status TEXT NOT NULL DEFAULT 'draft',             -- draft|calculated|needs_review|void
    created_by TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT)""",

"""CREATE TABLE IF NOT EXISTS invoice_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL REFERENCES invoices(invoice_id),
    action TEXT NOT NULL,                  -- created|extracted|calculated|voided|duplicate_blocked
    at TEXT NOT NULL,
    by TEXT,
    note TEXT)""",

"""CREATE TABLE IF NOT EXISTS model_registry (
    model_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    version INTEGER NOT NULL,
    artifact_path TEXT NOT NULL,
    dataset_fingerprint TEXT NOT NULL,
    train_date_from TEXT,
    train_date_to TEXT,
    n_records INTEGER,
    features_json TEXT,
    config_json TEXT,
    metrics_json TEXT,
    status TEXT NOT NULL DEFAULT 'staged',            -- staged|active|archived
    created_at TEXT NOT NULL,
    created_by TEXT,
    approved_by TEXT,
    approved_at TEXT,
    notes TEXT,
    UNIQUE(name, version))""",

"""CREATE TABLE IF NOT EXISTS factor_coverage (
    coverage_id INTEGER PRIMARY KEY AUTOINCREMENT,
    country_code TEXT NOT NULL,
    year INTEGER NOT NULL,
    sector TEXT NOT NULL,
    activity TEXT NOT NULL,
    gas TEXT NOT NULL DEFAULT 'CO2e',
    coverage_status TEXT NOT NULL,                    -- available|provisional|estimated|international_default|pending|unavailable|not_applicable
    available_source TEXT,
    missing_reason TEXT,
    review_date TEXT,
    reviewer TEXT,
    UNIQUE(country_code, year, sector, activity, gas))""",

"""CREATE TABLE IF NOT EXISTS source_documents (
    document_id INTEGER PRIMARY KEY AUTOINCREMENT,
    reference_id TEXT REFERENCES sources(reference_id),
    file_name TEXT,
    file_format TEXT,
    document_url TEXT,
    local_file_path TEXT,
    checksum TEXT,
    extraction_status TEXT DEFAULT 'not_extracted',
    review_status TEXT DEFAULT 'unreviewed',
    created_at TEXT)""",

"""CREATE TABLE IF NOT EXISTS reduction_targets (
    target_id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER REFERENCES companies(company_id),
    facility_id INTEGER REFERENCES facilities(facility_id),
    baseline_year INTEGER NOT NULL,
    baseline_kg_co2e TEXT NOT NULL,
    target_year INTEGER NOT NULL,
    target_kg_co2e TEXT NOT NULL,
    target_reduction_pct REAL,
    note TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(company_id, facility_id, target_year))""",

"CREATE INDEX IF NOT EXISTS ix_factor_lookup ON emission_factors(country_code, activity_category, activity, year_from, year_to)",
"CREATE INDEX IF NOT EXISTS ix_rec_period ON activity_records(activity_year, activity_month)",
"CREATE INDEX IF NOT EXISTS ix_rec_company ON activity_records(company_id, facility_id)",
"CREATE INDEX IF NOT EXISTS ix_rec_facility ON activity_records(facility_id, activity_year, activity_month)",
"CREATE INDEX IF NOT EXISTS ix_users_company ON users(company_id, facility_id)",
"CREATE INDEX IF NOT EXISTS ix_submissions_status ON report_submissions(company_id, facility_id, status, period_year, period_month)",
"CREATE UNIQUE INDEX IF NOT EXISTS ux_submissions_active "
"ON report_submissions(facility_id, period_year, IFNULL(period_month, 0)) "
"WHERE status IN ('submitted', 'approved')",
"CREATE INDEX IF NOT EXISTS ix_invoices_search ON invoices(company_id, facility_id, period_year, period_month)",
"CREATE UNIQUE INDEX IF NOT EXISTS ux_invoice_hash ON invoices(facility_id, file_hash) WHERE file_hash IS NOT NULL",
"CREATE INDEX IF NOT EXISTS ix_invoice_number ON invoices(facility_id, supplier, invoice_number, invoice_date)",
"""CREATE TABLE IF NOT EXISTS reference_library (
    ref_key TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    organization TEXT NOT NULL,
    edition TEXT,
    publication_year INTEGER,
    url TEXT,
    kind TEXT NOT NULL,                 -- standard|methodology|factor_database|gwp|national_inventory
    country_applicability TEXT,         -- GLOBAL | EG | other ISO2
    sectors TEXT,
    methodology_support TEXT,
    chapter_section TEXT,
    access_date TEXT,
    notes TEXT,
    verification_status TEXT NOT NULL DEFAULT 'unverified')""",

"""CREATE TABLE IF NOT EXISTS refrigerants (
    refrigerant_key TEXT PRIMARY KEY,
    designation TEXT NOT NULL,
    chemical_name TEXT,
    formula TEXT,
    family TEXT NOT NULL,               -- HFC | HFC blend | HCFC | HFO | natural
    components_json TEXT,               -- [["R-32", 0.5], ["R-125", 0.5]] mass fractions
    gwp_100_ar4 TEXT,
    gwp_100_ar5 TEXT,
    gwp_100_ar6 TEXT,
    gwp_20_ar5 TEXT,
    gwp_500_ar5 TEXT,
    basis_notes TEXT,
    source_ref TEXT,
    verification_status TEXT NOT NULL DEFAULT 'unverified',
    is_active INTEGER NOT NULL DEFAULT 1)""",

"""CREATE TABLE IF NOT EXISTS cooling_equipment (
    equipment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    facility_id INTEGER NOT NULL REFERENCES facilities(facility_id),
    company_id INTEGER REFERENCES companies(company_id),
    identifier TEXT NOT NULL,
    equipment_type TEXT,
    refrigerant_key TEXT,
    charge_kg TEXT,
    installed_year INTEGER,
    notes TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(facility_id, identifier))""",

"""CREATE TABLE IF NOT EXISTS refrigerant_service_records (
    service_id INTEGER PRIMARY KEY AUTOINCREMENT,
    equipment_id INTEGER NOT NULL REFERENCES cooling_equipment(equipment_id),
    facility_id INTEGER NOT NULL,
    service_date TEXT NOT NULL,
    refrigerant_key TEXT NOT NULL,
    added_kg TEXT, recovered_kg TEXT, leaked_kg TEXT,
    gwp_basis TEXT NOT NULL,
    gwp_value TEXT,
    leaked_calculated_kg TEXT,
    kg_co2e TEXT, t_co2e TEXT,
    record_id INTEGER REFERENCES activity_records(record_id),
    methodology TEXT,
    evidence_ref TEXT,
    notes TEXT,
    created_by TEXT,
    created_at TEXT NOT NULL)""",

"CREATE INDEX IF NOT EXISTS ix_service_facility ON refrigerant_service_records(facility_id, service_date)",
"CREATE INDEX IF NOT EXISTS ix_equipment_facility ON cooling_equipment(facility_id, identifier)",
"CREATE INDEX IF NOT EXISTS ix_refs_kind ON reference_library(kind, country_applicability)",
]

# ---- additive column migrations (applied only when the column is missing) ----
MIGRATIONS: list[tuple[str, str, str]] = [
    ("emission_factors", "sector", "TEXT"),
    ("emission_factors", "fuel_type", "TEXT"),
    ("emission_factors", "technology", "TEXT"),
    ("emission_factors", "gas", "TEXT"),
    ("emission_factors", "country_scope", "TEXT"),
    ("emission_factors", "quality_level", "TEXT"),
    ("emission_factors", "uncertainty", "TEXT"),
    ("emission_factors", "data_year", "INTEGER"),
    ("emission_factors", "source_page", "TEXT"),
    ("emission_factors", "source_table", "TEXT"),
    ("import_batches", "file_hash", "TEXT"),
    ("import_batches", "status", "TEXT NOT NULL DEFAULT 'committed'"),
    ("reduction_plans", "target_scope", "TEXT"),
    ("reduction_plans", "target_facility_id", "INTEGER REFERENCES facilities(facility_id)"),
    ("reduction_plans", "activity", "TEXT"),
    ("reduction_plans", "baseline_kg", "TEXT"),
    ("reduction_plans", "expected_reduction_pct", "REAL"),
    ("reduction_plans", "kpi", "TEXT"),
    ("reduction_plans", "priority", "TEXT"),
    ("reduction_plans", "reference_source", "TEXT"),
    ("reduction_plans", "plan_year", "INTEGER"),
    ("activity_records", "invoice_id", "INTEGER"),
]


def init_db(con: sqlite3.Connection, *, backup: bool = True) -> None:
    """Create/upgrade tables idempotently. Existing rows are never touched.

    Migration strategy (documented, reversible):
    * all tables/columns are additive; no DROP/DELETE ever runs here;
    * `MIGRATIONS` adds a column only when PRAGMA table_info shows it is missing;
    * a version bump triggers an automatic file backup before any change;
    * rollback for a column addition = ignore the column (SQLite keeps the data intact);
      restoring the pre-migration backup file is the documented hard rollback.
    """
    p = db_path()
    existing = p.exists() and p.stat().st_size > 0
    if backup and existing:
        row = None
        try:
            row = con.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()
        except sqlite3.OperationalError:
            pass
        if row is None or int(row["value"]) < SCHEMA_VERSION:
            backup_file(p, label="pre_migration")
    with transaction(con):
        for stmt in DDL:
            con.execute(stmt)
        for table, column, ddl in MIGRATIONS:
            cols = {r["name"] for r in con.execute(f"PRAGMA table_info({table})").fetchall()}
            if column not in cols:
                con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
        con.execute("INSERT OR IGNORE INTO schema_meta VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
        con.execute("UPDATE schema_meta SET value=? WHERE key='schema_version'", (str(SCHEMA_VERSION),))
        con.execute("INSERT OR IGNORE INTO schema_meta VALUES ('created_at', ?)", (now_iso(),))
