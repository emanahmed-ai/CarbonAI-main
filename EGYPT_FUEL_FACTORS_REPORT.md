# Egypt Fuel Factors Report

**Date:** 2026-11-11 · Scope: diesel, fuel oil (mazut), gasoline/petrol.

## 1. What is loaded now (live database)

| Factor | Value | Unit | Classification | Source | Valid |
|---|---|---|---|---|---|
| `IPCC-DIESEL-GAS-OIL-GJ` | 74.1 | kg CO₂/GJ | **international_default** | IPCC 2006 Vol.2 Table 2.2 (74,100 kg/TJ) | 2006–2026 |
| `IPCC-RESIDUAL-FUEL-OIL-GJ` | 77.4 | kg CO₂/GJ | **international_default** | IPCC 2006 Vol.2 Table 2.2 | 2006–2026 |
| `IPCC-MOTOR-GASOLINE-GJ` | 69.3 | kg CO₂/GJ | **international_default** | IPCC 2006 Vol.2 Table 2.2 | 2006–2026 |
| `IPCC-NATURAL-GAS-GJ` | 56.1 | kg CO₂/GJ | international_default | IPCC 2006 Table 2.2 | 2006–2026 |
| `IPCC-LPG-GJ` | 63.1 | kg CO₂/GJ | international_default | IPCC 2006 Table 2.2 | 2006–2026 |
| `IPCC-COAL-OTHER-BITUMINOUS-GJ` | 94.6 | kg CO₂/GJ | international_default | IPCC 2006 Table 2.2 | 2006–2026 |
| `EG-EEHC-THERMAL-INTENSITY-FY2023-24` | 0.3803 | kg CO₂/kWh | **egypt_official** | EEHC Annual Report 2023/2024 p.16 (thermal plants, generation side) | 2024 |

Every row carries `source_organization`, `source_document`, `source_locator`, `data_year`,
methodology, boundary note and the four-way classification. No value is labelled Egyptian official
unless it was quoted from an inspected Egyptian official document.

## 2. What could NOT be added

**No verified Egyptian official diesel/fuel-oil/gasoline factor was available in this build.**
The EEHC report contains generation data but not per-fuel default factors; EGPC/EGAS official
documents were not verified. Per the project rules, no Egyptian factor was invented, and IPCC
defaults are **not** presented as Egyptian official values. This is a documented data gap
(`EGYPT_MISSING_FACTORS_REPORT.md`).

## 3. Selection policy (implemented)

For every activity the Core now applies, in order:

1. **Exact year** factor for the same country (verified or a unique national one; unverified is
   flagged).
2. **Nearest available year** — allowed only for the same country or for international defaults;
   the result is marked `ESTIMATED` in `calc_notes`/factor selection reason (e.g. "factor valid
   2024, used for reporting year 2026, ±2 years").
3. **IPCC international default** — auto-selected for rows where no national factor exists,
   labelled "international default (auto-selected, marked)", stored as unverified/estimate.
4. **No factor at all** → the row is rejected with a clear reason; remaining rows continue.

Cross-country national factors are **never** auto-selected (they remain an explicit proxy choice
requiring confirmation). This was enforced after a test proved a New Zealand activity could
otherwise pick an Egyptian factor.

## 4. Where the factors are available

Imports (auto), invoices (auto by invoice year), the calculator, dashboard aggregation, reports
and reduction-plan calculations — all through the same Core (`ledger.add_record` →
`calculations.calculate`). The factors are listed in the Emission Factors page (admin-only)
with source and classification.

## 5. Unit handling

Values are stored per GJ (energy basis), exactly as published. The Core converts quantities
between compatible units (GJ/MJ/kWh) and refuses mass↔volume conversions without a documented
density/NCV — so a diesel volume in litres requires a documented conversion property rather than
a silent assumption. This is intentional and tested.
