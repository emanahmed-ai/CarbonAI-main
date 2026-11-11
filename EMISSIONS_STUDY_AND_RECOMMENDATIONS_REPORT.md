# Emissions Study & Recommendations Report

**Date:** 2026-11-11 · Implementation status of the studies/analysis capability.

## 1. What exists (implemented and tested)

`GET /api/plans/insights` (scoped by tenant) computes, from **calculated ledger records only**:

* total emissions and share by scope, with the highest scope identified;
* top facilities, categories and activities with kg values;
* data-driven recommendations for the top categories with:
  * baseline kg from the actual data,
  * a recognised reference (GHG Protocol Scope 2/Scope 3, IPCC 2006, DEFRA, EPA),
  * a methodology note that explicitly says a plant-specific audit is required before any
    percentage is claimed (no invented savings);
* a disclaimer.

The Reduction Plans page reuses the **same KPI component as the dashboard** (shared
`components/KpiCards.tsx`), so the numbers are identical by construction, and it shows
month-over-month changes (value + % + ↑/↓) from the same monthly series.

Plans have: baseline, target reduction % (only accepted with a reference source + KPI),
priority, owner, dates, status and linked category. `GET /api/plans/{id}/results` returns
**measured** results: baseline (stored, or the previous year of the plan year), actual ledger
emissions of the plan year, savings, reduction %, target status — never predictions.

## 2. The electricity example (data-integrity rule)

When only total factory electricity is recorded, the analysis:
* reports the **actual** electricity emissions and their share;
* recommends installing **sub-meters per operational area** and collecting separate readings;
* recommends reviewing lighting (LED), operating hours and cooling efficiency;
* **does not name a "highest-consuming area"** because no sub-meter data exists.

This rule is enforced in the recommendation templates (the system cannot know area consumption
from a single total).

## 3. What is not yet implemented (honest)

* **Persistent study objects**: the analysis is computed on request; there is no
  `studies` table, no study history, and no "convert study → plan" one-click persistence. The UI
  pre-fills a plan from a recommendation, but the link is not stored as a foreign key.
* **Automatic detection of unusual increases** uses month-over-month comparison and top-share
  evidence; formal statistical anomaly tests (seasonality-adjusted z-scores) are not implemented.
* **Estimated costs/savings** are not provided anywhere: the data required (tariffs, capex,
  production volumes) is not captured, and inventing them was explicitly rejected.
* **Per-study PDF export**: plans appear in the existing PDF reports; standalone study documents
  are not generated.

## 4. How to use

1. Ensure records have dates and calculated factors (dashboard shows the same totals).
2. Open **خطط الخفض**: the insights list shows evidence-based items; use one to prefill a plan.
3. Complete plan fields (owner, dates, baseline, target %, reference, KPI) and save.
4. After implementation, press 📊 on the plan to see measured results vs baseline.
