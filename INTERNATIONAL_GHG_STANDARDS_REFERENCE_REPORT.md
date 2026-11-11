# International GHG Standards & References Report

**Date:** 2026-11-03 · **Catalogue:** 36 entries in `reference_library` (live DB verified)
**Breakdown:** 12 standards · 2 methodologies · 7 factor databases · 3 GWP sources · 12 national inventories (14 Egypt-specific entries)

URLs are recorded only where the official page is known; entries whose site was not verified carry
`url = NULL` with a note (they are never invented). Access date: 2026-11-03.

## 1. IPCC

| Reference | Edition | URL | Chapter/table | Role |
|---|---|---|---|---|
| 2006 IPCC Guidelines | 2006 | https://www.ipcc-nggip.iges.or.jp/public/2006gl/ | Vol.2 Ch.2 Table 2.2; Vol.3 Ch.2 Table 2.1 | Default activity factors (labelled international_default) |
| 2019 Refinement | 2019 | https://www.ipcc-nggip.iges.or.jp/public/2019rf/index.html | Refinement volumes | Methodology reference (no values imported yet) |
| IPCC EFDB | online DB | https://www.ipcc-nggip.iges.or.jp/EFDB/main.php | web database | Future factor sourcing |
| AR4 GWP-100 | 2007 | https://www.ipcc.ch/report/ar4/syr/ | WG1 Ch.2 Table 2.14 | Refrigerant GWP basis AR4 |
| AR5 GWP-100 | 2014 | https://www.ipcc.ch/report/ar5/syr/ | WG1 Ch.8 Table 8.7 | Default refrigerant GWP basis |
| AR6 GWP-100 | 2021 | https://www.ipcc.ch/report/ar6/syr/ | WG1 Ch.7 Table 7.15 | Refrigerant GWP basis AR6 |

Distinction enforced: **methodologies/GWP values are not activity-specific emission factors**;
GWP values are stored separately from combustion factors and never mixed across assessment reports.

## 2. ISO (requirements, not factor databases)

| Standard | Edition | URL | Notes |
|---|---|---|---|
| ISO 14064-1 | 2018 | https://www.iso.org/standards.html | Organizational inventory requirements; catalogue entry |
| ISO 14064-2 | 2019 | https://www.iso.org/standards.html | Project-level reductions |
| ISO 14064-3 | 2019 | https://www.iso.org/standards.html | Validation/verification |
| ISO 14067 | 2018 | https://www.iso.org/standards.html | Product carbon footprint |

All four are flagged `kind = standard` — the platform explicitly states they define requirements and
are **not** emission-factor databases (tested: `test_catalogue_complete_and_honest`).

## 3. GHG Protocol

| Reference | Edition | URL | Role |
|---|---|---|---|
| Corporate Accounting and Reporting Standard | Revised 2004 | https://ghgprotocol.org/corporate-standard | Boundary setting + Scope 1/2/3 classification (basis of the scope classifier) |
| Scope 2 Guidance | 2015 | https://ghgprotocol.org/scope-2-guidance | Location vs market-based; market requires supplier evidence |
| Corporate Value Chain (Scope 3) Standard | 2011 | https://ghgprotocol.org/standards/scope-3-standard | 15 Scope 3 categories |

## 4. Other international sources

| Reference | Organisation | URL | Applicability | Role |
|---|---|---|---|---|
| Montreal Protocol / OzonAction | UNEP | https://www.unep.org/ozonaction | GLOBAL | Refrigerant policy |
| Kigali Amendment | UNEP | https://www.unep.org/ozonaction/our-work/kigali-amendment | GLOBAL | HFC phase-down context |
| GHG Emission Factors Hub | US EPA | https://www.epa.gov/climateleadership/ghg-emission-factors-hub | **US only** | Never presented as Egyptian/global |
| GHG Conversion Factors | UK DESNZ/DEFRA | https://www.gov.uk/government/collections/government-conversion-factors-for-company-reporting | **GB only** | Same rule |
| Emissions Factors 2025 | IEA | https://www.iea.org/data-and-statistics/data-product/emissions-factors-2025 | GLOBAL (paywalled) | Egypt values not accessible → recorded unavailable |
| FAOSTAT | FAO | https://www.fao.org/faostat/ | GLOBAL | Agriculture/AFOLU future sourcing |
| EDGAR | EC JRC | https://edgar.jrc.ec.europa.eu/ | GLOBAL | Cross-checking only |
| Ember | Ember | https://ember-energy.org/ | GLOBAL | Candidate for future verified Egypt grid factor |
| ASHRAE technical resources / Std 34 | ASHRAE | https://www.ashrae.org/technical-resources | GLOBAL | Refrigerant designations/safety; GWP comes from IPCC |

## 5. Egyptian sources (registered)

| Reference | Type | URL | Status |
|---|---|---|---|
| EEHC Annual Report 2023/2024 | national inventory | verified PDF (downloaded, inspected) | Official factor used |
| Egypt BTR1 (2024) | national inventory | UNFCCC link (from client brief) | Registered; not extracted |
| Egypt CRT (2024) | national inventory | https://unfccc.int/documents/645201 | Registered; not extracted |
| Egypt NC4 | national inventory | https://unfccc.int/documents/657656 | Registered; not extracted |
| CAPMAS statistics | national inventory | https://www.capmas.gov.eg/ | Registered |
| NREA | national inventory | https://www.nrea.gov.eg/ | Registered |
| EEAA / Ministry of Environment | national inventory | https://www.eeaa.gov.eg/ | Registered |
| EETC, EgyptERA, EGPC, EGAS, MoEE, MoA, National Ozone Unit | various | **null** (official sites not verified) | Recorded by name only — no invented URLs |

## 6. How the library is exposed

* API: `GET /api/references?kind=&country=&q=`, `GET /api/references/groups`.
* UI: «المراجع والمعايير» page — grouped by kind, shows title, organisation, edition, year,
  sectors, methodology, chapter/table, access date and the official link (or an explicit
  "URL not verified" label).
* Screenshot: `docs/screenshots/03_reference_library.png`.

## 7. Limitations

* ISO catalogue links point to the official standards catalogue, not per-standard deep links
  (no numeric page IDs were invented).
* BTR1/CRT/NC4 documents are registered but their tables were not machine-extracted in this build.
* IEA Egypt data is paywalled; EPA/DEFRA factors are US/UK-only and are flagged as such.
