# Data Import — Documentation

## Two import paths

| Path | Endpoint | When |
|---|---|---|
| Smart mapping (recommended) | `POST /api/imports/analyze` → `/preview-mapped` → `/commit-mapped` | Any column naming (Arabic/English, synonyms, fuzzy variants) |
| Legacy template | `POST /api/imports/preview` → `/commit` | Files already using the canonical Arabic/English headers |

Files: `.csv` (UTF-8 or Windows-1256) and `.xlsx/.xls`. Size limit 10 MB.

## Smart mapping flow

1. **Analyze** — reads sheets/columns/sample rows and returns per-field suggestions:
   `{column, confidence 0–1, method (exact synonym / synonym contains / fuzzy / heuristic), ambiguous, alternatives}`.
   Recognised fields: activity, quantity, unit, date, scope, factor, source, country, company,
   facility, category, fuel, description, control, energy_purchased, relation, invoice_number,
   amount, supplier.
2. **Review mapping** — the UI pre-selects only high-confidence non-ambiguous columns; anything
   below the ambiguity threshold (e.g. two similar quantity columns) is left for the user.
   Required fields: activity, quantity, unit — the commit button stays disabled until mapped.
3. **Preview** — validates every row (numbers, units, dates, scopes), lists rejected rows with
   reasons and warnings, and shows **which emission factor would be applied per row**:
   `auto` (exactly one verified national factor fits), `needs_selection`, `from_file`, `needs_input`.
4. **Commit** — inserts accepted rows through the unchanged ledger engine. Rows remain
   `needs_factor`/`needs_date` when data is missing (never zero-filled, never invented dates).

## Duplicate protection

* Every upload is SHA-256 hashed. A previously committed identical file → **409** with the original
  batch info (`force=true` overrides, but the ledger's own fingerprint check still skips row-level
  duplicates).
* Row-level duplicates: same activity/date/quantity/unit/country/company/facility/factor →
  reported as duplicates, not inserted (unless `keep_duplicates`).
* All attempts are recorded in `import_batches` (file name, hash, counts, notes) and rejections in
  `import_rejections`.

## Tenancy

* `factory_manager` uploads are always attributed to their own facility (file company/facility
  columns are overridden; the preview shows `facility_override`).
* `head_office`/`admin` may use file-provided company/facility columns.

## Example (curl)

```bash
curl -H "Authorization: Bearer $TOKEN" -F "file=@data.csv" \
     http://127.0.0.1:8000/api/imports/analyze

curl -H "Authorization: Bearer $TOKEN" -F "file=@data.csv" \
     -F 'mapping={"activity":"بيان البند","quantity":"كمية الاستهلاك","unit":"وحدة القياس","date":"تاريخ الفاتورة"}' \
     -F "default_country=EG" http://127.0.0.1:8000/api/imports/preview-mapped

curl -H "Authorization: Bearer $TOKEN" -F "file=@data.csv" \
     -F 'mapping={"activity":"بيان البند","quantity":"كمية الاستهلاك","unit":"وحدة القياس","date":"تاريخ الفاتورة"}' \
     -F "default_country=EG" http://127.0.0.1:8000/api/imports/commit-mapped
```
