# Emission Factor Source Registry

Registered in `sources` (idempotently seeded) and referenced by every factor row.

| reference_id | Organisation | Document | Year | URL | Scope | Usage notes |
|---|---|---|---|---|---|---|
| **EG-EEHC-AR-2023-24** | Egyptian Electricity Holding Company (EEHC) — government | EEHC Annual Report 2023/2024 (English edition) | 2024 | https://www.eehc.gov.eg/CMSEehc/Files/AnnualReport2024En.pdf | Egypt | Public report, downloaded and inspected (12.4 MB, HTTP 200) with pdfplumber. Values quoted verbatim with PDF/printed page references. |
| **IPCC-2006-GL** | IPCC — international | 2006 IPCC Guidelines, Vol.2 Energy Table 2.2; Vol.3 IPPU Table 2.1 | 2006 | https://www.ipcc-nggip.iges.or.jp/public/2006gl/ | Global | Default factors only; never presented as Egyptian official. |
| **IPCC-AR5-GWP100** | IPCC — international | AR5 100-year Global Warming Potential values | 2014 | https://www.ipcc.ch/report/ar5/syr/ | Global | GWP-100 applied to refrigerant leakage (kg CO₂e per kg). |
| SRC-001…SRC-018, **NZ-MFE-2023-ME1764** (legacy) | various / NZ MfE | Original starter reference list | — | — | — | Legacy list kept untouched. NZ source row is a target of the gated removal script; historical snapshots are never modified. |

## Source inspection log

| Date | Action | Result |
|---|---|---|
| 2026-11-03 | Downloaded EEHC Annual Report 2023/2024 | 12,439,261 bytes, 51 pages, extracted pages 16–18 (GHG section) |
| 2026-11-03 | Searched IEA "Emissions Factors 2025" page | Egypt values not visible (dataset behind account/paywall) → recorded as unavailable, not guessed |
| 2026-11-03 | UNFCCC BTR1 / CRT / NC4 | Not machine-extracted in this build → nothing claimed from them |
| 2026-11-03 | OCR tooling check | `pytesseract`/`tesseract` absent → image extraction reported `unavailable` |

## Integrity rules

1. Every factor row carries `reference_id`, `source_organization`, `source_document`,
   `source_locator`, and where available `source_page`/`source_table`/`source_url`.
2. A factor cannot be verified without a recorded locator or URL (`factor_library.set_verification`).
3. Changing a source is a new factor version — previous versions and audit rows are preserved.
4. `source_documents` table stores checksum/extraction/review status for ingested files
   (available for future automated ingestion).
