"""DB-backed factor library: query, ranked candidate suggestion, versioned add/verify.

Ranking tiers (docs): 1 national official (same country) > 2 regional/local >
3 international (global default) > 4 proxy (another country's national data).
Ranking is NOT absolute: unit compatibility, year validity and verification are applied first
and every excluded/non-chosen candidate carries a reason string.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal

from db.connection import now_iso, transaction
from schemas.domain import (D, EmissionFactor, FactorClass, GasComponent, ValueBasis,
                            VerificationStatus)
from services import unit_conversion as uc

TIER = {FactorClass.OFFICIAL_NATIONAL: 1, FactorClass.REGIONAL: 2, FactorClass.GLOBAL_DEFAULT: 3,
        FactorClass.PROXY: 4, FactorClass.USER_SUPPLIED: 5, FactorClass.TEST_SYNTHETIC: 9}

VERIFICATION_LABELS = {  # (ar, en)
    "verified": ("موثق من مصدر رسمي وتم التحقق منه", "Verified against official source"),
    "pending_review": ("مصدر معروف لكن المعامل يحتاج إلى مراجعة", "Known source, factor needs review"),
    "unverified": ("غير متحقق منه", "Unverified"),
    "superseded": ("منتهي الصلاحية أو يحتاج إلى تحديث", "Superseded / needs update"),
    "rejected": ("مرفوض", "Rejected"),
}


def row_to_factor(r) -> EmissionFactor:
    comps = tuple(GasComponent(g, D(v), ValueBasis(b)) for g, v, b in json.loads(r["components_json"] or "[]"))
    return EmissionFactor(
        factor_id=r["factor_id"], version=r["version"], country=r["country_code"],
        category=r["activity_category"], activity=r["activity"], numerator_unit="kg CO2e",
        denominator_unit=r["activity_unit"],
        total_co2e=None if r["co2e_factor_value"] is None else D(r["co2e_factor_value"]),
        components=comps, year_from=r["year_from"], year_to=r["year_to"],
        classification=FactorClass(r["factor_class"]), status=VerificationStatus(r["verification_status"]),
        source_org=r["source_organization"] or "", source_title=r["source_document"] or "",
        source_url=r["source_url"], source_locator=r["source_locator"] or "", gwp_set_id=r["gwp_set_id"],
        methodology=r["methodology"] or "", boundary_note=r["boundary_note"] or "",
        license_note=r["license_note"] or "")


def get_factor(con, factor_id: str, version: int | None = None) -> EmissionFactor | None:
    if version is None:
        r = con.execute("SELECT * FROM emission_factors WHERE factor_id=? ORDER BY version DESC LIMIT 1",
                        (factor_id,)).fetchone()
    else:
        r = con.execute("SELECT * FROM emission_factors WHERE factor_id=? AND version=?",
                        (factor_id, version)).fetchone()
    return row_to_factor(r) if r else None


def search_factors(con, *, country=None, category=None, sector=None, activity_like=None, scope=None,
                   year=None, organization=None, unit=None, status=None, factor_class=None):
    q, p = "SELECT * FROM emission_factors WHERE 1=1", []
    for col, val in (("country_code", country), ("activity_category", category),
                     ("industry_sector", sector), ("scope", scope), ("source_organization", organization),
                     ("activity_unit", unit), ("verification_status", status), ("factor_class", factor_class)):
        if val:
            q += f" AND {col}=?"; p.append(val)
    if activity_like:
        q += " AND (activity LIKE ? OR factor_name_en LIKE ?)"; p += [f"%{activity_like}%"] * 2
    if year:
        q += " AND year_from<=? AND year_to>=?"; p += [year, year]
    return con.execute(q + " ORDER BY country_code, activity_category, activity, year_from DESC, version DESC", p).fetchall()


def countries_coverage(con):
    """Which countries have factors, by class and status - used to avoid claiming global coverage."""
    return con.execute(
        "SELECT c.iso2_code, c.country_name_en, c.country_name_ar, "
        "COUNT(f.factor_id) AS n_factors, "
        "SUM(CASE WHEN f.verification_status='verified' THEN 1 ELSE 0 END) AS n_verified "
        "FROM countries c LEFT JOIN emission_factors f ON f.country_code=c.iso2_code "
        "WHERE c.is_active=1 GROUP BY c.country_id ORDER BY n_factors DESC, c.country_name_en").fetchall()


@dataclass
class Candidate:
    factor: EmissionFactor
    tier: int
    is_national_for_activity: bool
    verified: bool
    usable_without_confirmation: bool
    needs_proxy_confirmation: bool
    reason: str


@dataclass
class Suggestion:
    chosen: Candidate | None
    candidates: list = field(default_factory=list)
    excluded: list = field(default_factory=list)   # (factor_id, reason)
    message: str = ""


@dataclass
class NearestCandidate:
    factor: EmissionFactor
    distance_years: int          # 0 = year inside validity range
    reason: str


def nearest_candidates(con, *, country: str, category: str, unit: str, year: int,
                       fuel: str | None = None) -> list[NearestCandidate]:
    """Factors for the same country/category/unit outside the requested year, closest first.

    Used only by the documented selection policy: exact year -> nearest year (marked as an
    estimate) -> IPCC default (marked as international default). Rejected/superseded/synthetic
    factors and incompatible units are never returned.
    """
    rows = con.execute(
        "SELECT * FROM emission_factors WHERE activity_category=? "
        "AND verification_status NOT IN ('rejected','superseded')", (category,)).fetchall()
    out = []
    for r in rows:
        f = row_to_factor(r)
        if f.classification == FactorClass.TEST_SYNTHETIC:
            continue
        # Selection policy: nearest-year is only allowed for the SAME country's factors or for
        # international defaults (IPCC/GLOBAL). Another country's national factor is a proxy and
        # must never be auto-selected - it stays available only as an explicit, confirmed choice.
        if f.country != country and f.classification not in (FactorClass.GLOBAL_DEFAULT,
                                                             FactorClass.REGIONAL):
            continue
        if fuel and not f.activity.lower().startswith(fuel.lower()):
            continue
        try:
            uc.convert(1, unit, f.denominator_unit)
        except uc.UnitError:
            continue
        if f.year_from <= year <= f.year_to:
            distance = 0
        else:
            distance = min(abs(year - f.year_from), abs(year - f.year_to))
        if distance == 0:
            continue  # exact matches are handled by suggest()
        same_country = f.country == country
        out.append(NearestCandidate(
            f, distance,
            f"{'National' if same_country else 'International'} factor for {f.country} valid "
            f"{f.year_from}-{f.year_to}; requested year {year} → nearest-year estimate "
            f"(±{distance} year{'s' if distance != 1 else ''})"))
    out.sort(key=lambda c: (c.distance_years, not (c.factor.status == VerificationStatus.VERIFIED),
                            c.factor.country != country, -c.factor.version, c.factor.factor_id))
    return out


def suggest(con, *, country: str, category: str, year: int, unit: str, fuel: str | None = None) -> Suggestion:
    """Rank candidates. A factor is auto-chosen ONLY when exactly one verified national factor for the
    same country/category/year fits (after fuel + unit filters). Otherwise the user must choose."""
    rows = con.execute(
        "SELECT * FROM emission_factors WHERE activity_category=? AND year_from<=? AND year_to>=? "
        "AND verification_status NOT IN ('rejected','superseded')", (category, year, year)).fetchall()
    cands, excluded = [], []
    for r in rows:
        f = row_to_factor(r)
        if f.classification == FactorClass.TEST_SYNTHETIC:
            excluded.append((f.factor_id, "synthetic test factor")); continue
        if fuel and not f.activity.lower().startswith(fuel.lower()):
            excluded.append((f.factor_id, f"activity '{f.activity}' does not match fuel/material '{fuel}'")); continue
        try:
            uc.convert(1, unit, f.denominator_unit)
        except uc.UnitError:
            excluded.append((f.factor_id, f"unit {unit} cannot be converted to factor unit "
                                          f"{f.denominator_unit} without a documented conversion property")); continue
        national = f.country == country and f.classification == FactorClass.OFFICIAL_NATIONAL
        verified = f.status == VerificationStatus.VERIFIED
        tier = TIER[f.classification] if (f.country == country or f.classification != FactorClass.OFFICIAL_NATIONAL) else 4
        if f.country != country and f.classification == FactorClass.OFFICIAL_NATIONAL:
            why = f"National factor of {f.country}, NOT of {country}: proxy only if explicitly confirmed"
        elif national:
            why = f"Official national factor for {country}"
        else:
            why = f"{f.classification.value} factor ({f.country}); shown as a substitute, not a national factor"
        if not verified:
            why += f"; status={f.status.value}"
        cands.append(Candidate(f, tier, national, verified, national and verified,
                               tier >= 2 and not national, why))
    cands.sort(key=lambda c: (c.tier, not c.verified, -c.factor.version, c.factor.factor_id))
    auto = [c for c in cands if c.usable_without_confirmation]
    if len(auto) == 1:
        s = Suggestion(auto[0], cands, excluded, "Single verified national factor matched.")
        return s
    if len(auto) > 1:
        return Suggestion(None, cands, excluded,
                          "Several verified national factors match (e.g. different use/boundary): choose one.")
    nat_unv = [c for c in cands if c.is_national_for_activity and not c.verified]
    if nat_unv:
        return Suggestion(None, cands, excluded,
                          "National factor(s) exist but are NOT verified: a reviewer must verify them, or you may "
                          "explicitly accept an unverified factor (result will be flagged).")
    if cands:
        return Suggestion(None, cands, excluded,
                          f"No national factor for {country}. Only substitutes below; using one needs explicit "
                          "confirmation with a written rationale.")
    return Suggestion(None, [], excluded, f"No factor in the library for country={country}, category={category}, "
                                          f"year={year}. Record will be marked 'needs factor'.")


# ---------------- write operations (versioned, audited, never destructive) ----------------

def _log(con, f_id, ver, action, field_name, old, new, user, reason, ref):
    con.execute("INSERT INTO factor_audit_log(factor_id,version,action,field_name,old_value,new_value,"
                "changed_at,changed_by,reason,reference_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (f_id, ver, action, field_name, old, new, now_iso(), user, reason, ref))


def add_factor(con, *, factor_id, country_code, factor_class, category, activity, unit, value,
               year_from, year_to, reference_id, source_organization, source_document, source_url,
               source_locator, reason, user, boundary_note="", methodology="", gwp_set_id=None,
               notes=None, publication_year=None) -> int:
    """New factor id -> version 1. Existing id -> NEW version (old one is kept, marked superseded)."""
    if not reason or not reason.strip():
        raise ValueError("A reason is required for every library change")
    if not source_document or not source_organization:
        raise ValueError("source_organization and source_document are required (no unsourced factors)")
    v = D(value)
    if v < 0:
        raise ValueError("factor value must be >= 0")
    FactorClass(factor_class)
    with transaction(con):
        prev = con.execute("SELECT MAX(version) m FROM emission_factors WHERE factor_id=?", (factor_id,)).fetchone()["m"]
        ver = (prev or 0) + 1
        con.execute(
            "INSERT INTO emission_factors(factor_id,version,factor_name_en,country_code,factor_class,activity_category,"
            "activity,activity_unit,factor_unit,co2e_factor_value,components_json,gwp_set_id,reference_id,"
            "source_organization,source_document,source_url,source_locator,publication_year,year_from,year_to,"
            "geographic_coverage,methodology,boundary_note,verification_status,notes,created_at,gas_type)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,'[]',?,?,?,?,?,?,?,?,?,?,?,?,'unverified',?,?,'CO2e')",
            (factor_id, ver, f"{category} / {activity}", country_code, factor_class, category, activity, unit,
             f"kg CO2e/{unit}", str(v), gwp_set_id, reference_id, source_organization, source_document,
             source_url, source_locator, publication_year, year_from, year_to, country_code, methodology,
             boundary_note, notes, now_iso()))
        _log(con, factor_id, ver, "created" if ver == 1 else "new_version", "co2e_factor_value",
             None, str(v), user, reason, reference_id)
        if prev:
            old = con.execute("SELECT verification_status s FROM emission_factors WHERE factor_id=? AND version=?",
                              (factor_id, prev)).fetchone()["s"]
            con.execute("UPDATE emission_factors SET verification_status='superseded' WHERE factor_id=? AND version=?",
                        (factor_id, prev))
            _log(con, factor_id, prev, "superseded", "verification_status", old, "superseded", user, reason, reference_id)
    return ver


def set_verification(con, factor_id, version, new_status: str, *, reviewer: str, reason: str,
                     reference_id: str | None = None) -> None:
    """Promote/demote a factor. A named reviewer and a reason are mandatory; 'verified' also needs a source URL
    or locator recorded on the row (a bare link is not proof of the value - the reviewer attests the match)."""
    VerificationStatus(new_status)
    if not reviewer or not reason.strip():
        raise PermissionError("reviewer and reason are required")
    with transaction(con):
        r = con.execute("SELECT verification_status s, source_locator l, source_url u FROM emission_factors "
                        "WHERE factor_id=? AND version=?", (factor_id, version)).fetchone()
        if r is None:
            raise LookupError("factor/version not found")
        if new_status == "verified" and not (r["l"] or r["u"]):
            raise ValueError("Cannot verify a factor with no source locator/URL recorded")
        con.execute("UPDATE emission_factors SET verification_status=?, verified_by=?, last_verified_at=? "
                    "WHERE factor_id=? AND version=?",
                    (new_status, reviewer, now_iso() if new_status == "verified" else None, factor_id, version))
        _log(con, factor_id, version, "verification_change", "verification_status", r["s"], new_status,
             reviewer, reason, reference_id)


def audit_log(con, factor_id=None):
    if factor_id:
        return con.execute("SELECT * FROM factor_audit_log WHERE factor_id=? ORDER BY log_id", (factor_id,)).fetchall()
    return con.execute("SELECT * FROM factor_audit_log ORDER BY log_id").fetchall()


# ---------------- verification evidence (detailed comparison) ----------------

def verify_comparison(con, factor_id: str, version: int, *,
                      expected_min: str | None = None,
                      expected_max: str | None = None) -> dict:
    """Evidence for the Verify action. Compares the factor against the REGISTERED reference
    factors for the same category+activity+unit (e.g. the IPCC default we seeded with its exact
    source). No acceptance range is invented: 'within/out of range' applies only when the
    reviewer supplies an expected range; otherwise the difference is reported and the status is
    'differs_from_registered'. Never changes any status by itself."""
    from schemas.domain import D as _D

    f = get_factor(con, factor_id, version)
    if f is None:
        raise LookupError("factor not found")
    checked = {
        "factor_id": f.factor_id, "version": f.version, "value": str(f.total_co2e),
        "unit": f.denominator_unit, "year_from": f.year_from, "year_to": f.year_to,
        "country": f.country, "classification": f.classification.value,
        "status": f.status.value,
        "source_organization": f.source_org, "source_document": f.source_title,
        "source_locator": f.source_locator, "source_url": f.source_url,
    }
    if f.total_co2e is None:
        return {"checked": checked, "comparisons": [], "status_overall": "no_reference_available",
                "reason": "factor has no numeric value to compare"}

    rows = con.execute(
        "SELECT * FROM emission_factors WHERE activity_category=? AND activity=? "
        "AND country_code='GLOBAL' AND factor_class='global_default' "
        "AND verification_status NOT IN ('rejected') AND NOT (factor_id=? AND version=?)",
        (f.category, f.activity, f.factor_id, f.version)).fetchall()
    comparisons = []
    for r in rows:
        b = row_to_factor(r)
        if b.total_co2e is None or b.denominator_unit != f.denominator_unit:
            continue
        if factor_id.startswith("REF-") and b.factor_id.startswith("REF-"):
            continue  # same substance in another GWP basis: not an independent reference
        diff = _D(f.total_co2e) - _D(b.total_co2e)
        pct = float(diff / _D(b.total_co2e) * 100) if _D(b.total_co2e) != 0 else None
        if pct == 0:
            status = "matched"
        elif expected_min is not None and expected_max is not None:
            lo, hi = _D(expected_min), _D(expected_max)
            status = "within_range" if lo <= _D(f.total_co2e) <= hi else "out_of_range"
        else:
            status = "differs_from_registered"
        comparisons.append({
            "against": {"factor_id": b.factor_id, "version": b.version,
                        "source_organization": b.source_org, "source_document": b.source_title,
                        "source_url": b.source_url, "value": str(b.total_co2e),
                        "unit": b.denominator_unit,
                        "classification": b.classification.value,
                        "status": b.status.value,
                        "year_from": b.year_from, "year_to": b.year_to},
            "difference": str(diff), "difference_pct": None if pct is None else round(pct, 2),
            "status": status,
        })
    if expected_min is not None and expected_max is not None and not comparisons:
        lo, hi = _D(expected_min), _D(expected_max)
        in_range = lo <= _D(f.total_co2e) <= hi
        comparisons.append({
            "against": None,
            "difference": None, "difference_pct": None,
            "status": "within_range" if in_range else "out_of_range",
            "note": "reviewer-supplied expected range (no registered default factor for comparison)",
        })

    statuses = [c["status"] for c in comparisons]
    if not comparisons:
        overall = "no_reference_available"
        reason = ("No registered reference factor exists for this category/activity/unit "
                  "(and no reviewer range was supplied). Manual source check required.")
    elif "matched" in statuses:
        overall, reason = "matched", "identical to the registered reference value"
    elif "within_range" in statuses:
        overall, reason = "within_range", "within the reviewer-supplied expected range"
    elif "out_of_range" in statuses:
        overall, reason = "out_of_range", "outside the reviewer-supplied expected range"
    else:
        overall = "differs_from_registered"
        reason = ("differs from the registered reference value; no documented acceptance range "
                  "exists, so the difference is reported for reviewer judgement")
    return {"checked": checked, "comparisons": comparisons,
            "status_overall": overall, "reason": reason,
            "can_verify": overall in ("matched", "within_range")}
