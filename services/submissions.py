"""Report submission workflow between factories and the head office.

Flow: a factory manager snapshots a period of their OWN ledger into a submission row
(status='submitted') -> head office reviews -> approves or rejects with a note.

Guarantees:
* A submission is an IMMUTABLE snapshot: later edits to records never change an approved number.
  Consolidated reporting can therefore join on approved submissions without re-deriving them.
* One ACTIVE submission (submitted or approved) per facility/period, enforced by a partial
  unique index in the schema; resubmission is possible only after a rejection.
* The snapshot stores per-record fingerprints + amounts; totals only ever include rows whose
  calc_status='calculated' (same rule as ledger.summarize, so numbers match the dashboards).
"""
from __future__ import annotations

import json
import sqlite3
from decimal import Decimal

from db.connection import now_iso, transaction
from services import ledger as L

ACTIVE_STATUSES = ("submitted", "approved")


class SubmissionError(ValueError):
    pass


def _snap_row(r) -> dict:
    return {
        "record_id": r["record_id"], "fingerprint": r["fingerprint"],
        "activity_name": r["activity_name"], "scope": r["scope"],
        "scope_subcategory": r["scope_subcategory"], "category_key": r["category_key"],
        "activity_date": r["activity_date"], "quantity": r["quantity"], "unit": r["unit"],
        "kg_co2e": r["kg_co2e"], "t_co2e": r["t_co2e"],
        "calc_status": r["calc_status"], "factor_source": r["factor_source"],
        "factor_verification": r["factor_verification"], "data_verification": r["data_verification"],
    }


def create_submission(con: sqlite3.Connection, *, facility_id: int, period_year: int,
                      period_month: int | None, submitted_by: str, title: str = "",
                      company_id: int | None = None, allow_supersede: bool = False) -> dict:
    """Snapshot the facility's ledger for the period into a new submission. Raises SubmissionError
    when an active submission already exists for the same facility/period (unless allow_supersede,
    which withdraws the previous 'submitted' one first - an approved submission is never replaced)."""
    if not (1 <= period_month <= 12 if period_month else True):
        raise SubmissionError("period_month must be 1-12 or empty (full year)")
    fac = con.execute("SELECT f.*, c.name AS company_name FROM facilities f "
                      "JOIN companies c ON c.company_id=f.company_id WHERE f.facility_id=?",
                      (facility_id,)).fetchone()
    if fac is None:
        raise SubmissionError("facility not found")

    prev = con.execute(
        "SELECT submission_id, status FROM report_submissions WHERE facility_id=? AND period_year=? "
        "AND IFNULL(period_month,0)=IFNULL(?,0) AND status IN ('submitted','approved')",
        (facility_id, period_year, period_month)).fetchone()
    if prev is not None:
        if prev["status"] == "approved" or not allow_supersede:
            raise SubmissionError(
                f"An active submission (#{prev['submission_id']}, {prev['status']}) already exists for "
                f"this facility/period. Withdrawal or review is required first.")
        with transaction(con):
            con.execute("UPDATE report_submissions SET status='withdrawn' WHERE submission_id=?",
                        (prev["submission_id"],))
            con.execute("INSERT INTO submission_audit_log(submission_id,action,at,by,note) "
                        "VALUES (?, 'withdrawn', ?, ?, 'superseded by a new submission')",
                        (prev["submission_id"], now_iso(), submitted_by))

    df = L.fetch_records(con, facility_id=facility_id, year=period_year, month=period_month)
    s = L.summarize(df, year=period_year)
    records = [_snap_row(r) for _, r in df.iterrows()]
    with transaction(con):
        cur = con.execute(
            "INSERT INTO report_submissions(company_id,facility_id,period_year,period_month,title,status,"
            "total_kg_co2e,by_scope_json,monthly_json,records_count,calculated_count,needs_review_count,"
            "verified_factor_pct,records_json,submitted_by,submitted_at) "
            "VALUES (?,?,?,?,?, 'submitted', ?,?,?,?,?,?,?,?,?,?)",
            (fac["company_id"], facility_id, period_year, period_month,
             (title or f"{fac['name']} - {period_year}" + (f"-{period_month:02d}" if period_month else "")).strip(),
             str(s["total_kg"]), json.dumps({k: str(v) for k, v in s["by_scope_kg"].items()}),
             json.dumps({f"{y}-{m:02d}": str(v) for (y, m), v in s["monthly_kg"].items()}),
             s["records"], s["calculated"], s["needs_review"],
             s["verified_pct"], json.dumps(records), submitted_by, now_iso()))
        sid = cur.lastrowid
        con.execute("INSERT INTO submission_audit_log(submission_id,action,at,by,note) "
                    "VALUES (?, 'submitted', ?, ?, ?)", (sid, now_iso(), submitted_by,
                                                         f"records={s['records']}, total_kg={s['total_kg']}"))
    return {"submission_id": sid, "facility": fac["name"], "company": fac["company_name"],
            "records": s["records"], "calculated": s["calculated"],
            "needs_review": s["needs_review"], "total_kg_co2e": str(s["total_kg"]),
            "total_t_co2e": str(s["total_t"]), "status": "submitted"}


def review_submission(con: sqlite3.Connection, submission_id: int, *, decision: str,
                      reviewer: str, note: str = "") -> dict:
    """decision: 'approve' | 'reject'. Reviewer identity is mandatory; note recommended on reject."""
    if decision not in ("approve", "reject"):
        raise SubmissionError("decision must be approve or reject")
    if not reviewer or not reviewer.strip():
        raise SubmissionError("reviewer is required")
    with transaction(con):
        r = con.execute("SELECT * FROM report_submissions WHERE submission_id=?", (submission_id,)).fetchone()
        if r is None:
            raise LookupError("submission not found")
        if r["status"] != "submitted":
            raise SubmissionError(f"submission is already {r['status']}; only submitted reports can be reviewed")
        new_status = "approved" if decision == "approve" else "rejected"
        if decision == "reject" and not (note or "").strip():
            raise SubmissionError("a rejection requires a note explaining why")
        try:
            con.execute("UPDATE report_submissions SET status=?, reviewed_by=?, reviewed_at=?, review_note=? "
                        "WHERE submission_id=?", (new_status, reviewer.strip(), now_iso(),
                                                  (note or "").strip(), submission_id))
        except sqlite3.IntegrityError as e:
            raise SubmissionError("another approved submission already exists for this facility/period") from e
        con.execute("INSERT INTO submission_audit_log(submission_id,action,at,by,note) VALUES (?,?,?,?,?)",
                    (submission_id, new_status, now_iso(), reviewer.strip(), (note or "").strip()))
    return {"submission_id": submission_id, "status": new_status}


def list_submissions(con, *, company_id: int | None = None, facility_id: int | None = None,
                     status: str | None = None, year: int | None = None) -> list[dict]:
    q = ("SELECT s.*, f.name AS facility_name, c.name AS company_name FROM report_submissions s "
         "JOIN facilities f ON f.facility_id=s.facility_id JOIN companies c ON c.company_id=s.company_id WHERE 1=1")
    p: list = []
    for col, val in (("s.company_id", company_id), ("s.facility_id", facility_id),
                     ("s.status", status), ("s.period_year", year)):
        if val not in (None, ""):
            q += f" AND {col}=?"; p.append(val)
    rows = con.execute(q + " ORDER BY s.submitted_at DESC, s.submission_id DESC", p).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["by_scope"] = json.loads(r["by_scope_json"] or "{}")
        d["monthly"] = json.loads(r["monthly_json"] or "{}")
        d["records"] = json.loads(r["records_json"] or "[]")
        d.pop("records_json", None)
        out.append(d)
    return out


def submission_detail(con, submission_id: int) -> dict | None:
    rows = list_submissions(con)
    for r in rows:
        if r["submission_id"] == submission_id:
            return r
    return None


def consolidated(con, *, company_id: int | None = None, year: int | None = None) -> dict:
    """Head-office consolidated view from APPROVED submissions only, plus the live ledger totals
    for comparison. Duplicates are impossible by construction (one approved row per facility/period)."""
    q = ("SELECT s.*, f.name AS facility_name FROM report_submissions s "
         "JOIN facilities f ON f.facility_id=s.facility_id WHERE s.status='approved'")
    p: list = []
    if company_id is not None:
        q += " AND s.company_id=?"; p.append(company_id)
    if year is not None:
        q += " AND s.period_year=?"; p.append(year)
    rows = con.execute(q + " ORDER BY s.period_year, IFNULL(s.period_month,0), f.name", p).fetchall()

    per_facility: dict[int, dict] = {}
    monthly: dict[str, Decimal] = {}
    scopes = {"Scope 1": Decimal(0), "Scope 2": Decimal(0), "Scope 3": Decimal(0)}
    total = Decimal(0)
    for r in rows:
        kg = Decimal(r["total_kg_co2e"] or "0")
        agg = per_facility.setdefault(r["facility_id"], {
            "facility_id": r["facility_id"], "facility_name": r["facility_name"],
            "total_kg_co2e": Decimal(0), "submissions": 0, "last_approved_at": None})
        agg["total_kg_co2e"] += kg
        agg["submissions"] += 1
        agg["last_approved_at"] = max(agg["last_approved_at"] or "", r["reviewed_at"] or "")
        total += kg
        for k, v in json.loads(r["by_scope_json"] or "{}").items():
            if k in scopes:
                scopes[k] += Decimal(v)
        for ym, v in json.loads(r["monthly_json"] or "{}").items():
            monthly[ym] = monthly.get(ym, Decimal(0)) + Decimal(v)
    return {"year": year, "total_kg_co2e": str(total), "total_t_co2e": str(total / 1000),
            "by_scope_kg": {k: str(v) for k, v in scopes.items()},
            "monthly_kg": {k: str(v) for k, v in sorted(monthly.items())},
            "facilities": [{**a, "total_kg_co2e": str(a["total_kg_co2e"])} for a in
                           sorted(per_facility.values(), key=lambda x: -x["total_kg_co2e"])],
            "approved_submissions": len(rows)}
