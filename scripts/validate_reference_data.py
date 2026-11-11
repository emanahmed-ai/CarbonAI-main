"""Check every seeded NZ value really appears in the source PDF page.

Usage: python scripts/validate_reference_data.py <NZ-guide.pdf>
Exit code 1 on any mismatch. Also checks the file checksum recorded in the seed.
"""
import hashlib, json, sys
from pathlib import Path

import pdfplumber

pdf_path = Path(sys.argv[1])
seed = json.loads((Path(__file__).resolve().parent.parent /
                   "tests/fixtures/nz_mfe_2023_factors.json").read_text("utf-8"))
bad = 0
if hashlib.sha256(pdf_path.read_bytes()).hexdigest() != seed["source"]["file_sha256"]:
    print("CHECKSUM MISMATCH: seed was built from a different file"); bad += 1
with pdfplumber.open(pdf_path) as pdf:
    for r in seed["rows"]:
        lines = (pdf.pages[r["pdf_page"] - 1].extract_text() or "").splitlines()
        want = [r["total"], r["co2"], r["ch4"], r["n2o"]]
        key = str(r["year"]) if r["category"] == "electricity" else None
        ok = False
        for ln in lines:
            toks = ln.replace("%", "").split()
            if all(w in toks for w in want) and (key is None or toks[:1] == [key]) and r["unit"] in toks:
                ok = True; break
        if not ok:
            bad += 1; print("NOT FOUND ON PAGE:", r["key"], want)
print(f"checked {len(seed['rows'])} rows, mismatches={bad}")
sys.exit(1 if bad else 0)
