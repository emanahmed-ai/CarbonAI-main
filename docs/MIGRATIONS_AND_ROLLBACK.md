# Database Migrations & Rollback

**Schema versions:** v1 (original) → v2 (users, submissions) → **v3** (invoices, factor coverage,
model registry, reduction targets, extended columns).

## How migrations run

`db/schema.py::init_db()` executes on every startup and is fully idempotent:

1. If the DB exists and `schema_version` < current, an **automatic file backup** is written to
   `backups/carbonai_pre_migration_<UTC timestamp>.db` (SQLite online backup API) **before** any change.
2. `CREATE TABLE IF NOT EXISTS` for every table and index (additive only).
3. For each entry in `MIGRATIONS`, `PRAGMA table_info` is checked; the column is added with
   `ALTER TABLE ... ADD COLUMN` only if missing.
4. `schema_version` is updated.

There is **no DROP and no DELETE** anywhere in `db/schema.py` / `db/seed.py` (enforced by an
automated test).

## v3 additions

**New tables:** `invoices`, `invoice_audit_log`, `model_registry`, `factor_coverage`,
`source_documents`, `reduction_targets`.

**New columns:**

| Table | Columns |
|---|---|
| emission_factors | sector, fuel_type, technology, gas, country_scope, quality_level, uncertainty, data_year, source_page, source_table |
| import_batches | file_hash, status |
| reduction_plans | target_scope, target_facility_id, activity, baseline_kg, expected_reduction_pct, kpi, priority, reference_source, plan_year |
| activity_records | invoice_id |

**New indexes** include the partial unique indexes:
`ux_submissions_active` (one active submission per facility/period) and
`ux_invoice_hash` (one document hash per facility).

## Rollback strategy

| Level | Action |
|---|---|
| **Column addition** | Ignore the column — SQLite keeps existing data untouched; old code readers are unaffected. |
| **Table addition** | Ignore the table; nothing references it except the new features. |
| **Full hard rollback** | `python scripts\db_admin.py restore backups\carbonai_pre_migration_<ts>.db` (the current DB is copied aside first, never overwritten blindly). |
| **Data removal (NZ legacy)** | `scripts/nz_removal_dry_run.py` takes its own backup; restore that file to undo. |

## Verifying a migration before rolling out

```
python scripts\db_admin.py backup                       # manual backup
python -c "from db.connection import connect; from db.schema import init_db; c=connect(); init_db(c)"
python scripts\run_tests.py                             # 125 tests
```

## Deterministic-order rule

Migrations are appended, never edited. A released version's `MIGRATIONS` rows may be extended with
new rows only; changing an existing row would invalidate the `PRAGMA` check for databases already
migrated.
