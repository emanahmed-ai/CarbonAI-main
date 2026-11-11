"""Deterministic calculation engine. No UI, DB or AI dependency."""
from __future__ import annotations

from decimal import Decimal

from schemas.domain import (ActivityInput, CalculationResult, EmissionFactor,
                            FactorClass, ValueBasis, VerificationStatus, D)
from services import unit_conversion as uc
from services.gwp import GwpSet

ENGINE_VERSION = "0.1.0"


class CalculationError(ValueError):
    pass


class ProxyNotConfirmedError(CalculationError):
    pass


def kg_to_tonnes(kg) -> Decimal:
    return D(kg) / D(1000)


def calculate(activity: ActivityInput, factor: EmissionFactor, *,
              gwp_set: GwpSet | None = None, proxy_confirmed: bool = False,
              allow_superseded: bool = False, allow_test_factor: bool = False,
              allow_year_mismatch: bool = False
              ) -> CalculationResult:
    """Emissions = Activity quantity (in factor denominator unit) x Factor.

    allow_year_mismatch=True is used ONLY by the documented selection policy (nearest-year
    estimate): the year range check is skipped and the result is flagged as an estimate with a
    warning that records the factor validity period. The formulas are unchanged.
    """
    if activity.quantity < 0:
        raise CalculationError("Activity quantity must not be negative")
    if factor.status == VerificationStatus.REJECTED:
        raise CalculationError("Rejected factors cannot be used")
    if factor.status == VerificationStatus.SUPERSEDED and not allow_superseded:
        raise CalculationError("Factor is superseded; pass allow_superseded=True "
                               "only to reproduce a historical calculation")
    if factor.classification == FactorClass.TEST_SYNTHETIC and not allow_test_factor:
        raise CalculationError("Synthetic test factors are blocked for real calculations")
    if (activity.category, activity.activity) != (factor.category, factor.activity):
        raise CalculationError("Factor does not match the activity category/type")
    year_mismatch = not (factor.year_from <= activity.year <= factor.year_to)
    if year_mismatch and not allow_year_mismatch:
        raise CalculationError(
            f"Reporting year {activity.year} outside factor validity "
            f"{factor.year_from}-{factor.year_to}")

    warnings, steps = [], []
    is_estimate = False
    if year_mismatch:
        warnings.append(f"ESTIMATED: factor valid {factor.year_from}-{factor.year_to}, "
                        f"used for reporting year {activity.year} (nearest-year selection)")
        is_estimate = True
    if factor.country != activity.country or factor.classification in (
            FactorClass.PROXY, FactorClass.REGIONAL, FactorClass.GLOBAL_DEFAULT):
        if not proxy_confirmed:
            raise ProxyNotConfirmedError(
                f"Factor {factor.factor_id} is {factor.classification.value} "
                f"({factor.country}) not national data for {activity.country}; "
                "explicit confirmation required")
        warnings.append(f"PROXY: {factor.classification.value} factor from "
                        f"{factor.country} used for {activity.country}")
        is_estimate = True
    if factor.status != VerificationStatus.VERIFIED:
        warnings.append(f"Factor status is {factor.status.value}, not verified")
        is_estimate = True
    if factor.classification == FactorClass.TEST_SYNTHETIC:
        warnings.append("SYNTHETIC TEST FACTOR - not real data")

    try:
        norm = uc.convert(activity.quantity, activity.unit, factor.denominator_unit)
    except uc.UnitError as exc:
        raise CalculationError(f"Unit problem: {exc}") from exc
    if uc.canon(activity.unit) != uc.canon(factor.denominator_unit):
        steps.append(f"Converted {activity.quantity} {activity.unit} -> "
                     f"{norm} {factor.denominator_unit}")

    per_gas: dict[str, Decimal] = {}
    used_gwp = factor.gwp_set_id
    for comp in factor.components:
        if comp.basis == ValueBasis.CO2E:
            per_gas[comp.gas] = norm * comp.value
        else:
            if gwp_set is None:
                raise CalculationError(
                    f"Component {comp.gas} is a mass value; a GWP set is required")
            per_gas[comp.gas] = norm * comp.value * gwp_set.gwp(comp.gas)
            if used_gwp and used_gwp != gwp_set.set_id:
                raise CalculationError(
                    f"GWP mismatch: factor uses {used_gwp}, selected {gwp_set.set_id}")
            used_gwp = gwp_set.set_id
    component_total = sum(per_gas.values(), D(0))

    if factor.total_co2e is not None:
        kg = norm * factor.total_co2e
        formula = (f"Emissions (kg CO2e) = {norm} {factor.denominator_unit} x "
                   f"{factor.total_co2e} kg CO2e/{factor.denominator_unit}")
        steps.append("Used the published total factor; per-gas rows are shown for "
                     "transparency and may differ by rounding in the source.")
        if component_total and abs(component_total - kg) > abs(kg) * D("0.02"):
            warnings.append("Per-gas components differ from published total by >2%")
    else:
        kg = component_total
        formula = (f"Emissions (kg CO2e) = sum over gases of {norm} "
                   f"{factor.denominator_unit} x gas factor [x GWP]")

    return CalculationResult(
        kg_co2e=kg, t_co2e=kg_to_tonnes(kg), formula=formula,
        original_quantity=activity.quantity, original_unit=activity.unit,
        normalized_quantity=norm, normalized_unit=factor.denominator_unit,
        per_gas_kg_co2e=per_gas, factor_snapshot=factor.snapshot(),
        gwp_set_id=used_gwp, steps=steps, warnings=warnings,
        is_estimate=is_estimate, engine_version=ENGINE_VERSION)


def refrigerant_leakage(leaked_kg, gwp, *, refrigerant: str, gwp_source: str) -> Decimal:
    """kg CO2e = refrigerant leaked (kg) x GWP. Source of the GWP is mandatory."""
    if not refrigerant or not gwp_source:
        raise CalculationError("refrigerant and gwp_source are required")
    if D(leaked_kg) < 0 or D(gwp) < 0:
        raise CalculationError("leaked_kg and gwp must be non-negative")
    return D(leaked_kg) * D(gwp)


def combustion_co2e(co2_kg, ch4_kg, n2o_kg, gwp_set: GwpSet) -> Decimal:
    """Total CO2e = CO2 + CH4 x GWP_CH4 + N2O x GWP_N2O."""
    return (D(co2_kg) + D(ch4_kg) * gwp_set.gwp("CH4")
            + D(n2o_kg) * gwp_set.gwp("N2O"))
