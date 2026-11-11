"""In-memory background jobs for large imports.

The upload endpoint returns a job id immediately; a daemon thread reads the file, validates it
through the existing importer pipeline and commits in one transaction, updating progress.
The frontend polls GET /api/imports/jobs/{id} (never blocks a request).

Scope notes:
* jobs live in this process (the app runs one uvicorn worker; documented in DECISIONS.md);
* jobs expire from memory after 2 hours;
* a duplicate file hash while a job is queued/running returns the existing job (no double import);
* every job uses its own SQLite connection in its own thread.
"""
from __future__ import annotations

import json
import tempfile
import threading
import time
import uuid
from pathlib import Path

from db.connection import connect
from services import column_mapper as CM
from services import importer as I

_JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()
_TTL_SECONDS = 2 * 60 * 60


def _prune() -> None:
    now = time.time()
    with _LOCK:
        for k, j in list(_JOBS.items()):
            if j.get("finished_at") and now - j["finished_at"] > _TTL_SECONDS:
                _JOBS.pop(k, None)


def find_running_by_hash(file_hash: str, facility_id: int | None) -> str | None:
    with _LOCK:
        for jid, j in _JOBS.items():
            if j["file_hash"] == file_hash and j["facility_id"] == facility_id and \
                    j["status"] in ("queued", "running"):
                return jid
    return None


def get(job_id: str) -> dict | None:
    with _LOCK:
        j = _JOBS.get(job_id)
        return dict(j) if j else None


def _update(job_id: str, **kw) -> None:
    with _LOCK:
        if job_id in _JOBS:
            _JOBS[job_id].update(kw)


def _run(job_id: str, file_name: str, data: bytes, mapping: dict, options: dict) -> None:
    con = connect()
    tmp_path = None
    try:
        _update(job_id, status="running", phase="validating", started_at=time.time())
        df = I.read_upload(file_name, data, sheet_name=options.get("sheet"))
        renamed, problems = CM.apply_mapping(df, mapping)
        if problems:
            _update(job_id, status="error", phase="validating",
                    error="; ".join(problems), finished_at=time.time())
            return
        pv = I.preview(renamed, default_date=options.get("default_date"),
                       default_country=options.get("default_country"))
        if options.get("facility_override"):
            for a in pv.accepted:
                a["company"] = options.get("company_name") or ""
                a["facility"] = options["facility_override"]
        total = len(pv.accepted)
        _update(job_id, total=total, rejected=len(pv.rejected), phase="committing")
        if pv.missing_columns:
            _update(job_id, status="error", phase="validating",
                    error="missing required columns: " + ", ".join(pv.missing_columns),
                    finished_at=time.time())
            return

        def progress(done, total_, added, failed):
            _update(job_id, done=done, processed=done, added=added, failed=failed,
                    percent=round(100 * done / max(total_, 1), 1))

        res = I.commit(con, pv, file_name=file_name,
                       keep_duplicates=bool(options.get("keep_duplicates")), user=options.get("user"),
                       progress=progress)
        con.execute("UPDATE import_batches SET file_hash=? WHERE batch_id=?",
                    (options.get("file_hash"), res["batch_id"]))
        con.commit()
        _update(job_id, status="done", phase="done", percent=100.0, result=res,
                finished_at=time.time())
    except Exception as exc:  # surfaced to the client, never swallowed
        _update(job_id, status="error", phase="error", error=str(exc), finished_at=time.time())
    finally:
        con.close()
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)


def start_import_job(*, file_name: str, data: bytes, mapping: dict, options: dict,
                     file_hash: str, facility_id: int | None) -> str:
    _prune()
    existing = find_running_by_hash(file_hash, facility_id)
    if existing:
        return existing
    job_id = uuid.uuid4().hex[:16]
    with _LOCK:
        _JOBS[job_id] = {
            "job_id": job_id, "status": "queued", "phase": "queued", "file_name": file_name,
            "file_hash": file_hash, "facility_id": facility_id, "created_at": time.time(),
            "started_at": None, "finished_at": None, "total": 0, "done": 0, "added": 0,
            "failed": 0, "rejected": 0, "percent": 0.0, "error": None, "result": None,
        }
    t = threading.Thread(target=_run, args=(job_id, file_name, data, mapping, options), daemon=True)
    t.start()
    return job_id
