"""Factory-level backup (ZIP of JSON) and factory reset (operational data only).

Safety rules:
* backup is read-only and scoped to the caller's authorized company/facility;
* factory reset requires the caller's current password (verified by the router), takes an
  automatic database backup BEFORE deleting, and writes an audit entry to update_log;
* reset deletes ONLY operational rows of the target facility (records, invoices+audit, cooling,
  submissions+audit, plans, targets). Users, facilities, companies, emission factors, references
  and settings are never touched;
* import batch history is preserved as an audit trail (documented limitation).
"""
from __future__ import annotations

import io
import json
import zipfile
from decimal import Decimal

from db.connection import backup_file, db_path, now_iso, transaction


def _rows(con, sql: str, params=()) -> list[dict]:
    out = []
    for r in con.execute(sql, params).fetchall():
        d = {}
        for k in r.keys():
            v = r[k]
            d[k] = format(v, "f") if isinstance(v, Decimal) else v
        out.append(d)
    return out


def export_payload(con, *, company_id: int | None, facility_id: int | None) -> dict:
    """Operational data for one facility (or the whole company when facility_id is None)."""
    if facility_id is not None:
        facility_where, fparams = "facility_id=?", (facility_id,)
        fac = con.execute("SELECT f.*, c.name AS company_name FROM facilities f "
                          "JOIN companies c ON c.company_id=f.company_id WHERE f.facility_id=?",
                          (facility_id,)).fetchone()
        if fac is None:
            raise LookupError("facility not found")
        facilities = [_rows(con, "SELECT * FROM facilities WHERE facility_id=?", (facility_id,))]
    elif company_id is not None:
        facility_where, fparams = "facility_id IN (SELECT facility_id FROM facilities WHERE company_id=?)", (company_id,)
        fac = con.execute("SELECT * FROM companies WHERE company_id=?", (company_id,)).fetchone()
        if fac is None:
            raise LookupError("company not found")
        facilities = [_rows(con, "SELECT * FROM facilities WHERE company_id=?", (company_id,))]
    else:
        raise ValueError("company_id or facility_id is required for a backup")
    inv_where = facility_where.replace("facility_id", "i.facility_id")
    payload = {
        "format": "carbonai.factory-backup/1",
        "generated_at": now_iso(),
        "company": _rows(con, "SELECT * FROM companies WHERE company_id=?", (fac[0]["company_id"] if isinstance(fac, list) else fac["company_id"],)),
        "facilities": facilities,
        "activity_records": _rows(con, f"SELECT * FROM activity_records WHERE {facility_where}", fparams),
        "invoices": _rows(con, f"SELECT * FROM invoices WHERE {facility_where}", fparams),
        "invoice_audit": _rows(con, f"SELECT a.* FROM invoice_audit_log a JOIN invoices i ON i.invoice_id=a.invoice_id "
                                    f"WHERE {inv_where}", fparams),
        "cooling_equipment": _rows(con, f"SELECT * FROM cooling_equipment WHERE {facility_where}", fparams),
        "refrigerant_service_records": _rows(con, f"SELECT * FROM refrigerant_service_records WHERE {facility_where}", fparams),
        "submissions": _rows(con, f"SELECT * FROM report_submissions WHERE {facility_where}", fparams),
        "submission_audit": _rows(con, f"SELECT l.* FROM submission_audit_log l JOIN report_submissions s "
                                       f"ON s.submission_id=l.submission_id WHERE {facility_where.replace('facility_id', 's.facility_id')}", fparams),
        "reduction_plans": _rows(con, f"SELECT * FROM reduction_plans WHERE target_facility_id=?", (facility_id,)) if facility_id else [],
        "reduction_targets": _rows(con, f"SELECT * FROM reduction_targets WHERE facility_id=?", (facility_id,)) if facility_id else [],
    }
    return payload


def export_zip(con, *, company_id: int | None, facility_id: int | None) -> bytes:
    payload = export_payload(con, company_id=company_id, facility_id=facility_id)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("data.json", json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        # invoice attachments (original documents) when present on disk
        added = 0
        for inv in payload.get("invoices", []):
            path = inv.get("file_path")
            if path:
                from pathlib import Path as _P
                p = _P(path)
                if p.is_file():
                    z.write(str(p), arcname=f"attachments/{p.name}")
                    added += 1
        z.writestr("README.txt", "CarbonAI factory backup.\n"
                    "format: carbonai.factory-backup/1\n"
                    "Contains operational data for the selected factory only; emission factors, "
                    "references, users and settings are global and intentionally excluded.\n"
                    f"Invoice documents included: {added}.\n")
    return buf.getvalue()


def factory_reset(con, *, facility_id: int | None, company_id: int | None, user: str,
                  reason: str) -> dict:
    """Delete operational data for the facility (or company when facility_id is None)."""
    if facility_id is not None:
        fac = con.execute("SELECT facility_id FROM facilities WHERE facility_id=?", (facility_id,)).fetchone()
        if fac is None:
            raise LookupError("facility not found")
        facilities = [facility_id]
    elif company_id is not None:
        facilities = [r["facility_id"] for r in
                      con.execute("SELECT facility_id FROM facilities WHERE company_id=?", (company_id,)).fetchall()]
        if not facilities:
            raise ValueError("company has no facilities to reset")
    else:
        raise ValueError("facility_id or company_id is required")
    backup = backup_file(db_path(), label="pre_factory_reset")
    marks = ",".join("?" for _ in facilities)
    counts: dict[str, int] = {}
    with transaction(con):
        counts["scope_audit"] = con.execute(
            f"DELETE FROM scope_audit_log WHERE record_id IN (SELECT record_id FROM activity_records "
            f"WHERE facility_id IN ({marks}))", facilities).rowcount
        counts["records"] = con.execute(
            f"DELETE FROM activity_records WHERE facility_id IN ({marks})", facilities).rowcount
        counts["invoice_audit"] = con.execute(
            f"DELETE FROM invoice_audit_log WHERE invoice_id IN (SELECT invoice_id FROM invoices "
            f"WHERE facility_id IN ({marks}))", facilities).rowcount
        counts["invoices"] = con.execute(
            f"DELETE FROM invoices WHERE facility_id IN ({marks})", facilities).rowcount
        counts["service_records"] = con.execute(
            f"DELETE FROM refrigerant_service_records WHERE facility_id IN ({marks})", facilities).rowcount
        counts["cooling_equipment"] = con.execute(
            f"DELETE FROM cooling_equipment WHERE facility_id IN ({marks})", facilities).rowcount
        counts["submission_audit"] = con.execute(
            f"DELETE FROM submission_audit_log WHERE submission_id IN (SELECT submission_id "
            f"FROM report_submissions WHERE facility_id IN ({marks}))", facilities).rowcount
        counts["submissions"] = con.execute(
            f"DELETE FROM report_submissions WHERE facility_id IN ({marks})", facilities).rowcount
        counts["plans"] = con.execute(
            f"DELETE FROM reduction_plans WHERE target_facility_id IN ({marks})", facilities).rowcount
        counts["targets"] = con.execute(
            f"DELETE FROM reduction_targets WHERE facility_id IN ({marks})", facilities).rowcount
        con.execute("INSERT INTO update_log(at,source,outcome,detail) VALUES (?,?,?,?)",
                    (now_iso(), "factory_reset", "executed",
                     json.dumps({"user": user, "facilities": facilities, "reason": reason,
                                 "deleted": counts, "backup": str(backup)}, ensure_ascii=False)))
    return {"ok": True, "facilities": facilities, "deleted": counts,
            "backup": str(backup), "note": "Users, factories, global factors and references were preserved."}
