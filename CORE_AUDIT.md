# CORE AUDIT — CarbonAI calculation path

**Date:** 2026-11-11 · Scope: upload → column mapping → factor selection → calculation → storage →
dashboard / reports / plans. This audit was produced from the actual code and runtime measurements.

## 1. Where is the calculation logic?

| Layer | File | Role |
|---|---|---|
| Formula engine | `services/calculations.py` | Decimal formula: quantity × factor; per-gas + GWP; year/proxy/verification guards |
| Unit conversion | `services/unit_conversion.py` | Dimension-checked conversion (single location) |
| Factor selection | `services/factor_library.py` (+ `suggest`, `nearest_candidates`) | Ranking, exclusion reasons, exact/nearest year policy |
| Orchestration | `services/ledger.py` → `add_record` / `_calc` / `summarize` | Snapshot per record, scope classification, aggregation |
| Import | `services/importer.py` | Preview + commit; calls `ledger.add_record` only |
| Invoices | `services/invoices.py` | Auto factor selection, then `ledger.add_record` |
| Dashboard | `api/routers/dashboard.py` | `ledger.fetch_records` + `summarize` only |
| Reports | `services/reports.py`, `reports_detailed.py` | Same `summarize` path |
| Plans/studies | `api/routers/plans.py` | Same `fetch_records`/`summarize` |

**Finding:** no duplicated formula exists in routers or the frontend. All numbers flow through
`ledger.summarize`. (Verified again by grep + tests.)

## 2. Root cause of the infinite loading on a fresh machine

Three compounding defects, all fixed:

1. **The dashboard had no error handling.** `api.get('/dashboard/summary').then(setS)` with no
   `.catch`; any failed request left `s === null` and the UI rendered `<Spinner/>` forever.
   Requests could fail for ordinary reasons on a fresh clone (server restart, token expiry, a
   500 from any cause). **Fix:** explicit `error` state, retry button, axios timeout (60 s), and
   a "failed to load" card instead of an endless spinner.
2. **The SPA catch-all answered unknown `/api/*` GET routes with `index.html` and HTTP 200.**
   A missing/renamed endpoint or a proxy pointing at the wrong server returned HTML that the
   client tried to parse as JSON, producing confusing failures. **Fix:** `/api/*` unknown paths
   now return JSON 404 (tested in `test_api_v5.py::test_unknown_api_path_is_json_404`).
3. **Import commit wrote one SQLite transaction per row.** On a slower disk this multiplies
   fsync latency by the row count; a few thousand rows can look frozen for tens of minutes with
   no progress UI. **Fix:** one outer transaction + per-row SAVEPOINT + factor-suggestion cache,
   plus a background job with progress polling.

Measured on the same machine, 2,000-row file:

| Path | Before | After |
|---|---|---|
| Commit 2,000 rows | **14.26 s** | **0.73 s** (≈19.5×) |
| UI feedback | none until response | job accepted in 0.02 s, progress %, elapsed time |
| Failure mode | endless spinner | explicit error + retry + timeout message |

## 3. Silent assumptions found and removed

| Assumption | Status |
|---|---|
| Factor must match the reporting year exactly | Changed to the approved policy: exact → nearest year marked **ESTIMATED** → international default marked → row rejected with a clear error. The engine's formula is unchanged; a new `allow_year_mismatch` flag is set only by the selection layer and writes an ESTIMATED warning into `calc_notes`. |
| An unverified national factor is a dead end | Invoices/imports now auto-select a unique exact-year national factor and flag its verification status; nothing is presented as verified. |
| Manual factor entry in invoices | Removed (UI and API); invoices use the Core selection by activity/year/unit. |
| Unknown API path returns the app shell | Removed (JSON 404). |
| Rows with no factor produce a number | Unchanged: they stay `needs_factor`, are counted separately and never treated as zero. |

## 4. Scope classification check (dashboard "Scope 1 = 100%")

Verified: this was **correct behaviour for that dataset**, not a bug. The demo/Baseline records
were fuel combustion with `ownership_control = owned_controlled` (Scope 1) and no electricity
records. With the current seed and the tests, electricity records map to Scope 2 and refrigerant
records to Scope 1 (see `test_api_v4::test_scope_separation`). A record whose control facts are
missing stays scope-unverified and is counted in "needs review" - never silently bucketed.

## 5. Meaning of the review KPIs

* **"Records requiring review" / `needs_review`** = records whose `calc_status != 'calculated'`
  (needs factor/date/review/rejected unit) plus calculated records whose scope status is neither
  `confirmed` nor `suggested`. Computed from the actual filtered dataset in `ledger.summarize`.
* **"Verified share"** = calculated records whose factor status is `verified`, divided by all
  records in the filter (`verified_pct_definition` is returned by the API). Not a client
  invention.

## 6. Performance / consistency notes

* Dashboard and reports share `fetch_records` → identical numbers by construction.
* Indexes added earlier (`ix_rec_facility`, `ix_rec_period`, `ix_rec_company`) cover the dashboard
  filters; imports write in a single transaction; suggestions are cached per
  (country, category, year, unit, fuel).
* Aggregation loads the filtered rows into pandas (per period). For very large datasets a SQL
  aggregate would be the next step; current scale (tens of thousands of rows) is acceptable and
  measured (500-row export + dashboard under 1 s).

## 7. Remaining weaknesses (documented, not hidden)

* `services/column_mapper.py` still does the mapping automatically on the server; the UI no longer
  exposes it (per approved design). When a required column cannot be matched the job fails with
  the explicit list of missing fields instead of guessing.
* OCR for image invoices is still unavailable (no tesseract); PDF text extraction remains.
* The studies module is generated from live data via `/api/plans/insights` and plan results come
  from measured ledger values; studies are not yet persisted as separate database rows.
