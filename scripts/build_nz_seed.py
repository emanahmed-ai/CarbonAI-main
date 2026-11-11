"""Build database/seed/nz_mfe_2023_factors.json from the supplied NZ PDF.

Parses Table 3 (stationary combustion) and Table 9 (grid electricity) straight
from the PDF text layer so values are not hand-typed. Review the output before
import; rows land as UNVERIFIED -> a human reviewer promotes them.

Usage: python scripts/build_nz_seed.py <path-to-NZ-guide.pdf>
"""
import hashlib, json, re, sys
from pathlib import Path

import pdfplumber

PDF = Path(sys.argv[1])
OUT = Path(__file__).resolve().parent.parent / "database" / "seed" / "nz_mfe_2023_factors.json"
TITLE = ("Measuring emissions: A guide for organisations: 2023 detailed guide "
         "(ME 1764)")
NUM = r"[0-9]+(?:\.[0-9]+)?"


def page_text(pdf, n):  # n = 1-based PDF page
    return pdf.pages[n - 1].extract_text() or ""


def find_page(pdf, needle):
    for i, p in enumerate(pdf.pages, 1):
        t = p.extract_text() or ""
        if needle in t and "Table" in t:
            yield i, t


rows, pages = [], {}
with pdfplumber.open(PDF) as pdf:
    # ---- Table 9
    for i, t in find_page(pdf, "Emission factor for purchased grid-average electricity \u2013 annual average"):
        if "kg CO\u2082-e/unit" not in t:
            continue  # skip the list-of-tables page
        pages["table9"] = i
        for m in re.finditer(rf"^(20(?:1\d|2[0-2]))\s+kWh\s+({NUM})\s+({NUM})\s+({NUM})\s+({NUM})\s*$", t, re.M):
            y, tot, co2, ch4, n2o = m.groups()
            rows.append(dict(
                key=f"NZ-ELEC-GRID-{y}", category="electricity", activity="grid_average",
                use=None, unit="kWh", year=int(y), total=tot, co2=co2, ch4=ch4, n2o=n2o,
                uncertainty=None, locator="Table 9", pdf_page=i,
                boundary="Excludes transmission and distribution losses (see Table 12)"))
        break
    # ---- Table 3
    for i, t in find_page(pdf, "Emission factors for the stationary combustion of fuels"):
        if "Residential use" not in t or "Industrial use" not in t:
            continue
        pages["table3"] = i
        use, last_fuel = None, None
        for line in t.splitlines():
            s = line.strip()
            if s in ("Residential use", "Commercial use", "Industrial use"):
                use = s.split()[0].lower(); continue
            m = re.match(rf"^(Coal \u2013 \w[\w-]*|Diesel|LPG|Heavy fuel oil|Light fuel oil|Natural gas)\s+(kg|litre|kWh|GJ)\s+({NUM})\s+({NUM})\s+({NUM})\s+({NUM})\s+({NUM})%$", s)
            m2 = re.match(rf"^(kWh|GJ)\s+({NUM})\s+({NUM})\s+({NUM})\s+({NUM})\s+({NUM})%$", s)
            if m and use:
                name, unit, tot, co2, ch4, n2o, unc = m.groups(); last_fuel = name
            elif m2 and use and last_fuel == "Natural gas":
                name = last_fuel; unit, tot, co2, ch4, n2o, unc = m2.groups()
            else:
                continue
            slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
            rows.append(dict(
                key=f"NZ-FUEL-{use}-{slug}-{unit}".upper(), category="stationary_fuel",
                activity=slug, use=use, unit=unit, year=2021, total=tot, co2=co2,
                ch4=ch4, n2o=n2o, uncertainty=unc, locator="Table 3", pdf_page=i,
                boundary=f"{use} use; combustion only"))
        break

sha = hashlib.sha256(PDF.read_bytes()).hexdigest()
doc = {
    "source": {
        "org": "Ministry for the Environment (New Zealand)", "title": TITLE,
        "published": "2023-07", "country": "NZ", "publisher_site": "environment.govt.nz",
        "direct_url": None,
        "direct_url_note": "Direct download URL not present in the supplied file; not invented.",
        "file_sha256": sha, "licence_note": "Crown copyright New Zealand 2023 "
        "(per the PDF). Reuse terms not stated in the PDF; confirm before redistribution.",
        "gwp_basis": "AR5-GWP100 (guide Table 1; CH4 excludes fossil methane)",
        "pdf_pages": pages,
        "year_note": "Table 3 data are mainly 2021 per guide section 1.1; seeded as year 2021 "
                     "for review - confirm validity period against the guide's workbook.",
    },
    "rows": rows,
}
OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=False))
print(f"wrote {OUT} rows={len(rows)} pages={pages} sha256={sha[:12]}...")
