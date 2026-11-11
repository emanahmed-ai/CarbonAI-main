# CarbonAI — Implementation Report

**Date:** 2026-10-31 · **Scope:** full audit + upgrade of the existing CarbonAI v0.2 project
(Streamlit app → production web system: React frontend, FastAPI backend, multi-factory
workflow, ML integration path).

---

## 1. What the original project contained

The project was a Python package with a genuinely strong, tested core and a Streamlit UI
(`app.py`, 1,316 lines) on top:

| Component | State |
|---|---|
| `schemas/domain.py` | Pure-Python domain objects; **Decimal everywhere, floats rejected by design** |
| `services/calculations.py` | Deterministic engine: `Emissions = quantity(in factor unit) × factor`; per-gas components + GWP; proxy/verification guards; never recomputes history |
| `services/unit_conversion.py` | Dimension-checked conversion; mass↔volume↔energy only with a documented property; distinct pkm/tkm/vehicle-km dimensions |
| `services/gwp.py` | AR4/AR5 GWP-100 sets sourced from NZ MfE 2023 Table 1 |
| `services/factor_library.py` | DB-backed factor library: ranked candidates (national > regional > global > proxy), every exclusion carries a reason, versioned writes + audit log, reviewer-name-required verification |
| `services/scope_classifier.py` | Rule-based GHG Protocol Scope 1/2/3 decision aid that returns "needs review" + missing facts instead of guessing |
| `services/ledger.py` | Record persistence with factor+result **snapshots**, fingerprint dedup, no-invented-dates rule, single aggregation path (`summarize`) for dashboard/reports |
| `services/importer.py` | CSV/Excel preview→commit import (Arabic + English column aliases), rejected rows with reasons |
| `services/reports.py` | CSV + PDF (Arabic via arabic-reshaper/bidi) |
| `db/` | SQLite with **additive-only** schema (no DROP/DELETE; a test enforces it), automatic pre-migration backup, idempotent seeding (42 countries, 14 activity categories, 18 sources, 37 NZ factors) |
| `tests/` | 79 unit tests, all passing |
| `docs/` | Honest known-limitations file (the app had *never been rendered in a browser*) |

Environment finding: the machine's Python 3.14 had pandas 3.0 / FastAPI / uvicorn /
python-jose / scikit-learn installed but **not** reportlab/openpyxl/streamlit — the
Streamlit app could not even start there. I installed the missing reporting packages and
verified the 79 tests green before changing anything.

## 2. Problems discovered

1. **No working UI in practice** — Streamlit was never installable/run in this environment;
   the "quick entry" lived in session state, disconnected from the DB.
2. **No authentication or multi-tenancy** — reviewer name was free text; anyone could see
   and edit everything; `docs/known_limitations.md` listed auth/RLS as "not built".
3. **No head-office workflow** — companies/facilities tables existed but there was no
   submission/approval flow, no consolidation, no per-factory isolation.
4. **No REST API** — the business logic was only reachable through Streamlit.
5. **No ML model at all** — despite the upgrade request referencing "the existing PKL
   model": a full search of the project and of `Downloads\` found **no ML artifact inside
   CarbonAI**. The PKLs in `Downloads\` (`catboost_sales_model.pkl`, `models\dt_model.pkl`,
   …) belong to unrelated sales/classification exercises (features like `lag_1`,
   `rolling_mean_7`, `dayofweek_sin`); one cannot even be unpickled without `catboost`.
   Nothing in the code references pickle/sklearn/joblib.
6. **Two real bugs found during testing** (both fixed, see §5).
7. Technical debt: `docs/DB_SCHEMA.md` describes a PostgreSQL target that never landed
   (left as-is; SQLite is kept deliberately).

## 3. What was implemented

### 3.1 Backend REST API (`api/`, new — FastAPI)

The existing services are wrapped, **not rewritten**: every endpoint delegates to
`services/*`, so the tested engine is the only calculation path.

* `api/main.py` — app assembly, startup (`init_db` + `seed_all` idempotently), exception
  mapping (ValueError→400, LookupError→404, PermissionError→403, IntegrityError→409),
  CORS for the dev frontend, SPA serving of `frontend/dist`.
* `api/security.py` — JWT (HS256, python-jose); the signing secret is taken from
  `CARBONAI_JWT_SECRET` or generated once and persisted in `settings`.
* `api/deps.py` — per-request SQLite connection, `current_user`, role guards, and the
  **tenancy resolver** (see §4).
* Routers: `auth` (login/session/change-password, brute-force slowdown), `users`,
  `org` (companies/facilities), `records` (create via engine, filters+search+sort+
  pagination, scope override, scope preview), `factors` (search/suggest/coverage/sources/
  add/verify/audit), `dashboard` (summary + comparison), `reports` (CSV/monthly-CSV/PDF),
  `imports` (preview/commit/template/batches), `submissions`, `ml`, `settings` (+backup,
  db-info), `plans` (reduction plans).

### 3.2 Security & users (new)

* `services/security.py` — PBKDF2-HMAC-SHA256, 390k iterations, per-user salt, constant-time
  compare (stdlib only).
* `db/auth_store.py` — user CRUD (deactivation instead of deletion), `authenticate`.
* `db/seed.py::seed_auth` — first run creates the Head-Office organization and the default
  admin (`admin` / `admin123` from `CARBONAI_ADMIN_PASSWORD` else default) with a
  force-change flag; the console prints a prominent warning.

### 3.3 Multi-branch / multi-factory workflow (new, Phase 3 of the brief)

* **Schema additions (additive only, `SCHEMA_VERSION = 2`, automatic pre-migration backup):**
  `users`, `report_submissions`, `submission_audit_log`, plus indexes including the partial
  unique index `ux_submissions_active (facility, year, month) WHERE status IN
  ('submitted','approved')` — the database itself prevents duplicate active submissions.
* **`services/submissions.py`** — `create_submission` snapshots the facility's ledger for a
  period (record fingerprints + amounts + scope/monthly breakdown); `review_submission`
  (approve/reject, rejection requires a note); `consolidated` aggregates **approved
  snapshots only**. An approved snapshot is immutable: later activity never changes an
  approved number (verified by test).
* **Tenancy rules** (enforced server-side in `api/deps.resolve_scope`):
  * `factory_manager`/`viewer` — pinned to their facility; foreign facility_id → **403**;
    records/imports/submissions are always attributed to their own facility.
  * `head_office` — pinned to their company; sees every facility inside it; reviews
    submissions; cannot create admins or touch other companies.
  * `admin` — unrestricted.
* Head office can view each factory separately (dashboard facility filter, comparison
  chart) and consolidated emissions (dedicated page + endpoint).

### 3.4 React frontend (`frontend/`, new)

Vite + React 18 + TypeScript + Tailwind + Recharts + Axios + React Router. Build output
(`frontend/dist`) is served by the API in production; dev mode proxies `/api`.

* **Arabic/English with full RTL**: dictionary-driven i18n, `document.dir` switching,
  language toggle in the top bar; Arabic is the default.
* **Role-based sidebar** (Operations / Analysis / Administration) — factory users see a
  "facility scope" badge, head-office users see "full view".
* Pages: Login (+ forced password change), Dashboard (stat cards, monthly trend, scope
  donut, facility comparison, category bars, top sources, year/month/facility filters),
  New Activity (live **scope-suggestion preview** + ranked factor suggestion with
  proxy-confirmation flow + manual-factor option + calculation result card), Records
  (searchable/sortable/paginated table, filters, detail modal, scope override), Factor
  Library (factors/coverage/sources/add/verify/audit tabs), Import (preview→commit with
  rejected/warnings lists, template download, batch history), Reports (CSV/PDF-EN/PDF-AR
  downloads), Submissions (factory submit + HQ review queue with approve/reject modals +
  record-level detail), Consolidated (approved-only org report), Organization (companies +
  facilities), Users, Reduction Plans, ML Insights (status/predict/train), Settings
  (display options, password change, backup, DB stats).

### 3.5 ML integration (Phase 4 — honest path)

* **Finding:** no PKL existed in the project (see §2.5). Nothing was faked.
* `services/ml_model.py` — versioned bundle registry (`models/emission_model.pkl`,
  format `carbonai.ml/1`): status is always truthful (`loaded: false` + reason when
  absent), `predict` **404s instead of inventing numbers** when no model is loaded, and
  predictions are labelled planning-estimates that never enter the ledger.
* `scripts/train_emission_model.py` + `POST /api/ml/train` — trains a
  GradientBoostingRegressor on the organisation's **own calculated ledger records**
  (≥40 required; refuses otherwise), reports MAE/R², saves the bundle + meta JSON.
  Verified end-to-end: trained on 60 real-path records (R² = 0.88 on the holdout),
  registry + prediction served correctly; the fixture-trained artifact was then deleted so
  the project ships without a model.

### 3.6 Startup & docs

* `START_CARBONAI.bat` — locates Python, installs backend deps on first run, builds the
  frontend if `dist` is missing, warns about the default admin password, checks the port
  is free, starts uvicorn on `127.0.0.1:8000` and opens the browser. Verified by execution.
* `README.md` rewritten for the new architecture. This report. `docs/known_limitations.md`
  kept for historical honesty (its "not built" list is now largely implemented).

## 4. Design decisions worth knowing

1. **Preserve, don't rewrite.** Zero changes to the calculation formulas, unit rules, GWP
   handling, factor ranking, dedup fingerprints or the no-invented-dates policy. All 79
   original tests still pass unmodified.
2. **One source of truth for numbers.** Dashboard, reports and submissions all go through
   `ledger.fetch_records` + `ledger.summarize`; a submission is a *snapshot* of that path,
   so consolidation can never drift from the ledger rules (calculated rows only;
   needs-factor/date/review rows are listed, never counted as zero).
3. **Additive schema culture respected.** New tables only; no DROP/DELETE anywhere new;
   version bump triggers the pre-migration backup automatically.
4. **SQLite kept.** `docs/DB_SCHEMA.md`'s PostgreSQL ambition remains future work; the
   API isolates persistence behind `db.connection`, so the migration path stays open.
5. **English reasons preserved verbatim** from the engine (warnings/steps) — they are part
   of the audit trail; the UI adds Arabic labels around them.

## 5. Bugs found and fixed during validation

1. **Threading bug (critical, production-only):** `sqlite3` connections are created in
   FastAPI's dependency thread and used in the endpoint's worker thread →
   `sqlite3.ProgrammingError: SQLite objects created in a thread can only be used in that
   same thread`, surfacing as intermittent 500/401 under real uvicorn (invisible under
   TestClient). **Fix:** `check_same_thread=False` in `db/connection.py` — safe here
   because each request owns its connection and endpoints run sequentially per request.
   Verified with 60 sequential + 60 concurrent (10-thread) requests: 100% success.
2. **Submission INSERT placeholder mismatch** (`15 values for 16 columns`) — caught by the
   smoke test, fixed.
3. **Missing `rows_list` import** in the records router (`/api/records/meta` 500) — caught
   by the browser walkthrough, fixed.
4. **Factory users silently re-scoped** their own facility when POSTing a foreign
   facility_id — changed to explicit 403.
5. **Admin/head-office UX default:** creating a facility or head-office user without an
   explicit company now inherits the single seeded organization instead of failing.
6. Batch-script port-occupancy guard added after a stale test server caused
   `errno 10048` during bat validation.

## 6. Tests performed

| Suite | Result |
|---|---|
| Original 79 tests (engine, units, GWP, scope, ledger, importer, reports, schema) | **79/79 pass** (unmodified) |
| New API tests (`tests/unit/test_api.py`) — auth, weak-password rejection, RBAC, **factory isolation (records, direct-id access, foreign submissions)**, viewer read-only, head-office company scoping, engine-parity of API-created records, duplicate 409 + allow-duplicate, scope override (reason required, audited), listing filters/pagination, full submit→approve→consolidate, duplicate-submission 409, reject-needs-note, reject→resubmit, supersede, approved-snapshot immutability, ML status/predict-404/train-refusal, CSV/PDF, import preview/commit with tenancy override, factor suggest (unverified-by-design), settings roundtrip | **26/26 pass** |
| Production server (real uvicorn, not TestClient): health, SPA serving, SPA fallback, login/401, authenticated record create, dashboard, CSV/PDF | pass |
| Stress: 60 sequential + 60 concurrent requests (10 threads, mixed read/write) | **0 failures** after the threading fix |
| Frontend production build (`tsc -b && vite build`) | clean |
| Browser walkthrough (in-app browser, real server): Arabic RTL login → dashboard with live charts → records table → new-activity form with live scope classifier (unknown→needs review; owned+purchase→"Scope 2, high confidence") → submissions review queue → approve with note → status flips to "معتمد" | pass |
| `START_CARBONAI.bat` executed for real | pass (after port guard) |

**Total: 105 automated tests, all green.**

## 7. What remains open (honest list)

* **Factor coverage** — still only 37 NZ factors (unverified by design). Egypt/Saudi/UAE
  data requires the librarian workflow (add → verify with named reviewer + source). This
  is data acquisition, not code.
* **PostgreSQL/Alembic** migration described in `docs/DB_SCHEMA.md` — intentionally
  deferred; the current SQLite layer is wrapped behind `db.connection`.
* **Attachments/OCR** (the old invoices page was a session-only placeholder) — not built;
  the record-level `evidence_ref` field remains the hook.
* **ML model quality** — the trainer is a sensible baseline; feature engineering (weather,
  production volumes) and drift monitoring are future work. No model ships until the
  organisation trains one on its own data.
* **Scope 2 market-based evidence workflow** — needs supplier/contract-specific factors
  (as before; the UI communicates the requirement).
* Refresh-token/session-revocation UX (JWT is 12 h; deactivation takes effect on next
  request since the user row is re-read per request, but tokens aren't blacklisted).

## 8. File map of what changed / was added

```
Changed:  db/schema.py (v2: users, report_submissions, submission_audit_log, indexes)
          db/seed.py (+seed_auth), db/connection.py (threading fix)
          README.md
Added:    api/ (12 modules), services/{security,submissions,ml_model}.py,
          db/auth_store.py, scripts/train_emission_model.py,
          frontend/ (React app, ~25 source files, production build in frontend/dist),
          tests/unit/test_api.py (26 tests), START_CARBONAI.bat, IMPLEMENTATION_REPORT.md
Untouched: services/{calculations,unit_conversion,gwp,factor_library,scope_classifier,
           emission_factors,ledger,importer,reports,reference_loader,library_update}.py,
           schemas/domain.py, database/seed/*, docs/, scripts/{db_admin,run_tests,
           validate_reference_data}.py, original 79 tests
```
