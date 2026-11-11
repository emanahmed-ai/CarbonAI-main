# CARBONAI — New Requirements Audit

**Date:** 2026-11-11 · Status of every requirement in the latest brief against the actual code.

Legend: **DONE** (implemented + tested) · **PARTIAL** · **NOT DONE** (with reason).

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 1 | Main actions at top of the main page in order: Company Registration, Activity, Users | **DONE** | Dashboard quick-action bar in that exact order; company/users admin+head-office only, activity for managers; AR/EN keys `actionCompany/actionActivity/actionUsers` |
| 2 | Company Registration validated & connected to backend | **DONE** | Links to the existing Organization form (`/api/org/companies` + facilities); required name enforced server-side; no duplicate form/model |
| 3 | Remove Refrigerants & AC management page | **DONE** | Page, route, nav item, dashboard equipment section and `/api/refrigerants` + `/api/cooling/*` routers removed; tests assert 404 |
| 4 | Keep refrigerant factors/GWP/references | **DONE** | 17 refrigerants, 44 `REF-*` library factors still served by `/api/factors` (admin view) and usable in records; test `test_refrigerant_factors_available_in_emission_factors` |
| 5 | Refrigerant factor fields (gas, chemical id, pure/blend, GWP-100/20/500, unit, year, source, IPCC version, classification, status) | **PARTIAL** | All present except GWP-20/GWP-500 which are explicitly recorded as "not transcribed in this build" rather than invented (`REFRIGERANT_FACTORS_REPORT.md`) |
| 6 | Fuel factors diesel/fuel oil/gasoline with sources and classification | **DONE (international defaults)** / **PARTIAL (Egyptian official)** | IPCC 2006 defaults loaded and labelled `international_default`; no verified Egyptian official fuel factor was available to load, so none was invented (`EGYPT_FUEL_FACTORS_REPORT.md`) |
| 7 | Selection by year: exact → nearest marked → IPCC default → reject row with error | **DONE** | `factor_library.nearest_candidates` + `calculations.calculate(allow_year_mismatch)` + importer/invoice wiring; ESTIMATED warning stored in `calc_notes`; tests in `test_api_v5::NearestYear` and updated `test_db_layer::test_excel_import` |
| 8 | Dashboard error/loading/retry/empty handling | **DONE** | `Dashboard.tsx` error card + retry + axios timeout; empty state; single-month bar chart; KPI block shared |
| 9 | Import: remove visible column-matching UI, keep backend mapper | **DONE** | `column_mapper.py` untouched and used in `analyze`/jobs; UI no longer exposes mapping controls |
| 10 | Import preview: original file, pagination 100/page, Excel sheet tabs | **DONE** | `/api/imports/raw-preview`, sheet selector; tested page 2 returns 100 rows |
| 11 | Import calculation button + progress/total/processed/success/failed/row errors + no blocking | **DONE** | Background job `/api/imports/jobs` (202 in 0.02 s), polling progress, per-row errors; single-transaction commit 19.5× faster (14.26 s → 0.73 s for 2,000 rows) |
| 12 | Duplicate file/record prevention | **DONE** | SHA-256 per batch + import_jobs duplicate-in-flight; ledger fingerprint dedupe; tests |
| 13 | Activity Records correct filters/pagination/traceability | **DONE** | Existing endpoints; factor snapshot + selection reason + calc notes per record |
| 14 | Invoices: no manual factor, auto-select by year | **DONE** | Service + API + UI changed; exact-year national → nearest marked → error; tests |
| 15 | Emission Factors search/filter/country/gas/unit/source; 4 classifications | **DONE** | Admin-only page + `/api/factors/egypt`; classifications enforced |
| 16 | Factor management admin-only (backend + frontend) | **DONE** | All management GET/POST/verify endpoints require admin (403 otherwise, tested); nav hidden; page guard |
| 17 | Verify result detailed comparison | **PARTIAL** | Verify stores reviewer/status/audit; the proposed automatic comparison against "IPCC known ranges" is not implemented (no defensible numeric ranges table was found in the project); the factor's own source and value are shown instead |
| 18 | Studies: data analysis, evidence, confidence, missing data, recommendations, no area-level claims without sub-meters | **PARTIAL** | `/api/plans/insights` produces evidence-based items from calculated data (share, baseline kg, priorities, references, methodology); monthly changes shown; **studies are computed views, not persisted rows**; area-level electricity claims remain explicitly disallowed |
| 19 | Convert recommendation → plan; plan fields (baseline, target %, status, actual results) | **PARTIAL** | Prefill + extended plan fields + measured `/plans/{id}/results`; plan creation is manual from the prefilled form (no one-click persistence of a study object) |
| 20 | Actual performance tracking from measured data | **DONE** | Results endpoint: baseline (stored or previous year) vs actual ledger; status achieved/partial/not achieved; tested |
| 21 | ML: reuse existing model; no fake model | **DONE (honest)** | No shipped PKL; registry + train-on-real-data + forecast lifecycle; 404/INSUFFICIENT_DATA instead of predictions when unavailable (`ML_MODEL_INTEGRATION_REPORT.md`) |
| 22 | Prediction / studies / plans kept separate | **DONE** | Forecast API labelled as estimates; plan results never use predictions; separate endpoints and UI |
| 23 | Multi-tenancy preserved; new endpoints checked | **DONE** | resolve_scope on every new endpoint (backup, reset, jobs, plan results); tests incl. cross-factory |
| 24 | Reports: professional print layout, PDF, plans with target %, actual results | **PARTIAL** | PDF (AR/EN) with charts/plans/targets exists; a dedicated print-designed HTML report page and per-plan actual results inside the PDF are not implemented |
| 25 | Settings: language persistence/RTL | **DONE** | Language selector in Settings + top bar; persisted in localStorage; `document.dir` switches |
| 26 | Backup: factory-level ZIP incl. branches, permissions enforced | **DONE** | `/api/settings/backup.zip` JSON-in-ZIP; tenancy-scoped; tested |
| 27 | Factory reset: password, backup, audit, operational-only, no cross-factory | **DONE** | Verified password, `DELETE` confirmation, automatic DB file backup, `update_log` entry, operational tables only; other factory untouched (tested) |
| 28 | Audit logging for imports/calculations/factor changes/invoices/backup/reset | **PARTIAL** | Existing logs: factor audit, scope audit, invoice audit, submission audit, import batches, plus reset log. Backup creation is not itself logged in `update_log` (file timestamp + path returned to the user) |
| 29 | Performance: background jobs, chunking, indexes, no silent skips | **DONE** | Jobs + single transaction + suggest cache; existing indexes; failures are returned per row |
| 30 | Clean GitHub clone verification | **DONE** | Fresh DB run: empty dashboard 200/0 records, 500-row job import → 500 records, unknown API 404; deployment steps in `DECISIONS.md`/`FINAL_IMPLEMENTATION_REPORT.md` |
| 31 | Tests for all new functionality | **DONE** | 148 tests pass (v5 added 10: jobs, raw preview, nearest-year, admin-only factors, backup, reset, plan results, API 404) |
| 32 | i18n everywhere (no hard-coded UI text) | **PARTIAL** | Dashboard/Import/Settings/Plans/KPI cards fully keyed; some legacy pages still contain a few literal strings (e.g. availability factors labels, status slugs) and the reports use bilingual labels; full extraction remains |
| 33 | Docs (9 files) | **DONE** | this file + `CORE_AUDIT`, `CARBONAI_FULL_SYSTEM_AUDIT`, reports, `DECISIONS`, `FINAL_IMPLEMENTATION_REPORT` |

## Not done — with reasons

1. **Persistent studies**: the analysis engine produces study-style output on request; storing
   studies as rows requires a new table and UX that was out of the approved minimal scope.
2. **Print-designed HTML report**: PDF export already embeds charts and plans; an HTML print page
   is a presentation layer that was not built.
3. **GWP-20/GWP-500**: not transcribed from the assessment tables in this build; left empty
   (never guessed).
4. **Egyptian official fuel factors**: no verified official document was available; IPCC defaults
   are labelled and the nearest-year policy marks estimates.
5. **OCR**: no OCR engine installed; PDF text-layer extraction only.
6. **Automatic factor verification comparison**: no authoritative numeric range table exists in
   the project; fabricating one was explicitly rejected.

---

# Addendum §25 — status after the follow-up round (2026-11-11)

| Item | Previous | Now | Evidence |
|---|---|---|---|
| A. Smart Column Matching UI removed (mapper kept in backend) | DONE | DONE | `ImportPage.tsx` has no mapping UI; `services/column_mapper.py` used by `analyze`/jobs |
| A. "Reorder main actions" ignored | — | Decision kept | Quick-action bar stays (harmless, was already shipped); recorded in `DECISIONS.md` D15 |
| B. Factors page admin-only: sidebar + route guard + API 403 | PARTIAL (nav+API only) | **DONE** | `RequireAdmin` route wrapper in `App.tsx`; page guard; all management endpoints `require("admin")` (403 tested) |
| B. All references per country (country + IPCC, labelled) | NOT DONE | **DONE** | `GET /api/factors/refs-for-country?country=&category=`; UI panel «مراجع الدولة» in the Factors page listing both types with source/year/URL; tested |
| B. Verify detailed result (checked/against/diff/status/failure) | PARTIAL | **DONE** | `FL.verify_comparison` + `GET .../verify-preview` + `POST .../verify` returns full comparison and stores it in the audit reason; statuses: matched / within_range / out_of_range (reviewer range) / differs_from_registered / no_reference_available; **verification without evidence is refused (400)** — tested |
| C. Plans reuse the same KPI component + filters incl. date range | PARTIAL (no date range) | **DONE** | Plans uses shared `KpiCards` + same `/dashboard/summary` endpoint; From/To filters added and passed through |
| C. Monthly reduction indicators (value/%/↑↓) | DONE | DONE | Monthly changes card |
| C. Single month → bar chart in Dashboard AND Plans | PARTIAL (dashboard only) | **DONE** | Dashboard picks bar for 1 point; Plans renders a monthly **bar chart** (always bars) |
| C. Target % computed from measured data when not entered; overall weighted by volume | NOT DONE | **DONE** | `target_reduction_pct_computed` (source `computed_from_measured`) in plan results; `GET /api/plans/results-overview` weighted overall (tested: (1000×50 + 3000×10)/4000 = 20.0%) |
| D. i18n completeness | PARTIAL | **PARTIAL (improved)** | Dashboard/KPI/Import/Settings/Plans/verify-dialog/Records scope labels localized; remaining literal slugs documented below |
| E. Scope 1=100% sanity | DONE (documented) | DONE + test | Mixed-data test proves Scope 1/2/3 shares (85.06/14.28/0.63, Σ=100) and that unscoped records raise `needs_review` without entering scopes |
| E. KPI card meanings documented | DONE | DONE | `CORE_AUDIT.md` §5 + shared component code |
| E. Dashboard/Reports/Plans identical numbers | DONE (same summarize) | DONE + test | `test_dashboard_and_plans_identical_numbers` (dashboard == plans insights == overview actuals) |
| F. DECISIONS updated; rollback steps; no build artifacts edited | DONE | DONE | `DECISIONS.md` D13–D16; `docs/MIGRATIONS_AND_ROLLBACK.md` (no new migration required) |

## Remaining i18n literals (documented, not hidden)

Status value slugs rendered as-is in a few tables (they are database values, e.g. `needs_factor`),
plus legacy pages' minor captions. The verify dialog, KPI cards, dashboard, import, settings and
plans are fully keyed.
