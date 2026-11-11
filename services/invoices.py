"""Invoices & documents: manual entry, safe uploads, text extraction, carbon calculation,
search/archive and duplicate prevention.

Honesty rules:
* uploads are validated (extension + magic bytes + size) and stored under data/invoices/;
* PDF text layers are parsed with pdfplumber when available; images get an explicit
  'unavailable' extraction status (no OCR engine is installed) - never fabricated values;
* extracted values are CANDIDATES for human confirmation, marked unverified;
* calculations reuse the existing engine via ledger.add_record; the exact factor value,
  version and source are copied onto the invoice row;
* invoices are never deleted: status becomes 'void' with an audit entry.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from db.connection import now_iso, transaction
from services import factor_library as FL
from services import ledger as L

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "data" / "invoices"
MAX_BYTES = 10 * 1024 * 1024
ALLOWED = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}
MAGIC = {b"%PDF": "application/pdf", b"\xff\xd8\xff": "image/jpeg", b"\x89PNG\r\n\x1a\n": "image/png"}


class InvoiceError(ValueError):
    pass


class InvoiceDuplicate(InvoiceError):
    def __init__(self, message: str, existing_id: int | None = None, kind: str = "duplicate"):
        super().__init__(message)
        self.existing_id = existing_id
        self.kind = kind


def _log(con, invoice_id: int, action: str, by: str, note: str = "") -> None:
    con.execute("INSERT INTO invoice_audit_log(invoice_id,action,at,by,note) VALUES (?,?,?,?,?)",
                (invoice_id, action, now_iso(), by, note))


def validate_upload(file_name: str, data: bytes) -> str:
    ext = Path(file_name or "").suffix.lower()
    if ext not in ALLOWED:
        raise InvoiceError(f"unsupported file type {ext or '(none)'}; allowed: {', '.join(ALLOWED)}")
    if len(data) == 0:
        raise InvoiceError("empty file")
    if len(data) > MAX_BYTES:
        raise InvoiceError("file too large (max 10 MB)")
    if not any(data.startswith(m) for m in MAGIC):
        raise InvoiceError("file content does not match its extension (magic-byte check failed)")
    return ALLOWED[ext]


def extract_candidates(file_name: str, mime: str, data: bytes) -> dict:
    """Returns {'status': ..., 'fields': {...}, 'notes': [...]}. PDF text layer only."""
    if mime != "application/pdf":
        return {"status": "unavailable", "fields": {},
                "notes": ["No OCR engine is installed on this server; enter values manually and "
                          "attach the document as evidence."]}
    try:
        import io
        import pdfplumber
    except ImportError:
        return {"status": "unavailable", "fields": {},
                "notes": ["pdfplumber is not installed; text extraction unavailable."]}
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            text = "\n".join((p.extract_text() or "") for p in pdf.pages[:5])
    except Exception as e:
        return {"status": "unavailable", "fields": {}, "notes": [f"PDF could not be read: {e}"]}
    if not text.strip():
        return {"status": "unavailable", "fields": {},
                "notes": ["PDF has no selectable text layer (likely a scan); manual entry required."]}
    fields: dict = {}
    m = re.search(r"(?:invoice\s*(?:no|number|#)|فاتورة\s*(?:رقم|no))\s*[:#]?\s*([A-Za-z0-9\-/]{2,30})",
                  text, re.I)
    if m:
        fields["invoice_number"] = {"value": m.group(1), "confidence": "medium", "source": "text layer"}
    dates = re.findall(r"\b(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b|\b(\d{1,2})[-/.](\d{1,2})[-/.](20\d{2})\b", text)
    if dates:
        d = dates[0]
        iso = (f"{d[0]}-{int(d[1]):02d}-{int(d[2]):02d}" if d[0]
               else f"{d[5]}-{int(d[4]):02d}-{int(d[3]):02d}")
        fields["invoice_date"] = {"value": iso, "confidence": "low", "source": "text layer (first date found)"}
    amt = re.search(r"(?:total|grand total|الإجمالي|المجموع)\D{0,18}([\d,]+(?:\.\d+)?)", text, re.I)
    if amt:
        fields["amount"] = {"value": amt.group(1).replace(",", ""), "confidence": "low",
                            "source": "text layer"}
    supplier = next((ln.strip() for ln in text.splitlines() if re.search(r"(company|co\.|ltd|شركة|مؤسسة)", ln, re.I)), None)
    if supplier and len(supplier) <= 80:
        fields["supplier"] = {"value": supplier, "confidence": "low", "source": "text layer"}
    return {"status": "text_extracted", "fields": fields,
            "notes": ["Extracted values are candidates from the PDF text layer - verify before saving."]}


def create_invoice(con, *, facility_id: int, company_id: int, invoice_name: str,
                   invoice_number: str | None = None, supplier: str | None = None,
                   invoice_date: str | None = None, period_year: int | None = None,
                   period_month: int | None = None, category_key: str | None = None,
                   quantity: str | None = None, unit: str | None = None,
                   amount: str | None = None, currency: str = "EGP", notes: str = "",
                   created_by: str, file: tuple[str, str, bytes] | None = None,
                   confirm_duplicate: bool = False) -> dict:
    if not (invoice_name or "").strip():
        raise InvoiceError("invoice_name is required")
    file_hash = None
    file_path = file_mime = None
    extraction = {"status": "none", "fields": {}, "notes": []}
    if file:
        name, mime, data = file
        mime = validate_upload(name, data)
        file_hash = hashlib.sha256(data).hexdigest()
        dup = con.execute("SELECT invoice_id FROM invoices WHERE facility_id=? AND file_hash=?",
                          (facility_id, file_hash)).fetchone()
        if dup and not confirm_duplicate:
            raise InvoiceDuplicate("This exact document is already registered for this facility",
                                   existing_id=dup["invoice_id"], kind="same_file")
    if supplier and invoice_number and invoice_date:
        soft = con.execute(
            "SELECT invoice_id FROM invoices WHERE facility_id=? AND supplier=? AND invoice_number=? "
            "AND invoice_date=? AND status!='void'", (facility_id, supplier, invoice_number, invoice_date)).fetchone()
        if soft and not confirm_duplicate:
            raise InvoiceDuplicate("A non-void invoice with the same supplier/number/date exists",
                                   existing_id=soft["invoice_id"], kind="same_metadata")
    if file:
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^\w.\-]+", "_", Path(file[0]).name)[:80]
        dest = UPLOAD_DIR / f"{file_hash[:16]}_{safe}"
        dest.write_bytes(file[2])
        file_path = str(dest)
        file_mime = mime
        extraction = extract_candidates(file[0], mime, file[2])
    with transaction(con):
        cur = con.execute(
            "INSERT INTO invoices(company_id,facility_id,invoice_name,invoice_number,supplier,invoice_date,"
            "period_year,period_month,category_key,quantity,unit,amount,currency,notes,file_name,file_hash,"
            "file_path,file_mime,extraction_status,extraction_json,status,created_by,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'draft',?,?)",
            (company_id, facility_id, invoice_name.strip(), invoice_number, supplier, invoice_date,
             period_year, period_month, category_key, quantity, unit, amount, currency, notes,
             file[0] if file else None, file_hash, file_path, file_mime,
             extraction["status"], json.dumps(extraction, ensure_ascii=False), created_by, now_iso()))
        invoice_id = cur.lastrowid
        _log(con, invoice_id, "created", created_by,
             f"file={file[0] if file else 'none'}, extraction={extraction['status']}")
    return {"invoice_id": invoice_id, "status": "draft", "file_hash": file_hash,
            "extraction": extraction}


def calculate_invoice(con, invoice_id: int, *, user: str, factor_id: str | None = None,
                      factor_version: int | None = None,
                      proxy_confirmed: bool = False, proxy_rationale: str = "",
                      ownership_control: str = "unknown", energy_purchased: str = "unknown",
                      value_chain_relation: str = "unknown") -> dict:
    """Calculate an invoice through the Core. Manual factor entry is NOT supported by design:
    the factor is selected from the library by activity/category/unit/year using the documented
    policy (exact year -> nearest year marked ESTIMATED -> IPCC default marked international).
    An explicit factor_id is accepted only as an authorised library override."""
    inv = con.execute("SELECT * FROM invoices WHERE invoice_id=?", (invoice_id,)).fetchone()
    if inv is None:
        raise LookupError("invoice not found")
    if inv["status"] == "void":
        raise InvoiceError("void invoices cannot be calculated")
    if inv["record_id"]:
        raise InvoiceError(f"invoice already linked to record #{inv['record_id']}")
    if not (inv["quantity"] and inv["unit"]):
        raise InvoiceError("quantity and unit are required before calculation")
    if not inv["category_key"]:
        raise InvoiceError("category_key is required before calculation")
    d = L.parse_date(inv["invoice_date"]) if inv["invoice_date"] else None
    if d is None:
        raise InvoiceError("invoice_date is required: the factor is selected by year")

    factor, selection_reason, nearest_ok, is_intl = None, "", False, False
    if factor_id:
        factor = FL.get_factor(con, factor_id, factor_version)
        if factor is None:
            raise LookupError("factor not found")
        selection_reason = f"Library factor selected explicitly ({factor.factor_id})"
    else:
        sg = FL.suggest(con, country="EG", category=inv["category_key"], year=d.year,
                        unit=inv["unit"], fuel=None)
        if sg.chosen is not None:
            factor = sg.chosen.factor
            selection_reason = sg.chosen.reason
        else:
            # exactly one national factor for the exact year (even unverified) -> use it, flagged
            national = [c for c in sg.candidates if c.is_national_for_activity]
            if len(national) == 1:
                factor = national[0].factor
                selection_reason = ("National factor auto-selected (status: "
                                    f"{factor.status.value}) - " + national[0].reason)
            else:
                near = FL.nearest_candidates(con, country="EG", category=inv["category_key"],
                                             unit=inv["unit"], year=d.year)
                if near:
                    factor = near[0].factor
                    nearest_ok = True
                    selection_reason = f"ESTIMATED (nearest year): {near[0].reason}"
                else:
                    raise InvoiceError(
                        "No emission factor is available for this invoice (category "
                        f"{inv['category_key']}, unit {inv['unit']}, year {d.year}). "
                        "Add/verify a factor first. " + sg.message)
    is_intl = factor.classification.value in ("global_default", "regional", "proxy") \
        or factor.country not in ("EG",)
    if is_intl:
        selection_reason += " | international default (auto-selected, marked)"
    res = L.add_record(
        con, activity_name=inv["invoice_name"], quantity=inv["quantity"], unit=inv["unit"],
        country_code="EG", activity_date=inv["invoice_date"], description=inv["notes"] or "",
        company_id=inv["company_id"], facility_id=inv["facility_id"],
        category_key=inv["category_key"], factor=factor, factor_selection_reason=selection_reason,
        proxy_confirmed=is_intl, ownership_control=ownership_control,
        energy_purchased=energy_purchased, value_chain_relation=value_chain_relation,
        notes=f"invoice #{inv['invoice_number'] or inv['invoice_id']}",
        origin=f"invoice:{invoice_id}", evidence_ref=inv["invoice_number"] or inv["file_name"],
        user=user, nearest_year_ok=nearest_ok)
    if res.get("duplicate"):
        raise InvoiceError(f"an identical activity record already exists (#{res['record_id']})")
    row = con.execute("SELECT * FROM activity_records WHERE record_id=?", (res["record_id"],)).fetchone()
    with transaction(con):
        con.execute("UPDATE invoices SET record_id=?, factor_id=?, factor_version=?, factor_value=?, "
                    "factor_source=?, status=?, updated_at=? WHERE invoice_id=?",
                    (res["record_id"], factor.factor_id, factor.version,
                     None if factor.total_co2e is None else str(factor.total_co2e),
                     factor.source_org, "calculated" if res["status"] == "calculated" else "needs_review",
                     now_iso(), invoice_id))
        con.execute("UPDATE activity_records SET invoice_id=? WHERE record_id=?",
                    (invoice_id, res["record_id"]))
        _log(con, invoice_id, "calculated", user,
             f"record={res['record_id']}, factor={factor.factor_id} v{factor.version}, status={res['status']}")
    return {"invoice_id": invoice_id, "record_id": res["record_id"], "status": res["status"],
            "kg_co2e": None if row is None else row["kg_co2e"],
            "t_co2e": None if row is None else row["t_co2e"],
            "factor": {"factor_id": factor.factor_id, "version": factor.version,
                       "value": None if factor.total_co2e is None else str(factor.total_co2e),
                       "unit": factor.denominator_unit, "source": factor.source_org,
                       "status": factor.status.value}}


def void_invoice(con, invoice_id: int, *, user: str, reason: str) -> None:
    inv = con.execute("SELECT status FROM invoices WHERE invoice_id=?", (invoice_id,)).fetchone()
    if inv is None:
        raise LookupError("invoice not found")
    if not reason.strip():
        raise InvoiceError("a void reason is required")
    with transaction(con):
        con.execute("UPDATE invoices SET status='void', notes=COALESCE(notes,'') || ? , updated_at=? "
                    "WHERE invoice_id=?", (f"\n[VOID] {reason.strip()}", now_iso(), invoice_id))
        _log(con, invoice_id, "voided", user, reason.strip())


def invoice_detail(con, invoice_id: int) -> dict | None:
    r = con.execute(
        "SELECT i.*, f.name AS facility_name, c.name AS company_name, a.kg_co2e, a.t_co2e, "
        "a.scope, a.calc_status, a.activity_date AS record_date FROM invoices i "
        "JOIN facilities f ON f.facility_id=i.facility_id JOIN companies c ON c.company_id=i.company_id "
        "LEFT JOIN activity_records a ON a.record_id=i.record_id WHERE i.invoice_id=?",
        (invoice_id,)).fetchone()
    return None if r is None else _jsonable(dict(r))


def list_invoices(con, *, company_id=None, facility_id=None, search=None, year=None, month=None,
                  status=None, category=None, limit=200) -> list[dict]:
    q = ("SELECT i.*, f.name AS facility_name, a.kg_co2e, a.scope FROM invoices i "
         "JOIN facilities f ON f.facility_id=i.facility_id "
         "LEFT JOIN activity_records a ON a.record_id=i.record_id WHERE 1=1")
    p: list = []
    for col, val in (("i.company_id", company_id), ("i.facility_id", facility_id),
                     ("i.period_year", year), ("i.period_month", month),
                     ("i.status", status), ("i.category_key", category)):
        if val not in (None, ""):
            q += f" AND {col}=?"; p.append(val)
    if search:
        q += (" AND (i.invoice_name LIKE ? OR i.invoice_number LIKE ? OR i.supplier LIKE ?)")
        p += [f"%{search}%"] * 3
    rows = con.execute(q + " ORDER BY i.invoice_id DESC LIMIT ?", (*p, limit)).fetchall()
    return [_jsonable(dict(r)) for r in rows]


def audit(con, invoice_id: int) -> list[dict]:
    return [_jsonable(dict(r)) for r in con.execute(
        "SELECT * FROM invoice_audit_log WHERE invoice_id=? ORDER BY id", (invoice_id,)).fetchall()]


def _jsonable(d: dict) -> dict:
    from decimal import Decimal
    out = {}
    for k, v in d.items():
        out[k] = format(v, "f") if isinstance(v, Decimal) else v
    return out
