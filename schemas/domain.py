"""Pure-Python domain objects (no third-party dependencies).

All quantities and factor values are Decimal. Floats are rejected on purpose so
that persisted values never carry binary floating-point error.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Optional


def D(value) -> Decimal:
    """Build a Decimal from str/int/Decimal. Floats are rejected."""
    if isinstance(value, float):
        raise TypeError("float not allowed; pass str, int or Decimal")
    return value if isinstance(value, Decimal) else Decimal(str(value))


class FactorClass(str, Enum):
    OFFICIAL_NATIONAL = "official_national"
    REGIONAL = "regional"
    GLOBAL_DEFAULT = "global_default"
    PROXY = "proxy"
    USER_SUPPLIED = "user_supplied"
    TEST_SYNTHETIC = "test_synthetic"  # never allowed in real reports


class VerificationStatus(str, Enum):
    UNVERIFIED = "unverified"
    PENDING_REVIEW = "pending_review"
    VERIFIED = "verified"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"


class ValueBasis(str, Enum):
    CO2E = "co2e"  # value already expressed in CO2-equivalent; GWP NOT re-applied
    MASS = "mass"  # value is mass of the gas; GWP of the chosen set IS applied


@dataclass(frozen=True)
class GasComponent:
    gas: str              # "CO2", "CH4", "N2O", ...
    value: Decimal        # per one denominator unit
    basis: ValueBasis


@dataclass(frozen=True)
class EmissionFactor:
    factor_id: str
    version: int
    country: str                      # ISO alpha-2, or "GLOBAL"/"REGION:xx"
    category: str                     # e.g. "electricity", "stationary_fuel"
    activity: str                     # e.g. "diesel", "grid_average"
    numerator_unit: str               # "kg CO2e" (reporting unit of total)
    denominator_unit: str             # e.g. "kWh", "litre", "kg", "GJ"
    total_co2e: Optional[Decimal]     # published total (kg CO2e per denominator)
    components: tuple[GasComponent, ...]
    year_from: int
    year_to: int
    classification: FactorClass
    status: VerificationStatus
    source_org: str
    source_title: str
    source_url: Optional[str]         # direct URL if known; else None (never invented)
    source_locator: str               # table/page/row
    gwp_set_id: Optional[str]         # GWP basis embedded in CO2e values
    methodology: str = ""
    boundary_note: str = ""           # e.g. "excludes T&D losses"
    license_note: str = ""

    def snapshot(self) -> dict:
        """JSON-safe immutable copy stored with every calculation."""
        return {
            "factor_id": self.factor_id, "version": self.version,
            "country": self.country, "category": self.category,
            "activity": self.activity, "denominator_unit": self.denominator_unit,
            "total_co2e": None if self.total_co2e is None else str(self.total_co2e),
            "components": [[c.gas, str(c.value), c.basis.value] for c in self.components],
            "year_from": self.year_from, "year_to": self.year_to,
            "classification": self.classification.value, "status": self.status.value,
            "source_org": self.source_org, "source_title": self.source_title,
            "source_url": self.source_url, "source_locator": self.source_locator,
            "gwp_set_id": self.gwp_set_id, "boundary_note": self.boundary_note,
        }


@dataclass(frozen=True)
class ActivityInput:
    quantity: Decimal
    unit: str
    country: str
    year: int
    category: str
    activity: str


@dataclass
class CalculationResult:
    kg_co2e: Decimal
    t_co2e: Decimal
    formula: str
    original_quantity: Decimal
    original_unit: str
    normalized_quantity: Decimal
    normalized_unit: str
    per_gas_kg_co2e: dict
    factor_snapshot: dict
    gwp_set_id: Optional[str]
    steps: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    is_estimate: bool = False
    engine_version: str = ""
