"""GWP sets. Only values read from a supplied source document are stored.

AR4 and AR5 CH4/N2O values come from Table 1 of the NZ Ministry for the
Environment guide (2023), p.15. Table 1 states the AR5 CH4 value (28) EXCLUDES
the value for fossil methane. Other gases (HFCs etc.) are intentionally NOT
seeded here: they must be imported from a cited table (e.g. Table 7 of the same
guide, or the IPCC reports) via the reference-import pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from schemas.domain import D


@dataclass(frozen=True)
class GwpSet:
    set_id: str
    horizon_years: int
    values: dict
    source: str
    note: str = ""

    def gwp(self, gas: str) -> Decimal:
        try:
            return self.values[gas]
        except KeyError:
            raise KeyError(
                f"GWP for {gas!r} not present in set {self.set_id!r}; import it "
                "from a cited source rather than assuming a value.") from None


_SRC = ("Ministry for the Environment (NZ), Measuring emissions: A guide for "
        "organisations: 2023 detailed guide, Table 1, p.15")

AR4_100 = GwpSet("AR4-GWP100", 100,
                 {"CO2": D(1), "CH4": D(25), "N2O": D(298)}, _SRC)
AR5_100 = GwpSet("AR5-GWP100", 100,
                 {"CO2": D(1), "CH4": D(28), "N2O": D(265)}, _SRC,
                 "CH4 excludes the value for fossil methane (per Table 1 title).")

REGISTRY = {s.set_id: s for s in (AR4_100, AR5_100)}


def get_gwp_set(set_id: str) -> GwpSet:
    if set_id not in REGISTRY:
        raise KeyError(f"Unknown GWP set {set_id!r}")
    return REGISTRY[set_id]
