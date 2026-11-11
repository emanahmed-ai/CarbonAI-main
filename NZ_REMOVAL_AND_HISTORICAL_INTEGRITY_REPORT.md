# NZ Removal & Historical Integrity Report

**Date:** 2026-11-03 · **Authorisation:** client explicitly approved removal · **Status:** EXECUTED AND VERIFIED

## 1. Backup evidence

| Step | Evidence |
|---|---|
| Pre-migration backup (schema v2→v3) | `backups/carbonai_pre_migration_20261103T045555376245Z.db` — 208,896 bytes, `PRAGMA integrity_check = ok` |
| Dry-run backup | `backups/carbonai_pre_nz_removal_dryrun_20261103T045024767895Z.db` — 37 NZ rows visible, nothing deleted |
| **Pre-removal backup** | `backups/carbonai_pre_nz_removal_20261103T051058598799Z.db` — **397,312 bytes**, `integrity_check = ok`, **37 NZ factor rows present in backup** |

Backups use SQLite's online backup API (consistent copy) and are stored under `backups/`.

## 2. Removal execution

```
python scripts/nz_removal_dry_run.py --execute --confirm REMOVE-LEGACY-NZ
```

Output (actual):
```
NZ factor rows (all versions): 37
NZ source row present: True
Activity records with country_code='NZ': 0 (historical - preserved untouched)
Backup before deletion: ...carbonai_pre_nz_removal_20261103T051058598799Z.db
Deleted factor rows: 37; deleted sources: 1
Remaining NZ factors: 0
```

Deletion scope was exactly:
* `emission_factors` rows with `country_code='NZ'` → 37 deleted
* `sources` row `NZ-MFE-2023-ME1764` → 1 deleted

**Audit record** (`update_log`):
`2026-11-03T05:10:58+00:00 | nz_removal | executed | deleted 37 emission_factors rows and 1 source row; historical records/snapshots untouched (backup: …pre_nz_removal_20261103T051058598799Z.db)`

## 3. Operational de-registration (code level)

| Item | Before | After |
|---|---|---|
| Fresh-install seed (`seed_all()`) | seeded 37 NZ factors + NZ source | seeds **Egyptian** dataset only; NZ only behind `include_legacy_nz=True` (test fixtures) |
| `seed_sources()` | always registered the NZ source row | registers it only when explicitly `include_legacy_nz=True` |
| NZ seed JSON | `database/seed/nz_mfe_2023_factors.json` | moved to `tests/fixtures/` (test-only; not part of production seed) |
| Loader default path | `database/seed/…` | `tests/fixtures/…` (`services/reference_loader.py`) |
| Scripts (`build_nz_seed.py`, `validate_reference_data.py`) | pointed at seed dir | updated to the fixtures path |
| Default country | — | `settings.default_country = 'EG'` (verified in the live DB) |
| Factor selection | — | `/api/factors?country=NZ` returns `[]`; no NZ factor is selectable anywhere |

## 4. Historical integrity verification

| Check | Result |
|---|---|
| Activity records count before/after removal (test) | identical |
| Sum of `kg_co2e` before/after removal (test) | identical |
| Factor snapshot of a historical NZ-based record | still contains `"country": "NZ"` and the original kg (268.0) — untouched |
| Real database records | 1 record preserved, 0 deleted |
| `report_submissions`, invoices, audit logs | untouched (removal touches only the factor library + one source row) |
| Recalculation of history | none — the engine was not modified; snapshots keep the factor used at calculation time |

## 5. Test coverage for this part

`tests/unit/test_api_v4.py::NZRemoval.test_removal_cli_executes_and_preserves_history`
(seeds a legacy DB → inserts a historical NZ-factor record → runs the real CLI → asserts 0 NZ factors,
0 NZ source, identical record count/sum, snapshot intact, audit log present).

## 6. Rollback

```
python scripts\db_admin.py restore "backups\carbonai_pre_nz_removal_20261103T051058598799Z.db"
```
(The current DB is copied aside first; nothing is overwritten blindly.)

## 7. Remaining notes (honest)

* The test fixture `tests/fixtures/nz_mfe_2023_factors.json` remains **for the original 79-test
  suite only**. It is never loaded by production code paths (verified by the seed flag).
* No NZ records existed in the production database, so no historical NZ totals could change;
  the preservation test exercises the snapshot path explicitly.
