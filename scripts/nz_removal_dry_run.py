"""Gated removal of the legacy New Zealand dataset (client specification §2/§15).

SAFE BY DEFAULT: without --confirm nothing is deleted.

    python scripts/nz_removal_dry_run.py                 # backup + dry-run report only
    python scripts/nz_removal_dry_run.py --execute --confirm REMOVE-LEGACY-NZ

What --execute deletes (and ONLY this):
    * emission_factors rows with country_code='NZ'   (library entries; current versions)
    * the NZ seed source row (sources.reference_id='NZ-MFE-2023-ME1764')
What is NEVER touched:
    * activity_records and their factor_snapshot_json / kg_co2e (historical calculations)
    * report_submissions snapshots, audit logs, settings
Rollback: restore the automatic backup taken before execution
    python scripts/db_admin.py restore backups/<file>.db
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from db.connection import backup_file, connect, db_path, now_iso  # noqa: E402

CONFIRM_TOKEN = "REMOVE-LEGACY-NZ"


def collect(con) -> dict:
    factors = con.execute(
        "SELECT factor_id, version, verification_status FROM emission_factors "
        "WHERE country_code='NZ' ORDER BY factor_id, version").fetchall()
    snapshots = con.execute(
        "SELECT COUNT(*) c FROM activity_records WHERE factor_snapshot_json LIKE '%\"country\": \"NZ\"%' "
        "OR country_code='NZ'").fetchone()["c"]
    records = con.execute("SELECT COUNT(*) c FROM activity_records WHERE country_code='NZ'").fetchone()["c"]
    source = con.execute("SELECT reference_id FROM sources WHERE reference_id='NZ-MFE-2023-ME1764'").fetchone()
    return {"factors": factors, "records_nz": records, "records_with_nz_snapshot": snapshots,
            "source_row": source is not None}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true", help="perform the deletion (requires --confirm)")
    ap.add_argument("--confirm", default="", help=f"must equal {CONFIRM_TOKEN}")
    args = ap.parse_args()

    con = connect()
    try:
        info = collect(con)
        print(f"Database: {db_path()}")
        print(f"NZ factor rows (all versions): {len(info['factors'])}")
        for f in info["factors"]:
            print(f"  - {f['factor_id']} v{f['version']} [{f['verification_status']}]")
        print(f"NZ source row present: {info['source_row']}")
        print(f"Activity records with country_code='NZ': {info['records_nz']} "
              f"(historical - will be PRESERVED untouched)")
        print(f"Records whose factor snapshot references NZ: {info['records_with_nz_snapshot']} "
              f"(snapshots - will be PRESERVED untouched)")

        if not args.execute:
            backup = backup_file(db_path(), label="pre_nz_removal_dryrun")
            print(f"\nDRY RUN ONLY. Automatic backup: {backup}")
            print("No rows were changed. To delete the legacy library rows run:")
            print(f"  python scripts/nz_removal_dry_run.py --execute --confirm {CONFIRM_TOKEN}")
            return 0

        if args.confirm != CONFIRM_TOKEN:
            print(f"\nREFUSED: --execute requires --confirm {CONFIRM_TOKEN}")
            return 2
        backup = backup_file(db_path(), label="pre_nz_removal")
        print(f"\nBackup before deletion: {backup}")
        with con:
            n1 = con.execute("DELETE FROM emission_factors WHERE country_code='NZ'").rowcount
            n2 = con.execute("DELETE FROM sources WHERE reference_id='NZ-MFE-2023-ME1764'").rowcount
            con.execute(
                "INSERT INTO update_log(at,source,outcome,detail) VALUES (?,?,?,?)",
                (now_iso(), "nz_removal",
                 "executed", f"deleted {n1} emission_factors rows and {n2} source row; "
                             f"historical records/snapshots untouched (backup: {backup})"))
        after = collect(con)
        print(f"Deleted factor rows: {n1}; deleted sources: {n2}")
        print(f"Remaining NZ factors: {len(after['factors'])}")
        print(f"Historical NZ records still present (expected): {after['records_nz']}")
        print("Rollback if needed:", f"python scripts/db_admin.py restore \"{backup}\"")
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
