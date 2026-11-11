# CarbonAI — Implementation Report (Round 2: Egypt DB, Invoices, Intelligent Import, Reporting, Forecasting)

**Date:** 2026-11-03 · **Previous round:** `IMPLEMENTATION_REPORT.md` (Streamlit→React migration,
multi-factory workflow, 105 tests). This report covers the requirements-audit round.

## 1. Starting point (verified, not assumed)

All prior claims were re-tested: 79 original core tests green, 105 total tests green, factory
workflow and reports working. The audit (`CARBONAI_REQUIREMENTS_AUDIT.md`) found these genuine
gaps: no per-scope KPIs/period comparison, fixed-template-only import, no invoices module, no
Egyptian factor database, basic PDF (no embedded charts), non-data-driven reduction plans,
no forecasting lifecycle, and no admin-only factor management on the backend.

## 2. Delivered in this round

| Area | Delivered | Evidence |
|---|---|---|
| **Audit** | `CARBONAI_REQUIREMENTS_AUDIT.md` with per-requirement status | file |
| **Dashboard** | 4 KPI cards (total + Scope 1/2/3) with share %, previous-period change (only when a real baseline exists), date-range filter, annual trend chart | `/api/dashboard/summary` `scopes_kpi` + `comparison`; tests |
| **Intelligent import** | `services/column_mapper.py` (normalisation, AR/EN synonyms, fuzzy, data-type evidence), analyze→mapping→preview→commit flow, **factor preview per row**, SHA-256 duplicate-file block, batch hash history | 20 v3 tests; browser check |
| **Invoices & documents** | New page + API: manual entry, validated upload (ext/magic/size), PDF text-layer extraction with reviewable candidates, calculation via the existing engine, search/archive, hash + metadata duplicate prevention, void-with-audit (no deletion) | `services/invoices.py`, `/api/invoices/*`; 5 tests |
| **Egypt factor database** | 13 source-backed factors (1 Egyptian official EEHC + 12 IPCC defaults), four-way classification, 420-row coverage matrix 2006–2026, source traceability, admin-only management, export CSV | `EGYPT_*` reports; 4 tests |
| **NZ legacy removal** | Gated script with backup + dry-run (37 rows identified, **not deleted** pending explicit confirmation) | `scripts/nz_removal_dry_run.py`, backup file |
| **Reports** | Detailed management PDF with embedded vector charts (scope, monthly, facility, annual comparison), annual report, AR/EN, plans+targets inside the PDF | `/api/reports/pdf-detailed`, `/annual`; tests |
| **Reduction plans** | Data-driven insights from actual scoped ledger data, standard-referenced suggestions, baselines, KPI, priority; % requires reference+KPI; targets table; multi-year roadmap chart (actual vs target) | `/api/plans/insights`, `/targets`, `/roadmap`; tests + UI |
| **ML forecasting** | Full lifecycle (dataset fingerprint, chronological split, baseline comparison, staged→active registry, no retrain on predict, monthly/annual, error band) | `ML_FORECASTING_IMPLEMENTATION_REPORT.md`; tests |
| **Security** | Admin-only factor writes enforced in backend (403 for head_office/factory), admin-only training/activation, upload validation, tenant isolation everywhere | tests |

## 3. Files created / modified

**Created**
```
services/column_mapper.py        intelligent header recognition
services/invoices.py             invoice service (upload/extract/calculate/audit)
services/forecast.py             forecasting lifecycle + registry
services/egypt_seed.py           Egypt seed loader + coverage builder
services/reports_detailed.py     detailed PDF with charts
api/routers/invoices.py          invoices API
scripts/build_egypt_seed.py      coverage matrix generator
scripts/nz_removal_dry_run.py    gated legacy removal (dry-run + execute)
database/seed/egypt_factors_2006_2026.json
database/seed/egypt_coverage_2006_2026.json
EGYPT_ANNUAL_COVERAGE_2006_2026.csv
frontend/src/pages/Invoices.tsx
tests/unit/test_api_v3.py        (20 tests)
+ 9 deliverable markdown docs
```

**Modified**
```
db/schema.py          v3 tables (invoices, invoice_audit_log, model_registry, factor_coverage,
                      source_documents, reduction_targets) + additive column migrations
db/seed.py            Egypt is the fresh-install seed; NZ only behind include_legacy_nz (tests)
api/routers/imports.py           analyze / preview-mapped / commit-mapped + hash dedupe + factor preview
api/routers/factors.py           admin-only writes; /egypt, /coverage-matrix, /export.csv
api/routers/reports.py           /pdf-detailed, /annual
api/routers/plans.py             insights, targets, roadmap, extended plan validation
api/routers/dashboard.py         scopes_kpi + previous-period comparison
api/main.py                      invoices router; KeyError no longer masked as 404
api/routers/ml.py                forecast lifecycle endpoints
frontend pages: Dashboard, ImportPage, Reports, Plans, MLPage, Factors, Layout, App, i18n
README.md
```

**Not touched (protecting working code)**
```
services/calculations.py, unit_conversion.py, gwp.py, ledger.py, importer.py, reports.py,
factor_library.py, scope_classifier.py, emission_factors.py, schemas/domain.py,
the original 79 tests (only their seed call was pointed at the legacy-fixture flag)
```

## 4. Database migrations (additive, reversible)

* `SCHEMA_VERSION` 2 → 3; automatic backup before migration of an existing DB.
* New tables: `invoices`, `invoice_audit_log`, `model_registry`, `factor_coverage`,
  `source_documents`, `reduction_targets`.
* Column additions via `PRAGMA table_info` + `ALTER TABLE ADD COLUMN`
  (emission_factors ×10, import_batches ×2, reduction_plans ×11, activity_records ×1).
* No `DROP`/`DELETE` in schema/seed (enforced by the original test).
* Rollback: restore the automatic pre-migration backup
  (`backups/carbonai_pre_migration_*.db`) with `python scripts\db_admin.py restore <file>`;
  column addition rollback = ignore the column (data intact). Details:
  `docs/MIGRATIONS_AND_ROLLBACK.md`.

## 5. Test results

```
python scripts/run_tests.py
Ran 125 tests in 80s  —  OK
  • 79 original engine/DB/report tests (unchanged)
  • 26 prior API tests (auth, tenancy, submissions, ML, reports, imports)
  • 20 new v3 tests (Egypt DB, coverage, admin-only factors, smart import + hash dedupe,
    invoices incl. isolation/duplicates/void/audit, forecast lifecycle, detailed PDFs,
    plan validation, targets/roadmap, dashboard KPIs/comparison)
```

Browser verification on the live server: login → ML forecast chart (14-month actual vs
predicted with band) → invoice form → Egypt factors tab (EEHC 0.3803 kg/kWh, source page shown).
Production build: `tsc -b && vite build` clean.

## 6. What remains open (honest)

1. **Egypt official coverage** is 1 factor + 12 IPCC defaults; BTR1/CRT/NC4 extraction and IEA
   Egypt data (paywalled) were not obtained. Gap list: `EGYPT_MISSING_FACTORS_REPORT.md`.
2. **NZ deletion gated** — run `python scripts\nz_removal_dry_run.py --execute --confirm REMOVE-LEGACY-NZ`
   when authorised (backup is taken automatically).
3. **OCR** not installed → images require manual entry (PDF text layer extraction works).
4. **No production forecast model** until ≥12 months of real data are trained + activated by admin.
5. Market-based Scope 2 evidence workflow, attachments to activity records beyond invoices, and
   PostgreSQL migration remain future work (documented, unchanged from round 1).
