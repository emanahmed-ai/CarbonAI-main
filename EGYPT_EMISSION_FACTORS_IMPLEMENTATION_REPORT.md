# Egypt Emission Factors — Implementation Report

**Country:** Egypt (EG) · **Coverage period:** 2006–2026 · **Date:** 2026-11-03

## 1. What was built

| Component | Location |
|---|---|
| Seed dataset (sources + factors) | `database/seed/egypt_factors_2006_2026.json` |
| Loader / seeder / coverage builder | `services/egypt_seed.py` |
| Coverage matrix (JSON seed + CSV deliverable) | `database/seed/egypt_coverage_2006_2026.json`, `EGYPT_ANNUAL_COVERAGE_2006_2026.csv` |
| Schema (additive, v3) | `emission_factors` extra columns (`sector`, `fuel_type`, `technology`, `gas`, `country_scope`, `quality_level`, `uncertainty`, `data_year`, `source_page`, `source_table`), `factor_coverage`, `source_documents` |
| API | `GET /api/factors/egypt`, `/coverage-matrix`, `/export.csv`; admin-only writes |
| UI | Factors → «معاملات مصر» + «مصفوفة التغطية 2006–2026» tabs |
| Default country | `settings.default_country = 'EG'` (seeded; UI defaults to EG) |

## 2. Factor counts by classification and sector

| Classification | Count | Sector |
|---|---|---|
| **egypt_official** (Type A) | **1** | Energy – Power generation (EEHC thermal intensity) |
| egypt_research (Type B) | **0** | — (no verified Egyptian research factor loaded) |
| international_egypt_specific (Type C) | **0** | — (IEA Egypt data is paywalled; no verified figure available) |
| **international_default** (Type D) | **12** | Energy – stationary combustion (6 fuels), IPPU cement (1), IPPU refrigerants/industrial gases (5) |

Total: **13 factors**, all inserted as `unverified` pending a named reviewer sign-off
(library rule: no factor is auto-verified).

### The one Egyptian official factor (verbatim source)

> **EG-EEHC-THERMAL-INTENSITY-FY2023-24** — 0.3803 kg CO₂/kWh (original: **380.3 ton CO₂/GWh in
> 2023/2024**), EEHC Annual Report 2023/2024, "Environmental indicators of thermal power plants",
> PDF p.16 (printed p.30).
> Boundary: **thermal power plants only** (Scope 1 of generation). It is **not** a consumer
> grid-consumption (Scope 2) factor and the record says so explicitly.

### International defaults (Type D) — exact values

| Factor | Value | Source |
|---|---|---|
| Diesel / gas oil | 74.1 kg CO₂/GJ | IPCC 2006 Vol.2 Table 2.2 (74,100 kg/TJ) |
| Natural gas | 56.1 kg CO₂/GJ | IPCC 2006 Vol.2 Table 2.2 |
| Motor gasoline | 69.3 kg CO₂/GJ | IPCC 2006 Vol.2 Table 2.2 |
| LPG | 63.1 kg CO₂/GJ | IPCC 2006 Vol.2 Table 2.2 |
| Residual fuel oil | 77.4 kg CO₂/GJ | IPCC 2006 Vol.2 Table 2.2 |
| Other bituminous coal | 94.6 kg CO₂/GJ | IPCC 2006 Vol.2 Table 2.2 |
| Cement clinker | 510 kg CO₂/t clinker | IPCC 2006 Vol.3 Table 2.1 (0.510 t/t) |
| R-410A | 1924 kg CO₂e/kg | IPCC AR5 GWP-100 |
| R-134a | 1300 | IPCC AR5 GWP-100 |
| R-32 | 677 | IPCC AR5 GWP-100 |
| R-22 (HCFC-22) | 1760 | IPCC AR5 GWP-100 |
| SF6 | 23,500 | IPCC AR5 GWP-100 |

Every row documents that CH₄/N₂O defaults from Table 2.2 are excluded from the CO₂ total and
that the factor is **generic international**, never Egyptian official.

## 3. Annual coverage matrix

420 rows = 21 years × 20 catalogued activities. Statuses per year:

| Status | Rows | Meaning |
|---|---|---|
| available | 1 | only 2024 (FY2023/24 EEHC figure) |
| international_default | 252 | IPCC defaults usable as documented fallback (labelled) |
| pending | 167 | no verified Egyptian source loaded for that year/activity |
| provisional / estimated / unavailable / not_applicable | 0 | none asserted |

2025 and 2026 are **assessed independently**: both have 0 available, 8 pending and 12
international-default entries. FY2023/24 data is never presented as 2025/2026 actual data.
Deliverable: `EGYPT_ANNUAL_COVERAGE_2006_2026.csv`.

## 4. Source selection priority (implemented in `factor_library.suggest`)

1. Egyptian official factor, same country/category/year/unit → auto-selected **only if verified
   and unique**.
2. Nearby-year official factor → shown as candidate, requires explicit choice + reason.
3. Egyptian research factor → candidate (none loaded).
4. International Egypt-specific → candidate (none loaded).
5. International default → candidate, labelled by classification; using it requires explicit
   selection (proxy confirmation where applicable).

## 5. What was NOT done and why (no fabrication)

* **No invented Egyptian values.** Only figures quoted from an inspected official document were
  entered. The report was downloaded (12.4 MB, HTTP 200) and inspected with pdfplumber.
* **No derived "grid factor".** EEHC publishes thermal-only intensity; a grid-wide consumption
  factor would require a documented derivation across all generation (including renewables and
  private producers) — recorded as Pending in the matrix.
* **2025/2026 remain Pending** — no official publication was verified.
* **New Zealand removal is gated.** Dry-run + backup produced
  (`scripts/nz_removal_dry_run.py`); execution requires `--execute --confirm REMOVE-LEGACY-NZ`.
  Existing `data/carbonai.db` still contains 37 legacy NZ rows until that confirmation.
* **BTR1 / CRT / NC4 not extracted.** These are large UNFCCC PDFs; automated extraction was not
  performed in this build, so nothing from them is claimed.

## 6. How to add factors in the future

1. Put the official number in `database/seed/egypt_factors_2006_2026.json` with `reference_id`,
   `source_locator` (page/table), `data_year`, classification and boundary note.
2. `python scripts/build_egypt_seed.py` regenerates the coverage matrix + CSV.
3. Restart (seed is idempotent) or use the admin UI «إضافة معامل» (admin-only).
4. A named reviewer must verify the factor (`POST /api/factors/{id}/{version}/verify`) before it
   can be auto-selected by the engine.
