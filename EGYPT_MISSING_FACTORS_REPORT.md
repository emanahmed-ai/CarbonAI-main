# Egypt — Missing Factors Report

**Date:** 2026-11-03 · Generated from `factor_coverage` (420 rows) and the seed dataset.

## Summary

| Classification | Loaded |
|---|---|
| Egyptian official (A) | 1 |
| Egyptian research (B) | 0 |
| International Egypt-specific (C) | 0 |
| International default (D) | 12 |

## What is missing (explicitly recorded as pending — never filled with invented values)

| Sector | Activity | Status | Why it is missing / what is required |
|---|---|---|---|
| Energy – Power generation | Grid consumption factor (Scope 2) | **Pending** (all years) | EEHC publishes generation-side thermal intensity only. A consumption-based national grid factor requires a documented derivation (total CO₂ ÷ total grid kWh incl. renewables) or a verified IEA/Ember Egypt figure. |
| Energy – Power generation | Thermal intensity, years ≠ 2024 | **Pending** | FY2023/24 is the only EEHC annual report inspected. Other years require their own reports; 2025 needs FY2024/25. |
| Energy – Stationary combustion | Diesel, natural gas, gasoline, LPG, fuel oil, coal | International default | IPCC 2006 defaults are loaded as documented fallbacks. Egypt-specific official factors (e.g. EEAA/EGPC fuel analyses) were not available in a verifiable form. |
| IPPU | Cement clinker | International default | IPCC default 0.510 t CO₂/t clinker. No Egyptian plant-specific factor loaded. |
| IPPU | Refrigerants / F-gases | International default | AR5 GWP values. Egypt-specific leakage rates and equipment inventories are not factors and were not asserted. |
| Waste | Landfill, incineration | **Pending** | Require Egypt-specific DOC/MCF/composition parameters (methodology, not a single factor). |
| Water | Wastewater | **Pending** | Requires influent/effluent data and methane correction factors. |
| Transport | Freight tonne-km | **Pending** | No verified Egyptian tonne-km factor; fuel-based calculation remains available. |
| Agriculture | Enteric fermentation, manure, soils, rice, residue burning | **Pending** | Require livestock populations and Tier 1/2 Egypt parameters. |
| AFOLU / LULUCF | Forestry, land use, land-use change | **Pending** | Requires land-use data and a documented methodology. |

## 2025 and 2026

| Year | available | international_default | pending |
|---|---|---|---|
| 2025 | 0 | 12 | 8 |
| 2026 | 0 | 12 | 8 |

No official 2025/2026 Egyptian publication was verified in this build, so no value was copied
forward from 2023/2024. This is the correct, documented state.

## How to close the gaps (procedure, not guesswork)

1. Obtain the official document (EEHC annual report for the target year, EEAA inventory, CAPMAS,
   EETC, EGPC/EGAS publication).
2. Record `reference_id`, exact page/table, data year, unit and boundary.
3. Add the factor to `database/seed/egypt_factors_2006_2026.json` (or admin UI) and rebuild the
   coverage matrix.
4. A named reviewer verifies it. Only then can the engine auto-select it.

> Rule enforced by the system: a missing factor is visible as missing. The engine never falls back
> to another country's factor without explicit, logged confirmation.
