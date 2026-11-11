# Refrigerant Emissions & GWP Report

**Date:** 2026-11-03 · **Module:** Refrigerants & Cooling (new, fully integrated)
**Database:** 17 refrigerants · **44 library factors** (REF-<key>-<basis>) · 3 GWP bases

## 1. Refrigerant database

Fields per substance: designation, chemical name, formula, family, blend composition (mass
fractions), GWP-100 per IPCC basis (AR4/AR5/AR6), GWP-20/GWP-500 (see §4), basis notes,
source, verification status.

| Refrigerant | Family | Formula | AR4 | AR5 | AR6 |
|---|---|---|---|---|---|
| R-134a | HFC | C2H2F4 | 1430 | 1300 | 1530 |
| R-32 | HFC | CH2F2 | 675 | 677 | 771 |
| R-125 | HFC | C2HF5 | 3500 | 3170 | 3740 |
| R-143a | HFC | C2H3F3 | 4470 | 4800 | 5810 |
| R-227ea | HFC | C3HF7 | 3220 | 3350 | 3600 |
| R-22 | HCFC | CHClF2 | 1810 | 1760 | 1960 |
| R-404A | blend 44/52/4 | — | 3922 | 3943 | 4728* |
| R-407A | blend 20/40/40 | — | 2107 | 1923 | 2262* |
| R-407C | blend 23/25/52 | — | 1800 | 1624 | 1908* |
| R-410A | blend 50/50 | — | 2088 | 1924 | 2256* |
| R-507A | blend 50/50 | — | 3985 | 3985 | 4775* |
| R-290 | natural | C3H8 | 3.3 | 3 | — |
| R-600a | natural | C4H10 | 3 | 3 | — |
| R-744 | natural | CO2 | 1 | 1 | 1 |
| R-1234yf | HFO | C3H2F4 | — | 4 | — |
| R-1234ze(E) | HFO | C3H2F4 | — | 7 | — |
| R-717 | natural | NH3 | 0 | 0 | — |

`*` = **computed** by mass-fraction weighting from the same report's component values (method
validated against published AR5 blends: R-410A 1924 ✓, R-407C 1624 ✓, R-404A 3943 ✓, R-507A 3985 ✓).
`—` = not recorded in this build (not invented). `0` for ammonia = not a GHG under the Convention.

**Basis rule enforced:** one basis per calculation; GWP values from different IPCC reports are never
mixed in one record; the chosen basis is stored on every service record and factor snapshot.

## 2. GWP-20 / GWP-500

Left **NULL** with an explicit note: the 20-year/500-year columns were not transcribed in this build.
The requirement allows omission when authoritative values are not available; they are never guessed.

## 3. Emission calculation

* Direct leakage: **kg CO₂e = leaked kg × GWP-100** (served by the existing engine function
  `calculations.refrigerant_leakage`, which mandates a GWP source).
* **Leakage determination:**
  1. explicit `leaked_kg` (technician measurement) wins;
  2. otherwise `leaked = max(0, added − recovered)` — recovered gas is NOT an atmospheric emission;
  3. the **full charge is never assumed leaked**;
  4. a record with no quantities is rejected (no default leakage rate exists in the system);
  5. no default leakage rate is applied anywhere.
* The calculation is written to the ledger through `ledger.add_record` with the refrigerant factor
  `REF-<key>-<basis>` — so the factor value, version, basis, source and boundary are snapshotted per
  record exactly like every other emission.

## 4. Scope classification & double counting

* Refrigerant leakage from company-owned/controlled equipment → **Scope 1** (GHG Protocol; the
  classifier maps `owned_controlled` + `refrigerant` → Scope 1). If the equipment is not controlled,
  the user can classify it outside Scope 1; the record states the boundary input used.
* **Electricity for cooling is entered separately** as an electricity activity → **Scope 2**.
  The module never auto-creates electricity records and never merges the two sources.
* Refrigerant production/supply-chain emissions are NOT included in the leakage calculation.
* Dashboard `by_scope_kg` shows refrigerant only under Scope 1; the KPI
  `share_of_scope1_pct` is computed against the actual Scope 1 total (tested:
  5 kg leaked × 1924 = 9,620 kg = 100% of Scope 1 in the isolation test; electricity 4,500 kg stays
  in Scope 2).

## 5. Verified calculations (automated tests)

| Case | Input | Expected | Result |
|---|---|---|---|
| Single gas | R-410A AR5, added 10 kg | 10 × 1924 = 19,240 | ✔ |
| Blend | R-407C AR5, leaked 1 kg | 1 × 1624 | ✔ |
| Recovery | added 10, recovered 4 | 6 × 1924 = 11,544 | ✔ |
| Over-recovery | added 2, recovered 5 | leaked 0, 0 kg | ✔ |
| Explicit leak | leaked 2.5 (added 10) | 2.5 × 1924 = 4,810 | ✔ |
| Missing quantities | no added/recovered/leaked | 400 error | ✔ |
| Scope separation | refrigerant + electricity | Scope 1 / Scope 2 separately | ✔ |
| Tenancy | factory B → A's equipment | 403 | ✔ |
| Invalid basis | AR9 | 400 | ✔ |

## 6. Equipment inventory and service records

Tables `cooling_equipment` (facility, identifier, equipment type, refrigerant, charge kg) and
`refrigerant_service_records` store: added/recovered/explicit leaked kg, GWP basis and value,
calculated leaked kg, kg CO₂e, t CO₂e, ledger record id, methodology text, evidence reference,
notes, creator and timestamp. Equipment types supported: commercial AC, central HVAC, chillers,
refrigerators/freezers, industrial refrigeration, cold storage, other.

## 7. UI integration

* New page «المبردات والتكييف»: Scope 1 refrigerant KPI, share of Scope 1, equipment count,
  by-equipment bar chart, equipment form/table, service form (with result card), service records,
  refrigerant database with AR4/AR5/AR6 columns.
* Dashboard: refrigerant KPI strip (kg, share of Scope 1, records, top equipment).
* Reports: refrigerant records flow into the ledger and therefore into the detailed/annual PDFs.
* Screenshots: `docs/screenshots/01_dashboard_refrigerant_kpi.png`,
  `docs/screenshots/02_refrigerants_module.png`.

## 8. Limitations

* GWP-20/GWP-500 not transcribed (documented above).
* AR6 values for HFOs/hydrocarbons not recorded (left empty rather than guessed).
* "Repair" vs "recharge" events are modelled purely by the mass balance added−recovered (or an
  explicit leak); equipment-level leak-rate screening (e.g. EPA 608 thresholds) is not implemented.
* No refrigerant purchase/recovery inventory ledger (only service events).
