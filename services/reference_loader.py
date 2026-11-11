"""Load seed JSON into EmissionFactor objects. Rows load as UNVERIFIED unless a
named reviewer promotes them; nothing is auto-verified."""
from __future__ import annotations

import json
from pathlib import Path

from schemas.domain import (D, EmissionFactor, FactorClass, GasComponent,
                            ValueBasis, VerificationStatus)

SEED_DIR = Path(__file__).resolve().parent.parent / "database" / "seed"
FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def load_nz_mfe_2023(path: Path | None = None, *, reviewer: str | None = None):
    doc = json.loads((path or FIXTURES / "nz_mfe_2023_factors.json").read_text("utf-8"))
    src = doc["source"]
    status = VerificationStatus.VERIFIED if reviewer else VerificationStatus.UNVERIFIED
    out = []
    for r in doc["rows"]:
        activity = r["activity"] if not r["use"] else f'{r["activity"]}_{r["use"]}'
        comps = (GasComponent("CO2", D(r["co2"]), ValueBasis.CO2E),
                 GasComponent("CH4", D(r["ch4"]), ValueBasis.CO2E),
                 GasComponent("N2O", D(r["n2o"]), ValueBasis.CO2E))
        out.append(EmissionFactor(
            factor_id=r["key"], version=1, country="NZ", category=r["category"],
            activity=activity, numerator_unit="kg CO2e", denominator_unit=r["unit"],
            total_co2e=D(r["total"]), components=comps,
            year_from=r["year"], year_to=r["year"],
            classification=FactorClass.OFFICIAL_NATIONAL, status=status,
            source_org=src["org"], source_title=src["title"], source_url=src["direct_url"],
            source_locator=f'{r["locator"]}, PDF p.{r["pdf_page"]}',
            gwp_set_id="AR5-GWP100",
            methodology="Published national factor; CH4/N2O columns already in CO2e",
            boundary_note=r["boundary"], license_note=src["licence_note"]))
    return out
