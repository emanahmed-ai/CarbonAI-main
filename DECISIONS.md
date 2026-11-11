# DECISIONS

**Date:** 2026-11-11 · Decisions made while implementing the latest brief, with alternatives and
reasons. Nothing here overrides the approved product decisions in the brief.

## D1 — Import jobs run in-process (thread + registry), not an external queue

* **Chosen:** `services/jobs.py` runs one daemon thread per import with an in-memory registry and
  polling endpoint.
* **Alternatives:** Celery/RQ/Redis (new infrastructure, deployment burden for a single-server
  app); synchronous request (the original cause of apparent hangs).
* **Why:** zero new dependencies, works in the documented single-worker deployment, immediate
  202 response, progress + timeout, duplicate-in-flight prevention. **Limitation:** jobs are lost on
  server restart and not shared across multiple uvicorn workers — documented; the app runs one
  worker and the batch table/hash still prevents double imports.

## D2 — One transaction with per-row SAVEPOINTs for imports

* **Chosen:** the whole batch commits once; each row runs in a savepoint.
* **Alternatives:** keep per-row transactions (≈20× slower on HDD/AV machines); bulk
  `INSERT` bypassing `ledger.add_record` (would duplicate the Core; forbidden).
* **Why:** measured 2,000 rows: 14.26 s → 0.73 s; row-level failures still isolate; every row
  still goes through the single calculation path and stores snapshots/traceability.

## D3 — Factor selection: exact → nearest marked → international default → reject row

* **Chosen:** `nearest_candidates` may return only **same-country** factors or **international
  defaults** (GLOBAL/regional). Cross-country national factors remain explicit proxy choices.
  The engine gains `allow_year_mismatch` (default **false**, so all existing strict behaviour and
  tests remain) and writes an `ESTIMATED` warning when the selection layer enables it.
* **Alternatives:** silently use any factor (rejected: mislabels data); change the formula/validity
  model globally (rejected: breaks historical semantics and the tested engine).
* **Why:** satisfies the approved policy while preserving the engine and traceability.

## D4 — Remove the refrigerant management page/API, keep the science

* **Chosen:** deleted `frontend/src/pages/Refrigerants.tsx`, its route/nav, `api/routers/cooling.py`;
  kept `services/cooling.py` **only** for seeding refrigerants/GWP factors and the reference
  library. Tables remain (no destructive migration; historical data preserved).
* **Why:** requested removal; the requirement explicitly forbids removing refrigerant factors,
  GWP values, references and historical records. The dashboard refrigerant KPI remains because the
  latest brief lists refrigerant-related emissions among dashboard KPIs (it reads ledger records,
  not the removed page).

## D5 — Emission-factor management is admin-only at the API level

* **Chosen:** all factor listing/coverage/source/verify/write endpoints require `admin`; the
  calculator still uses `/api/factors/suggest`, which stays available to all authenticated roles.
* **Why:** the brief requires backend enforcement (hidden menus are not security). Factory users
  only need suggestions for calculations.

## D6 — Manual factor entry removed from invoices, kept for activity records

* **Chosen:** invoice API/UI no longer accept a manual factor; the invoice factor comes from the
  library by category/year/unit (exact → nearest marked → clear error). Direct activity entry
  keeps the existing, documented user-supplied factor feature (unverified, source required).
* **Why:** the brief scopes the removal to invoice processing; user-supplied activity factors are
  an existing, audited capability used when no library factor exists.

## D7 — Studies are computed views, not persisted entities (this round)

* **Chosen:** `/api/plans/insights` produces evidence-based studies/recommendations on request;
  the UI prefills a plan from a recommendation. No `studies` table was added.
* **Alternatives:** new tables + lifecycle (larger scope, risk of half-built UX).
* **Why:** delivers the evidence and conversion workflow now without inventing approvals/versions;
  the limitation is documented in `CARBONAI_NEW_REQUIREMENTS_AUDIT.md`.

## D8 — Factory reset scope and safety

* **Chosen:** deletes operational rows of the selected facility (records + scope audit, invoices +
  audit, service records + equipment, submissions + audit, plans, targets) after verifying the
  current password, requiring typed `DELETE`, taking an automatic DB backup and writing
  `update_log`. Users, factories, factors, references, settings and **import batch history**
  are preserved.
* **Why:** import batches are audit evidence; deleting them would hide what happened. Backup before
  destruction and password re-entry are mandatory per the brief.

## D9 — Factory backup format

* **Chosen:** ZIP with `data.json` (format `carbonai.factory-backup/1`) plus the original invoice
  attachments found on disk; global entities (users, factors, references) excluded; tenancy
  enforced (head office pinned to its company).
* **Why:** portable, inspectable, no DB internals; matches "factory-level operational data".

## D10 — Unknown `/api/*` routes return JSON 404, never the SPA shell

* **Why:** the old catch-all returned HTML with HTTP 200 for missing endpoints, which produced
  misleading "stuck loading" symptoms when clients tried to parse HTML as JSON.

## D11 — i18n approach

* **Chosen:** dictionary-driven keys; dashboard/import/settings/plans/KPI cards fully keyed;
  Arabic default with RTL and persisted language.
* **Honest state:** a few legacy labels/status slugs remain literal English (e.g. raw status
  values); full extraction of every string in every legacy page is incomplete and listed as a gap.

## D12 — Optimistic updates / refetch

* **Chosen:** after mutations the affected lists refetch from the server (single source of truth);
  no client-side recomputation of emissions. **Why:** prevents frontend/backend divergence.

## D13 — Verify requires evidence, with reviewer-supplied ranges

* **Chosen:** `verify-preview` compares the factor against REGISTERED global-default references of
  the same category+activity+unit in our own library (which carry exact IPCC sources). Statuses:
  `matched` / `within_range` / `out_of_range` (only when the reviewer supplies min/max — no
  invented IPCC tolerance) / `differs_from_registered` / `no_reference_available`. Marking
  `verified` is refused (400) unless the comparison is `matched` or `within_range`.
* **Alternatives:** auto-accept with ±10% tolerance (rejected — an invented range); allow verify
  with reason only (rejected — "verified without evidence").
* REF-* (GWP) factors have no independent reference of the same basis → they require a reviewer
  range or remain unverified; documented.

## D14 — References-per-country listing

* **Chosen:** `refs-for-country` returns DISTINCT registered sources referenced by the country's
  factors (type `country_specific`) plus sources referenced by GLOBAL defaults relevant to the
  category filter (type `ipcc_default`).
* **Why:** "all references for the country" must include IPCC defaults without mislabelling them
  as Egyptian; filtering by category keeps the list relevant.

## D15 — Main-page quick actions kept although "reorder" was withdrawn

* The bar was shipped in the previous round and is harmless; removing it would be an unrelated
  refactor. The requirement itself is ignored (no re-ordering logic was added).

## D16 — Weighted overall plan reduction

* **Chosen:** overall measured % = Σ(baseline−actual)/Σ(baseline) over plans with a measurable
  baseline; per-plan effective target = user target else computed-from-measured (labelled);
  overall target = Σ(baseline×target%)/Σ(baseline).
* **Why:** matches "weighted by emission volume" and never uses predictions.
