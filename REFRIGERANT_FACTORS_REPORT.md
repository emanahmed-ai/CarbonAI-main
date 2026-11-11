# Refrigerant Factors Report

**Date:** 2026-11-11 · Factors live in the **Emission Factors** module only (the dedicated
equipment page was removed on request; the science stays).

## 1. What is stored where

* `refrigerants` table: designation, chemical name, formula, family (HFC/HFC blend/HCFC/HFO/
  natural), blend composition (mass fractions), GWP-100 per IPCC basis (AR4/AR5/AR6),
  GWP-20/GWP-500 (currently NULL — see §4), basis notes, source reference, status.
* `emission_factors`: one factor per refrigerant × basis — `REF-<key>-<AR4|AR5|AR6>` —
  category `refrigerant`, unit `kg` (kg CO₂e per kg leaked), classification
  `international_default`, source = IPCC assessment report, status `unverified` until a reviewer
  signs off. 17 substances → **44 factors**.
* The factors are searchable/filterable in the Emission Factors page (admin-only) with country,
  category, gas, year, unit, source, status and classification columns, and via
  `GET /api/factors?category=refrigerant` (admin) or `GET /api/factors/suggest` (all roles).

## 2. GWP-100 values and assessment basis

| Refrigerant | Family | AR4 | AR5 | AR6 | Notes |
|---|---|---|---|---|---|
| R-134a | HFC | 1430 | 1300 | 1530 | |
| R-32 | HFC | 675 | 677 | 771 | |
| R-125 | HFC | 3500 | 3170 | 3740 | |
| R-143a | HFC | 4470 | 4800 | 5810 | |
| R-227ea | HFC | 3220 | 3350 | 3600 | |
| R-22 | HCFC | 1810 | 1760 | 1960 | Montreal Protocol phase-out context |
| R-404A | blend 44/52/4 | 3922 | 3943 | 4728\* | published AR4/AR5 |
| R-407A | blend 20/40/40 | 2107 | 1923 | 2262\* | published AR4/AR5 |
| R-407C | blend 23/25/52 | 1800 | 1624 | 1908\* | published AR4/AR5 |
| R-410A | blend 50/50 | 2088 | 1924 | 2256\* | published AR4/AR5 |
| R-507A | blend 50/50 | 3985 | 3985 | 4775\* | published AR4/AR5 |
| R-290 | natural | 3.3 | 3 | — | |
| R-600a | natural | 3 | 3 | — | |
| R-744 | natural | 1 | 1 | 1 | definitional |
| R-1234yf | HFO | — | 4 | — | not in AR4 |
| R-1234ze(E) | HFO | — | 7 | — | not in AR4 |
| R-717 (ammonia) | natural | 0 | 0 | — | not a GHG under the Convention |

`*` computed by mass-fraction weighting from the same report's component values; the method was
validated against published AR5 blend values (R-410A 1924 ✓, R-407C 1624 ✓, R-404A 3943 ✓,
R-507A 3985 ✓). `—` = not recorded in this build (never invented).

**Basis rule:** every factor ID embeds the basis; calculations never mix AR4/AR5/AR6; the chosen
basis is written into the factor snapshot and the selection reason.

## 3. Usage after the page removal

* Ledger path: create an activity in category `refrigerant` with a `REF-*` factor (or let the
  nearest-year policy pick one). Quantity = leaked kg → kg CO₂e = leaked × GWP-100.
* Scope: controlled equipment → Scope 1 per the GHG Protocol classifier (tested).
* Dashboard: "Refrigerant emissions" card and `share of Scope 1` remain (they read ledger
  records, not a management page).
* No equipment/service management UI or API remains (`/api/refrigerants`, `/api/cooling/*` → 404).

## 4. Gaps

* GWP-20 and GWP-500 columns are NULL with the note "not transcribed in this build"; the
  calculation basis is GWP-100.
* AR6 values for HFOs and hydrocarbons are not recorded (left empty).
* Blend AR6 values are computed, not published, and are flagged as computed.
* No refrigerant purchase/recovery inventory (removed with the page).
