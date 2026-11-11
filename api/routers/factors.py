"""Emission factor library endpoints: search, ranked suggestion, coverage, sources, audit,
and the versioned write/verify operations (every change requires a reason - library rule)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import Auth, get_con, require
from api.util import rows_list
from services import factor_library as FL

router = APIRouter(prefix="/api/factors", tags=["factors"])


class FactorIn(BaseModel):
    factor_id: str
    country_code: str
    factor_class: str
    category: str
    activity: str
    unit: str
    value: str
    year_from: int
    year_to: int
    reference_id: str | None = None
    source_organization: str
    source_document: str
    source_url: str | None = None
    source_locator: str
    reason: str
    boundary_note: str = ""
    methodology: str = ""
    gwp_set_id: str | None = None
    notes: str | None = None
    publication_year: int | None = None


class VerifyIn(BaseModel):
    status: str
    reviewer_reason: str
    reference_id: str | None = None
    expected_min: str | None = None     # reviewer-supplied acceptance range (optional)
    expected_max: str | None = None


@router.get("")
def search_factors(country: str | None = None, category: str | None = None, sector: str | None = None,
                   activity_like: str | None = None, scope: str | None = None, year: int | None = None,
                   organization: str | None = None, unit: str | None = None, status: str | None = None,
                   factor_class: str | None = None, con=Depends(get_con), user: Auth = Depends(require("admin"))):
    rows = FL.search_factors(con, country=country, category=category, sector=sector,
                             activity_like=activity_like, scope=scope, year=year,
                             organization=organization, unit=unit, status=status, factor_class=factor_class)
    return rows_list(rows)


@router.get("/suggest")
def suggest(country: str, category: str, year: int, unit: str, fuel: str | None = None,
            con=Depends(get_con), user: Auth = Depends(require("admin", "head_office", "factory_manager", "viewer"))):
    sg = FL.suggest(con, country=country, category=category, year=year, unit=unit, fuel=fuel)
    near = FL.nearest_candidates(con, country=country, category=category, unit=unit, year=year, fuel=fuel)
    return {
        "message": sg.message,
        "chosen": (None if sg.chosen is None else {
            "factor": {k: (str(v) if hasattr(v, "isoformat") else v) for k, v in
                       [("factor_id", sg.chosen.factor.factor_id), ("version", sg.chosen.factor.version),
                        ("country", sg.chosen.factor.country), ("category", sg.chosen.factor.category),
                        ("activity", sg.chosen.factor.activity),
                        ("denominator_unit", sg.chosen.factor.denominator_unit),
                        ("total_co2e", str(sg.chosen.factor.total_co2e)),
                        ("status", sg.chosen.factor.status.value),
                        ("classification", sg.chosen.factor.classification.value),
                        ("source_org", sg.chosen.factor.source_org),
                        ("source_title", sg.chosen.factor.source_title),
                        ("source_url", sg.chosen.factor.source_url),
                        ("boundary_note", sg.chosen.factor.boundary_note)]},
            "tier": sg.chosen.tier, "reason": sg.chosen.reason,
            "needs_proxy_confirmation": sg.chosen.needs_proxy_confirmation,
            "usable_without_confirmation": sg.chosen.usable_without_confirmation}),
        "candidates": [{"factor_id": c.factor.factor_id, "version": c.factor.version,
                        "activity": c.factor.activity, "country": c.factor.country,
                        "unit": c.factor.denominator_unit, "value": str(c.factor.total_co2e),
                        "tier": c.tier, "status": c.factor.status.value,
                        "classification": c.factor.classification.value,
                        "national": c.is_national_for_activity, "verified": c.verified,
                        "needs_proxy_confirmation": c.needs_proxy_confirmation,
                        "usable_without_confirmation": c.usable_without_confirmation,
                        "reason": c.reason} for c in sg.candidates],
        "nearest": [{"factor_id": c.factor.factor_id, "version": c.factor.version,
                     "activity": c.factor.activity, "country": c.factor.country,
                     "unit": c.factor.denominator_unit, "value": str(c.factor.total_co2e),
                     "valid_from": c.factor.year_from, "valid_to": c.factor.year_to,
                     "distance_years": c.distance_years,
                     "status": c.factor.status.value,
                     "classification": c.factor.classification.value,
                     "reason": c.reason} for c in near[:5]],
        "excluded": [{"factor_id": f, "reason": r} for f, r in sg.excluded],
    }


@router.get("/coverage")
def coverage(con=Depends(get_con), user: Auth = Depends(require("admin"))):
    return rows_list(FL.countries_coverage(con))


@router.get("/audit")
def factor_audit(factor_id: str | None = None, con=Depends(get_con), user: Auth = Depends(require("admin", "head_office"))):
    return rows_list(FL.audit_log(con, factor_id))


@router.post("", status_code=201)
def add_factor(body: FactorIn, con=Depends(get_con), user: Auth = Depends(require("admin"))):
    """Admin-only: factor library management is restricted to authorised administrators on the
    backend (menu hiding is not security). Factory users consume factors via calculations only."""
    try:
        ver = FL.add_factor(con, factor_id=body.factor_id.strip(), country_code=body.country_code.strip().upper(),
                            factor_class=body.factor_class, category=body.category, activity=body.activity,
                            unit=body.unit, value=body.value, year_from=body.year_from, year_to=body.year_to,
                            reference_id=body.reference_id, source_organization=body.source_organization,
                            source_document=body.source_document, source_url=body.source_url,
                            source_locator=body.source_locator, reason=body.reason, user=user.username,
                            boundary_note=body.boundary_note, methodology=body.methodology,
                            gwp_set_id=body.gwp_set_id, notes=body.notes,
                            publication_year=body.publication_year)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"factor_id": body.factor_id.strip(), "version": ver}


@router.get("/{factor_id}/{version}/verify-preview")
def verify_preview(factor_id: str, version: int, expected_min: str | None = None,
                   expected_max: str | None = None, con=Depends(get_con),
                   user: Auth = Depends(require("admin"))):
    """Detailed evidence for the Verify action (no status change)."""
    try:
        return FL.verify_comparison(con, factor_id, version,
                                    expected_min=expected_min, expected_max=expected_max)
    except LookupError as e:
        raise HTTPException(404, str(e))


@router.post("/{factor_id}/{version}/verify")
def verify_factor(factor_id: str, version: int, body: VerifyIn, con=Depends(get_con),
                  user: Auth = Depends(require("admin"))):
    if not body.reviewer_reason.strip():
        raise HTTPException(400, "reviewer reason is required")
    try:
        cmp = FL.verify_comparison(con, factor_id, version,
                                   expected_min=body.expected_min, expected_max=body.expected_max)
        if body.status == "verified" and not cmp["can_verify"]:
            raise HTTPException(
                400, {"detail": "cannot mark verified without evidence",
                      "comparison": cmp, "failure_reason": cmp["reason"]})
        full_reason = f"{body.reviewer_reason.strip()} | comparison: {cmp['status_overall']}"
        if cmp["comparisons"]:
            c0 = cmp["comparisons"][0]
            if c0.get("difference_pct") is not None:
                full_reason += (f" (Δ {c0['difference']} vs {c0['against']['factor_id']}, "
                                f"{c0['difference_pct']}%)")
        FL.set_verification(con, factor_id, version, body.status, reviewer=user.username,
                            reason=full_reason, reference_id=body.reference_id)
    except HTTPException:
        raise
    except (ValueError, LookupError, PermissionError) as e:
        raise HTTPException(400, str(e))
    return {"factor_id": factor_id, "version": version, "status": body.status,
            "comparison": cmp}


@router.get("/refs-for-country")
def refs_for_country(country: str, category: str | None = None, con=Depends(get_con),
                     user: Auth = Depends(require("admin"))):
    """ALL references relevant to a country: the country-specific records AND the IPCC
    default references, each labelled with source, year and type."""
    if len(country) != 2:
        raise HTTPException(400, "country must be an ISO2 code")
    out: dict[str, list] = {"country_specific": [], "ipcc_default": []}
    for r in con.execute(
            "SELECT DISTINCT s.reference_id, s.organization_name, s.document_title, "
            "s.publication_year, s.source_url, s.verification_status FROM sources s "
            "JOIN emission_factors f ON f.reference_id=s.reference_id WHERE f.country_code=?",
            (country.upper(),)).fetchall():
        out["country_specific"].append({**dict(r), "type": "country_specific",
                                        "country": country.upper()})
    ipcc_q = ("SELECT DISTINCT s.reference_id, s.organization_name, s.document_title, "
              "s.publication_year, s.source_url, s.verification_status FROM sources s "
              "JOIN emission_factors f ON f.reference_id=s.reference_id "
              "WHERE f.country_code='GLOBAL' AND f.factor_class='global_default'")
    p: list = []
    if category:
        ipcc_q += " AND f.activity_category=?"
        p.append(category)
    for r in con.execute(ipcc_q, p).fetchall():
        out["ipcc_default"].append({**dict(r), "type": "ipcc_default"})
    out["total"] = len(out["country_specific"]) + len(out["ipcc_default"])
    return out


@router.get("/sources")
def sources(con=Depends(get_con), user: Auth = Depends(require("admin"))):
    return rows_list(con.execute("SELECT * FROM sources ORDER BY reference_id").fetchall())


@router.get("/gwp-sets")
def gwp_sets(user: Auth = Depends(require("admin"))):
    from services.gwp import REGISTRY
    return [{"set_id": s.set_id, "horizon_years": s.horizon_years,
             "values": {k: str(v) for k, v in s.values.items()}, "source": s.source, "note": s.note}
            for s in REGISTRY.values()]


# ---------------- Egypt factor database: rich filtering, coverage, export ----------------

@router.get("/egypt")
def egypt_factors(country: str = "EG", year: int | None = None, sector: str | None = None,
                  activity: str | None = None, gas: str | None = None,
                  country_scope: str | None = None, status: str | None = None,
                  q: str | None = None, con=Depends(get_con),
                  user: Auth = Depends(require("admin"))):
    sql = ("SELECT factor_id, version, country_code, sector, activity_category, activity, fuel_type, "
           "technology, gas, co2e_factor_value, activity_unit, year_from, year_to, country_scope, "
           "verification_status, source_organization, source_document, source_url, source_page, "
           "source_locator, data_year, quality_level, uncertainty, methodology, boundary_note "
           "FROM emission_factors WHERE 1=1")
    p: list = []
    if country and country != "ALL":
        # Egypt view includes GLOBAL international defaults (labelled by country_scope)
        sql += " AND country_code IN (?, 'GLOBAL')"; p.append(country)
    for col, val in (("sector", sector), ("activity", activity), ("gas", gas),
                     ("country_scope", country_scope), ("verification_status", status)):
        if val:
            sql += f" AND {col}=?"; p.append(val)
    if year:
        sql += " AND year_from<=? AND year_to>=?"; p += [year, year]
    if q:
        sql += " AND (factor_id LIKE ? OR activity LIKE ? OR source_organization LIKE ?)"
        p += [f"%{q}%"] * 3
    return rows_list(con.execute(sql + " ORDER BY country_scope, sector, activity, data_year", p).fetchall())


@router.get("/coverage-matrix")
def coverage_matrix(year: int | None = None, status: str | None = None,
                    activity: str | None = None, con=Depends(get_con),
                    user: Auth = Depends(require("admin"))):
    sql = "SELECT * FROM factor_coverage WHERE country_code='EG'"
    p: list = []
    if year:
        sql += " AND year=?"; p.append(year)
    if status:
        sql += " AND coverage_status=?"; p.append(status)
    if activity:
        sql += " AND activity=?"; p.append(activity)
    rows = rows_list(con.execute(sql + " ORDER BY year, sector, activity", p).fetchall())
    summary = {}
    for r in con.execute("SELECT year, coverage_status, COUNT(*) n FROM factor_coverage "
                         "WHERE country_code='EG' GROUP BY year, coverage_status").fetchall():
        summary.setdefault(int(r["year"]), {})[r["coverage_status"]] = int(r["n"])
    return {"rows": rows, "summary": [{"year": y, "statuses": summary.get(y, {})}
                                      for y in range(2006, 2027)]}


@router.get("/export.csv")
def export_factors(country: str = "EG", con=Depends(get_con),
                   user: Auth = Depends(require("admin", "head_office"))):
    from fastapi.responses import Response
    rows = con.execute(
        "SELECT factor_id, version, country_code, sector, activity_category, activity, fuel_type, "
        "technology, gas, co2e_factor_value, activity_unit, year_from, year_to, country_scope, "
        "verification_status, source_organization, source_document, source_url, data_year "
        "FROM emission_factors WHERE (?='ALL' OR country_code=?) ORDER BY country_code, activity",
        (country, country)).fetchall()
    import csv as _csv, io as _io
    buf = _io.StringIO()
    w = _csv.DictWriter(buf, fieldnames=list(rows[0].keys()) if rows else ["factor_id"])
    w.writeheader()
    for r in rows:
        w.writerow({k: r[k] for k in w.fieldnames})
    data = buf.getvalue().encode("utf-8-sig")
    return Response(content=data, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="carbonai_factors_{country}.csv"'})
