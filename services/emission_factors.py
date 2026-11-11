"""Factor selection. Never invents a factor; never silently falls back."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from schemas.domain import EmissionFactor, FactorClass, VerificationStatus


class MissingFactorError(LookupError):
    """No usable factor. Carries any proxy candidates for explicit user choice."""

    def __init__(self, message: str, proxy_candidates=()):
        super().__init__(message)
        self.proxy_candidates = list(proxy_candidates)


@dataclass
class Selection:
    factor: EmissionFactor
    is_proxy: bool
    rationale: str
    alternatives: list = field(default_factory=list)


_USABLE = {VerificationStatus.VERIFIED}
_NON_NATIONAL = {FactorClass.REGIONAL, FactorClass.GLOBAL_DEFAULT, FactorClass.PROXY}


def _match(f, country, category, activity, year):
    return (f.category == category and f.activity == activity
            and f.year_from <= year <= f.year_to)


def select_factor(factors: Iterable[EmissionFactor], *, country: str, category: str,
                  activity: str, year: int, allow_unverified: bool = False,
                  allow_test: bool = False) -> Selection:
    """Pick the national, verified, in-year factor for the exact activity.

    Policy (documented in docs/calculation_methodology.md):
      1. Only factors for the requested country are eligible as primary.
      2. Only VERIFIED (or explicitly allowed UNVERIFIED) factors are eligible.
      3. TEST_SYNTHETIC factors are excluded unless allow_test=True.
      4. If several remain, the highest version wins; the others are returned as
         alternatives so disagreements are visible, not hidden.
      5. If none: raise MissingFactorError listing proxy candidates; the caller
         must obtain explicit confirmation to use one (select_proxy).
    """
    pool = [f for f in factors if _match(f, country, category, activity, year)
            and f.status != VerificationStatus.REJECTED
            and f.status != VerificationStatus.SUPERSEDED
            and (allow_test or f.classification != FactorClass.TEST_SYNTHETIC)]
    nat = [f for f in pool if f.country == country
           and f.classification not in _NON_NATIONAL
           and (f.status in _USABLE or allow_unverified)]
    if nat:
        nat.sort(key=lambda f: (-f.version, f.factor_id))
        best = nat[0]
        return Selection(best, False,
                         f"National factor for {country}, status={best.status.value}",
                         nat[1:])
    proxies = [f for f in pool if f.country != country
               and f.status in _USABLE | ({VerificationStatus.UNVERIFIED}
                                           if allow_unverified else set())]
    raise MissingFactorError(
        f"No verified national factor for country={country}, category={category}, "
        f"activity={activity}, year={year}.", proxies)


def select_proxy(candidate: EmissionFactor, *, confirmed_by: str, rationale: str) -> Selection:
    if not confirmed_by or not rationale.strip():
        raise PermissionError("Proxy use requires confirmed_by and a written rationale")
    return Selection(candidate, True,
                     f"PROXY confirmed by {confirmed_by}: {rationale}")
