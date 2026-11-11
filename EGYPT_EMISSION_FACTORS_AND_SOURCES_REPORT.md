# Egypt Emission Factors & Sources Report (consolidated)

**Date:** 2026-11-03 · **Default country:** EG · **Coverage:** 2006–2026

> Detailed per-factor tables: `EGYPT_EMISSION_FACTORS_IMPLEMENTATION_REPORT.md`,
> `EGYPT_MISSING_FACTORS_REPORT.md`, `EGYPT_2025_ASSESSMENT.md`, `EGYPT_2026_ASSESSMENT.md`,
> `EGYPT_ANNUAL_COVERAGE_2006_2026.csv`. This report is the consolidated summary.

## 1. Database state (verified in the live DB)

| Metric | Value |
|---|---|
| Egyptian factors total (incl. GLOBAL defaults shown in the EG view) | 13 |
| — Egyptian official (Type A) | **1** |
| — Egyptian research (Type B) | 0 |
| — International Egypt-specific (Type C) | 0 |
| — International default (Type D) | 12 |
| Coverage-matrix rows | **420** (21 years × 20 activities) |
| Sources registered for the dataset | 3 (EEHC, IPCC 2006, IPCC AR5) |
| Default country | `EG` |

## 2. The verified Egyptian official factor

**EG-EEHC-THERMAL-INTENSITY-FY2023-24** — `0.3803 kg CO₂/kWh`
(original: **380.3 ton CO₂/GWh in 2023/2024**)
* Source: EEHC Annual Report 2023/2024, environmental indicators of thermal power plants
  (PDF p.16; printed p.30). Document downloaded (12,439,261 bytes, 51 pages) and inspected with
  pdfplumber — quoted verbatim, converted t→kg / GWh→kWh.
* Boundary: **thermal power plants only** (Scope 1 of generation). It is **not** a consumer
  grid-consumption (Scope 2) factor; the factor record and UI state this explicitly.
* Verification: `unverified` pending a named reviewer (library rule). It can be selected
  explicitly; it does not auto-apply.

## 3. Factors by sector and classification

| Sector | Activity | Classification | Value | Basis / note |
|---|---|---|---|---|
| Energy – Power generation | thermal_generation_intensity | Egyptian official | 0.3803 kg CO₂/kWh | EEHC 2023/24, FY2024 |
| Energy – Stationary combustion | diesel | International default | 74.1 kg CO₂/GJ | IPCC 2006 Vol.2 Table 2.2 |
| Energy – Stationary combustion | natural_gas | International default | 56.1 kg CO₂/GJ | IPCC 2006 Vol.2 Table 2.2 |
| Energy – Stationary combustion | gasoline | International default | 69.3 kg CO₂/GJ | IPCC 2006 Vol.2 Table 2.2 |
| Energy – Stationary combustion | lpg | International default | 63.1 kg CO₂/GJ | IPCC 2006 Vol.2 Table 2.2 |
| Energy – Stationary combustion | fuel_oil | International default | 77.4 kg CO₂/GJ | IPCC 2006 Vol.2 Table 2.2 |
| Energy – Stationary combustion | coal | International default | 94.6 kg CO₂/GJ | IPCC 2006 Vol.2 Table 2.2 (other bituminous) |
| IPPU – Cement | cement_clinker | International default | 510 kg CO₂/t clinker | IPCC 2006 Vol.3 Table 2.1 |
| IPPU – Refrigerants | R-410A / R-134a / R-32 / R-22 / SF6 | International default | GWP-100 (AR5) | See refrigerant report |
| Refrigerants (17 substances × bases) | 44 library factors | International default | GWP-100 AR4/AR5/AR6 | `REFRIGERANT_EMISSIONS_AND_GWP_REPORT.md` |

## 4. Coverage matrix (2006–2026)

| Status | Rows | Meaning |
|---|---|---|
| available | 1 | only 2024 (EEHC FY2023/24) |
| international_default | 252 | IPCC defaults usable as labelled fallbacks |
| pending | 167 | no verified Egyptian source loaded for that year/activity |
| provisional / estimated / unavailable / not_applicable | 0 | nothing asserted |
| **2025** | 0 available · 12 international_default · 8 pending | assessed independently |
| **2026** | 0 available · 12 international_default · 8 pending | assessed independently |

Deliverable: `EGYPT_ANNUAL_COVERAGE_2006_2026.csv` (420 rows, UTF-8 BOM for Excel).

## 5. Source traceability

Every factor row stores: `reference_id`, `source_organization`, `source_document`,
`source_locator`, `source_page` (where applicable), `source_url`, `data_year`, `methodology`,
`boundary_note`, `quality_level`, `uncertainty`. Automated test
`test_source_traceability_everywhere` asserts that no Egypt-view factor lacks source metadata.

Source selection priority (implemented in `factor_library.suggest`): Egyptian official same-year →
nearby-year official (explicit choice + reason) → Egyptian research → international Egypt-specific
→ international default (explicit confirmation; `proxy_confirmed` enforced by the API).

## 6. Gaps (no fabrication)

* No verified **grid-consumption (Scope 2)** factor — requires a documented derivation or IEA/Ember
  Egypt data (IEA page behind a paywall; nothing claimed).
* BTR1 / CRT / NC4 registered but **not machine-extracted**; no values claimed from them.
* No Type B/C factors verified yet (research/Egypt-specific sources were not available in a
  verifiable form).
* Sector coverage pending: waste, wastewater, freight tonne-km, agriculture, AFOLU, most
  non-2024 power years.
* 2025/2026 remain Pending — this is the correct state until official publications are verified.

## 7. Administration & permissions

Factor management (create/verify) is **admin-only at the backend** (403 for head_office and factory
users — tested). Read access and the coverage matrix are available to all authenticated roles.
Export: `GET /api/factors/export.csv?country=EG`.
