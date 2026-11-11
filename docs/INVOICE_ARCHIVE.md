# Invoice Archive — Documentation

## Purpose

Register utility/fuel invoices (with the original document attached), calculate their emissions
through the existing engine, and keep a searchable, auditable archive. Invoices are **never
deleted** — they can only be voided with a reason.

## Storage

* Files are validated (extension ∈ {pdf, jpg, jpeg, png}, **magic-byte check**, ≤ 10 MB) and stored
  at `data/invoices/<sha256[:16]>_<safe-name>`.
* The SHA-256 of the document is stored on the invoice row. A partial unique index
  `ux_invoice_hash (facility_id, file_hash)` prevents the same document being registered twice for
  a facility.
* Soft duplicate check: same facility + supplier + invoice number + invoice date (non-void) → 409
  with `existing_invoice_id`; `confirm_duplicate=true` overrides deliberately.

## Extraction (honest capability)

| File type | Behaviour |
|---|---|
| PDF with text layer | `pdfplumber` reads pages 1–5; regex candidates for invoice number, first date, total amount, supplier line. Status `text_extracted`; values are **candidates requiring human review**. |
| PDF scan / image | No OCR engine is installed on this server → status `unavailable` with a clear note. Manual entry required; the document is still archived as evidence. |

Extracted values are never auto-saved as verified data.

## Calculation

`POST /api/invoices/{id}/calculate` accepts either:
* `factor_id` (+ optional version) from the library — proxy confirmation flags apply; or
* `manual_value` + `manual_source` (stored as user-supplied/unverified).

The invoice must have quantity, unit, category and date. The engine's `add_record` creates the
ledger row (`origin = invoice:<id>`, `evidence_ref = invoice number`), and the invoice stores
`record_id`, factor id/version/value/source, status (`calculated` / `needs_review`).
Manual factors cannot be used as a Scope 2 "market-based" shortcut without a source.

## Audit & lifecycle

`invoice_audit_log` records: `created` (incl. extraction status), `calculated` (record + factor),
`voided` (reason). Status transitions: `draft → calculated|needs_review → void`.
Voiding keeps the linked ledger record intact (accounting history is never rewritten).

## Permissions

| Role | Capabilities |
|---|---|
| admin / head_office | full, incl. void |
| factory_manager | create/calculate/search **own facility only** (403 otherwise) |
| viewer | no invoice menu (API requires a write role for creation) |

## Search

`GET /api/invoices?search=&year=&month=&status=&category=` searches name, number and supplier;
results include facility, kg CO₂e, scope, status and file presence. The detail view streams the
original document through an authenticated endpoint (`/api/invoices/{id}/file`) with the same
tenancy checks.
