"""Dimension-checked unit conversion.

Rules enforced:
* Conversion only inside one physical dimension.
* Mass<->volume or volume<->energy NEVER converted implicitly; the caller must
  supply a documented density / calorific value (convert_with_property).
* passenger-km, tonne-km and vehicle-km are DISTINCT dimensions.
* No currency conversion without an explicitly supplied rate.
"""
from __future__ import annotations

from decimal import Decimal, getcontext

from schemas.domain import D

getcontext().prec = 40


class UnitError(ValueError):
    pass


class IncompatibleUnitsError(UnitError):
    pass


# unit -> (dimension, factor to the dimension's base unit)
_UNITS: dict[str, tuple[str, Decimal]] = {
    "kg": ("mass", D(1)), "g": ("mass", D("0.001")),
    "tonne": ("mass", D(1000)), "t": ("mass", D(1000)),
    "litre": ("volume", D(1)), "l": ("volume", D(1)),
    "ml": ("volume", D("0.001")), "m3": ("volume", D(1000)),
    # energy base kWh; 1 kWh = 3.6 MJ
    "kwh": ("energy", D(1)), "mwh": ("energy", D(1000)),
    "mj": ("energy", D(1) / D("3.6")),
    "gj": ("energy", D(1000) / D("3.6")),
    "km": ("distance", D(1)), "m": ("distance", D("0.001")),
    "mile": ("distance", D("1.609344")),
    "pkm": ("passenger_distance", D(1)),
    "tkm": ("freight_distance", D(1)),
    "room_night": ("room_night", D(1)),
    "unit": ("count", D(1)),   # added: generic count unit used by the original UI
}

_ALIASES = {"liter": "litre", "liters": "litre", "litres": "litre",
            "kilogram": "kg", "kilograms": "kg", "tonnes": "tonne",
            "tonne-km": "tkm", "tonne_km": "tkm", "passenger-km": "pkm", "units": "unit"}


def canon(unit: str) -> str:
    u = unit.strip().lower()
    u = _ALIASES.get(u, u)
    if u not in _UNITS:
        raise UnitError(f"Unknown unit: {unit!r}")
    return u


def dimension(unit: str) -> str:
    return _UNITS[canon(unit)][0]


def convert(quantity, from_unit: str, to_unit: str) -> Decimal:
    q = D(quantity)
    f, t = canon(from_unit), canon(to_unit)
    df, ff = _UNITS[f]
    dt, ft = _UNITS[t]
    if df != dt:
        raise IncompatibleUnitsError(
            f"Cannot convert {from_unit} ({df}) to {to_unit} ({dt}) without an "
            "explicitly supplied, documented conversion property.")
    return q * ff / ft


def _base(dim: str) -> str:
    return {"mass": "kg", "volume": "litre", "energy": "kwh"}[dim]


def convert_with_property(quantity, from_unit: str, to_unit: str, *,
                          property_value, property_unit: str) -> Decimal:
    """Cross-dimension conversion using a caller-supplied documented property.

    Supported: mass<->volume ('kg/litre'); volume/mass<->energy
    ('kWh/litre', 'kWh/kg').
    """
    q, p = D(quantity), D(property_value)
    if p <= 0:
        raise UnitError("property_value must be positive")
    f, t = canon(from_unit), canon(to_unit)
    df, dt = _UNITS[f][0], _UNITS[t][0]
    pu = property_unit.strip().lower().replace(" ", "")
    table = {
        ("volume", "mass", "kg/litre"): lambda x: x * p,
        ("mass", "volume", "kg/litre"): lambda x: x / p,
        ("volume", "energy", "kwh/litre"): lambda x: x * p,
        ("energy", "volume", "kwh/litre"): lambda x: x / p,
        ("mass", "energy", "kwh/kg"): lambda x: x * p,
        ("energy", "mass", "kwh/kg"): lambda x: x / p,
    }
    fn = table.get((df, dt, pu))
    if fn is None:
        raise IncompatibleUnitsError(
            f"Property {property_unit!r} cannot convert {df} to {dt}.")
    return convert(fn(convert(q, f, _base(df))), _base(dt), t)


def convert_currency(amount, rate, *, rate_source: str, rate_date: str) -> Decimal:
    """Currency conversion only with an explicit, documented rate."""
    if not rate_source or not rate_date:
        raise UnitError("rate_source and rate_date are required")
    r = D(rate)
    if r <= 0:
        raise UnitError("rate must be positive")
    return D(amount) * r
