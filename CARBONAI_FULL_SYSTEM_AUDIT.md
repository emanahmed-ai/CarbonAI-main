# CARBONAI — Full System Audit

**Date:** 2026-11-11 · Basis: source inspection + runtime tests on a fresh database (GitHub-clone
scenario). This audit precedes the changes documented in `FINAL_IMPLEMENTATION_REPORT.md`.

## 1. Architecture (as found)

* **Backend:** FastAPI (`api/`), routers per domain, JWT auth, role guards, tenancy resolver.
* **Core:** Decimal formula engine + unit conversion + factor library + ledger (single aggregation
  path), covered by 79 original tests.
* **Database:** SQLite, additive migrations (v1→v4), automatic pre-migration backup, no
  DROP/DELETE in schema/seed.
* **Frontend:** React + Vite + TS + Tailwind + Recharts, AR/EN with RTL, role-based sidebar.
* **Reports:** CSV/PDF (basic + detailed with charts), annual report.
* **ML:** row-estimate registry (honest no-model state) + forecasting lifecycle
  (dataset fingerprint, chronological evaluation, staged→active, monthly/annual).
* **Deployment:** `START_CARBONAI.bat` (installs deps, builds frontend if missing, starts uvicorn,
  port guard). `.env.example` present.

## 2. Working functionality (verified by tests)

148 automated tests, all passing (see `FINAL_IMPLEMENTATION_REPORT.md` for the breakdown):
calculation engine, units, GWP, scope classifier, ledger snapshots, factor library, imports,
invoices, submissions/approval, consolidation, dashboard, reports, plans, forecasting, tenancy,
Egypt factors, refrigerant factors, admin-only factor management, backup/reset.

## 3. Broken functionality found

| # | Defect | Impact | Fixed |
|---|---|---|---|
| 1 | Dashboard had no API-error handling; spinner forever on any failed request | Friend's clone appeared "stuck with no data" | Yes — error card + retry + timeout |
| 2 | SPA catch-all returned `index.html` (200) for unknown `/api/*` | Clients tried to parse HTML as JSON; misleading failures | Yes — JSON 404 for `/api/*` |
| 3 | Import commit = one transaction per row | Multi-thousand-row files appeared frozen for a very long time | Yes — single transaction + savepoints + suggest cache (19.5× faster measured) |
| 4 | No progress or job API for long imports | User cannot tell whether it is running | Yes — background jobs + progress polling + 15-min client timeout |
| 5 | Invoice factor entry was manual | Could store arbitrary/unsourced factors | Removed; Core selects by year with ESTIMATED marking |
| 6 | Factors page/API reachable by non-admins | Unauthorised factor management surface | Backend 403 + nav hidden + page guard for non-admin |
| 7 | No nearest-year selection policy | Rows failed even when a valid adjacent-year factor existed | Implemented selection layer with explicit ESTIMATED marking |

## 4. Duplicate logic / inconsistencies

* No duplicate formulas found (single `calculation` service; dashboard/reports/plans share
  `ledger.summarize`).
* **Partial duplication found in the frontend:** the KPI markup existed only in the Dashboard.
  Extracted to `components/KpiCards.tsx` and reused by the Reduction Plans page (same numbers and
  filters).
* Reports recalculated nothing; they already reused `summarize`. The detailed report adds charts
  and plan sections but no new formulas.

## 5. Security issues

| Issue | Status |
|---|---|
| Factor management APIs accessible to all authenticated users | Fixed (admin-only; tested 403) |
| Unknown API routes leaked the SPA shell | Fixed (JSON 404) |
| No rate limiting on login? | Already present (5 failures → 30 s lockout) |
| Upload validation | Extension + magic bytes + size (invoices/imports) — already present |
| Cross-factory access | Tenancy enforced in backend; covered by tests including guessed IDs |
| Factory reset | New: password verification + automatic backup + audit log (tested) |

## 6. Performance bottlenecks

* Import per-row transactions (fixed, measured).
* Factor suggestion per row (now cached per combination).
* Dashboard reads full filtered records into pandas; acceptable at current scale, indexed filters.
* No pagination on `/records`? Present (page/page_size) and used by the UI.

## 7. Missing features (as of audit)

* Persistent "study" entities (analysis existed as computed insights only).
* Print-designed HTML report page (PDF export existed).
* Language switch inside Settings (top bar only).
* Factory-level ZIP backup (only full DB backup existed).
* Factory reset (data deletion) did not exist.
* Nearest-year factor selection did not exist.
* Refrigerants management page existed and was later removed on request; factors remain.

## 8. Existing ML status

* `services/ml_model.py` — row-estimate registry; **no shipped PKL**; 404 when absent (by design).
* `scripts/train_emission_model.py` — trains only from real calculated ledger rows (≥40).
* `services/forecast.py` — forecasting lifecycle with dataset fingerprint, chronological split,
  seasonal-naive baseline, staged→admin activation, monthly/annual forecasts, explicit
  INSUFFICIENT_DATA. No model ships until trained on the organisation's own data.
* Unrelated PKLs found earlier outside the repo were inspected and rejected (sales models).

## 9. Recommended / executed sequence

1. Fix loading + API error handling and the SPA 404 contract. ✔
2. Fix import performance + background jobs. ✔
3. Selection policy (exact → nearest → international default → reject row). ✔
4. Remove refrigerants page; keep factors. ✔
5. Invoices: auto factor. ✔
6. Settings: language, backup ZIP, factory reset. ✔
7. Plans: KPI reuse, monthly changes, measured plan results. ✔ (studies remain generated views)
8. Tests + docs. ✔
9. Remaining: persistent studies, print HTML report, OCR, persistent ML model — documented.
