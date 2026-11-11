# Status and known limitations (honest)

## Built and executed (sandbox: Python 3.12, no network)
- Decimal engine, units, GWP, selection rules (original core, 37 tests, unchanged behaviour).
- SQLite layer: schema, idempotent seeding, backup/restore, factor library (versioned + audit), scope classifier,
  ledger (monthly/annual aggregation), CSV/Excel importer, library file update, CSV + PDF reports.
- 79 tests pass (`python scripts/run_tests.py`). New tests use isolated temp databases.

## Written but NOT run for real
- `app.py` (Streamlit UI): only compiled, and every page was executed once against a *stub* of streamlit/plotly to catch
  Python errors. It was never rendered in a browser; layout, widget behaviour, file upload and download buttons are untested.
  Streamlit, Plotly were not installed in the sandbox.
- Arabic PDF: needs `arabic-reshaper`, `python-bidi` and an Arabic font; not installed here, so it was never produced.
  Without them the app shows a message and offers the English PDF. English PDF (multi-page, repeated header) was verified.

## Not built
Authentication/permissions (reviewer name is free text), OCR, automatic download/scraping of official sources,
PostgreSQL/Alembic, RLS/tenant isolation, AI assistant, attachments storage, Scope 2 market-based factor evidence workflow
(market-based needs a manual factor with a source), GWP tables for HFCs/refrigerants, currency-based (spend) factors.

## Data coverage (important)
- Only New Zealand has factors (37, all UNVERIFIED). Egypt, Saudi Arabia, UAE and every other country: **no factors**.
  The country list (42 ISO entries) is a starter set, not a coverage claim.
- No national factor is auto-used unless VERIFIED. Substitutes require explicit confirmation + written rationale.
- Source URLs were never fetched; `last_checked_at` is empty. NZ licence: Crown copyright, reuse terms unconfirmed.

## Behaviour choices to review
- Undated records with a user-typed factor are calculated, counted in totals, but excluded from monthly/annual views.
- Undated records with a library factor are `needs_date` (validity year unknown) and not counted.
- Duplicate = same activity/date/quantity/unit/country/company/facility/factor; reported, not inserted unless allowed.
- "Verified share" = calculated records with a verified factor / all records in the filter.
- Scope rules are a decision aid; ambiguous cases return needs_review with the missing facts rather than a guess.
- Original issues found: the demo "clear activities" button said "restore demo data" but emptied the table (now needs a
  confirmation tick and only touches session rows); filters did not filter data (they do now; "All" added); demo
  factors (0.45, 2.68, 0.12) are untraceable and stay labelled demo.
