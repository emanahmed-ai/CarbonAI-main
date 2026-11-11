"""Regenerate the Egypt coverage matrix (JSON for seeding + CSV deliverable).

    python scripts/build_egypt_seed.py

Writes:
    database/seed/egypt_coverage_2006_2026.json
    EGYPT_ANNUAL_COVERAGE_2006_2026.csv   (project root, deliverable)
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.egypt_seed import COVERAGE_PATH, build_coverage, load_seed  # noqa: E402


def main() -> int:
    rows = build_coverage()
    COVERAGE_PATH.write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    out = ROOT / "EGYPT_ANNUAL_COVERAGE_2006_2026.csv"
    with open(out, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["country_code", "year", "sector", "activity", "gas",
                                           "coverage_status", "available_source", "missing_reason",
                                           "review_date", "reviewer"])
        w.writeheader()
        w.writerows(rows)
    doc = load_seed()
    print(f"factors in seed: {len(doc['factors'])} (sources: {len(doc['sources'])})")
    print(f"coverage rows: {len(rows)} across {len(set(r['year'] for r in rows))} years")
    counts = Counter(r["coverage_status"] for r in rows)
    print("coverage status counts:", dict(counts))
    print("wrote:", COVERAGE_PATH)
    print("wrote:", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
