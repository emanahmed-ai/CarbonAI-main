# CARBONAI — Requirements Audit

**Date:** 2026-11-03 · **Scope:** full verification of every requirement in the master specification
against the actual code and runtime behaviour, before and after this upgrade round.

Status vocabulary: **COMPLETE** · **PARTIAL** · **MISSING** · **NOT VERIFIED**.
Every status below was verified by executing the code/tests, not by trusting previous reports.

| # | Requirement | Implementation (files) | Verified behaviour | Status |
|---|---|---|---|---|
| 1 | FastAPI backend | `api/` (12 routers), `api/main.py` | uvicorn serves API + SPA; 125 tests green | COMPLETE |
| 2 | React frontend | `frontend/` (Vite+TS+Tailwind+Recharts) | production build; browser walkthrough done | COMPLETE |
| 3 | 105 tests passing (prior claim) | `tests/` | was true; now **125** tests pass | COMPLETE |
| 4 | Factory/head-office workflow | `services/submissions.py`, `api/routers/submissions.py` | submit → approve/reject → consolidated; duplicate active submission blocked by partial unique index; approved snapshots immutable | COMPLETE |
| 5 | ML training pipeline + registry (prior claim) | `scripts/train_emission_model.py`, `services/ml_model.py` | row-estimate model trains **from real ledger data only**; no PKL ever shipped; 404 instead of fake predictions | COMPLETE (honest path) |
| 6 | Data import | `services/importer.py` | legacy fixed-template import worked; **exact-header dependency was a real limitation** | PARTIAL → upgraded below |
| 7 | PDF reporting | `services/reports.py` | CSV + basic PDF verified; **no charts inside PDF** | PARTIAL → upgraded below |
| 8 | Reduction plans | `reduction_plans` table, `api/routers/plans.py`, Plans page | CRUD + status worked; **not data-driven, no targets/roadmap** | PARTIAL → upgraded below |
| 9 | Dashboard KPIs (4 cards w/ scope share + previous-period change) | Dashboard page | prior dashboard had total/records/review/verified cards — **no per-scope cards, no period comparison** | MISSING → implemented |
| 10 | Charts: trend, scope comparison, distribution, facility, category, top sources, monthly, annual | Dashboard | all present except annual trend | PARTIAL → annual chart added |
| 11 | Dashboard filters: year, month, date range, facility, scope, sector/category | Dashboard | year/month/facility/scope existed; **date range missing** | PARTIAL → added |
| 12 | Intelligent column recognition (synonyms AR/EN, fuzzy, data-type evidence) | `services/column_mapper.py` (new), `/imports/analyze` | verified: messy Arabic headers mapped at 0.86–1.0 confidence | COMPLETE |
| 13 | Mapping interface with preview + manual correction + factor preview + confirmation | Import page rewrite | analyze → mapping UI → preview (with expected factor per row) → commit | COMPLETE |
| 14 | Duplicate file detection (SHA-256) + import history + audit | `api/routers/imports.py`, `import_batches.file_hash` | 2nd identical upload → 409; force=true override; batch hash stored | COMPLETE |
| 15 | Invoices & Documents page (manual entry, upload, search, archive, calculation, dedupe, audit) | `services/invoices.py`, `api/routers/invoices.py`, Invoices page (new) | create/upload/calculate/search/void/audit verified by tests + browser | COMPLETE |
| 16 | OCR / document extraction | `extract_candidates()` | PDF text layer (pdfplumber) only; **no OCR engine installed** — images honestly marked `unavailable` | PARTIAL (environmental limit, explicitly surfaced) |
| 17 | Invoice duplicate prevention (hash + metadata) | `ux_invoice_hash`, supplier/number/date check | same file → 409; same metadata → 409 with `existing_invoice_id`; forced override possible | COMPLETE |
| 18 | Egyptian emission factors DB 2006–2026 | `database/seed/egypt_factors_2006_2026.json`, `services/egypt_seed.py`, `factor_coverage` | 13 source-backed factors (1 Egyptian official + 12 IPCC defaults); 420-row coverage matrix | PARTIAL (see §Egypt below) |
| 19 | Four-classification model | `country_scope` column | egypt_official / egypt_research / international_egypt_specific / international_default — no merging; tested | COMPLETE |
| 20 | Annual coverage matrix, every year explicit, 2025/2026 independent | coverage CSV + `/factors/coverage-matrix` | 21 years × 20 activities = 420 rows; 2024 has 1 available; 2025/2026 have **0 available, 8 pending + 12 international_default each** | COMPLETE |
| 21 | Source traceability for every approved factor | `source_organization`, `source_document`, `source_locator`, `source_page`, `source_url` | every seeded factor carries source + page; tested | COMPLETE |
| 22 | Egypt default country | `settings.default_country='EG'`, UI defaults | tested | COMPLETE |
| 23 | Remove New Zealand from active system | gated script `scripts/nz_removal_dry_run.py` | dry-run executed: 37 NZ rows + 1 source identified; **deletion NOT executed** — requires `--execute --confirm REMOVE-LEGACY-NZ` (spec §2 requires explicit confirmation) | PARTIAL (gated as mandated) |
| 24 | Original New Zealand factors removed from the live DB | — | **still present in the existing `data/carbonai.db`** until the gated removal is confirmed | PENDING (destructive gate) |
| 25 | Factor management admin-only (backend) | `api/routers/factors.py` | factory_manager/head_office POST → 403; admin → 201; verify admin-only; tested | COMPLETE |
| 26 | Reports: detailed + annual, charts inside PDF, AR/EN | `services/reports_detailed.py`, `/reports/pdf-detailed`, `/reports/annual` | PDFs generated (vector charts); AR path requires arabic-reshaper+bidi (installed) | COMPLETE |
| 27 | Reduction plans: data-driven insights, references, baselines, KPI, targets, roadmap chart | `plans/insights`, `plans/targets`, `plans/roadmap`; Plans page | insights from actual scoped ledger data; % requires reference+KPI (400 otherwise); roadmap actual-vs-target chart | COMPLETE |
| 28 | ML forecasting lifecycle (dataset fingerprint, staged→active, no retrain on predict, chronological eval, baseline comparison, monthly/annual) | `services/forecast.py`, `/ml/*` | insufficient data → explicit INSUFFICIENT_DATA; train→staged→activate→forecast; 2nd train with same data → skipped; seasonal-naive baseline compared; band labelled as empirical | COMPLETE |
| 29 | Monthly/annual forecasting incl. horizon 1/3/6/12, facility + consolidated | `/ml/forecast?horizon`, facility/company scoping | verified with 14-month demo series; consolidated uses company-level totals (no double counting) | COMPLETE |
| 30 | Security: tenant isolation, upload validation, admin-only training | `api/deps.py`, `services/invoices.validate_upload`, ML guards | isolation tests; magic-byte/size/ext checks; train/activate 403 for non-admins | COMPLETE |
| 31 | Historical integrity: no recalculation, snapshots preserved | engine untouched; no UPDATE of `activity_records` results | 79 original tests unchanged; snapshots still stored per record | COMPLETE |
| 32 | Destructive-op protection (backup + dry-run + confirmation) | `scripts/nz_removal_dry_run.py`, `init_db` auto-backup | backup file created before dry-run; hard rollback documented | COMPLETE |

## Honest gaps (not fabricated)

1. **Egyptian official factor coverage is thin by necessity.** Only one figure could be verified
   from the official EEHC 2023/2024 report (380.3 t CO₂/GWh thermal intensity). The IEA Egypt
   dataset is paywalled; UNFCCC BTR1/CRT/NC4 PDFs were not machine-extracted in this build.
   Everything else is either an IPCC international default (Type D, labelled) or Pending.
2. **NZ removal is gated, not executed.** The specification demands explicit confirmation before
   destructive changes; the script is ready and the dry-run + backup are produced.
3. **OCR is unavailable** (no tesseract/pytesseract); PDF text-layer extraction is implemented and
   clearly marked as candidate values requiring human review.
4. **No production forecast model ships.** A model only exists after an admin trains it on ≥12
   consecutive months of real calculated data, then activates it.
5. **2025/2026 have no Available factors** — no official publication was verified for those years;
   the matrix records this explicitly instead of copying 2024 data forward.

## Verification evidence

```
python scripts/run_tests.py  →  Ran 125 tests ... OK
python scripts/build_egypt_seed.py → 13 factors, 420 coverage rows
python scripts/nz_removal_dry_run.py → dry run only + backup
browser walkthrough: login → dashboard → ML forecast chart → invoices form → Egypt factors tab
```
