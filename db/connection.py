"""SQLite persistence (stdlib only). Safe to call repeatedly: never drops or resets data.

Location: env CARBONAI_DB_PATH, else <project>/data/carbonai.db.
Every schema change is additive (CREATE ... IF NOT EXISTS / ADD COLUMN) and is
applied inside a transaction after an automatic file backup of an existing DB.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def db_path() -> Path:
    return Path(os.environ.get("CARBONAI_DB_PATH", ROOT / "data" / "carbonai.db"))


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    p = Path(path) if path else db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False: the REST API (FastAPI) creates the connection in a dependency and
    # uses it in the endpoint's worker thread. Every request gets its OWN connection and endpoints
    # run sequentially within a request, so there is never concurrent sharing of one connection.
    con = sqlite3.connect(str(p), timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


@contextmanager
def transaction(con: sqlite3.Connection):
    """All-or-nothing block. Rolls back on any exception and re-raises.

    Nesting-aware: when the connection is already inside a transaction (e.g. a bulk import
    wrapping many ledger writes), this is a no-op so the caller's outer transaction owns the
    commit. Row-level isolation inside a bulk import is achieved with SAVEPOINTs by the caller.
    """
    if con.in_transaction:
        yield con
        return
    try:
        con.execute("BEGIN")
        yield con
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise


def backup_file(path: Path | str | None = None, label: str = "manual") -> Path | None:
    """Consistent copy of the DB using SQLite's online backup API."""
    p = Path(path) if path else db_path()
    if not p.exists():
        return None
    out_dir = p.parent.parent / "backups" if p.parent.name == "data" else p.parent / "backups"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    dest = out_dir / f"{p.stem}_{label}_{stamp}.db"
    src = sqlite3.connect(str(p))
    dst = sqlite3.connect(str(dest))
    try:
        src.backup(dst)
    finally:
        dst.close(); src.close()
    return dest


def restore_file(backup: Path | str, path: Path | str | None = None) -> Path:
    """Restore a backup. The current DB is first copied aside, never overwritten blindly."""
    p = Path(path) if path else db_path()
    if p.exists():
        backup_file(p, label="pre_restore")
    shutil.copyfile(str(backup), str(p))
    return p


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
