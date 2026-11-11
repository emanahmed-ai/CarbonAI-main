"""Reduction plans, data-driven insights, reduction targets and the multi-year roadmap.

Honesty rules baked in:
* insights are derived from the caller's ACTUAL calculated ledger data (scoped, no double count);
* suggested actions cite recognised methodologies (GHG Protocol, IPCC, IEA, EPA) and explicitly
  state that a plant-specific audit is required before any percentage reduction is claimed;
* `expected_reduction_pct` is accepted only when the user supplies a reference source and KPI -
  the system never invents guaranteed reduction percentages.
"""
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import Auth, current_user, get_con, require, resolve_scope
from api.util import rows_list
from db.connection import now_iso, transaction
from services import ledger as L

router = APIRouter(prefix="/api/plans", tags=["plans"])

AREAS = ["رفع كفاءة الكهرباء", "تحسين كفاءة الوقود", "تحسين النقل والشحن",
         "تقليل المخلفات", "تحسين كفاءة المياه", "مراجعة المشتريات",
         "Electricity efficiency", "Fuel efficiency", "Transport & freight",
         "Waste reduction", "Water efficiency", "Procurement review"]
STATUSES = ("planned", "in_progress", "done", "cancelled")
PRIORITIES = ("high", "medium", "low")


class PlanIn(BaseModel):
    area: str
    description: str = ""
    owner: str = ""
    target_date: str | None = None
    status: str = "planned"
    linked_category_key: str | None = None
    assumptions: str = ""
    target_scope: str | None = None
    target_facility_id: int | None = None
    activity: str | None = None
    baseline_kg: str | None = None
    expected_reduction_pct: float | None = None
    kpi: str | None = None
    priority: str | None = None
    reference_source: str | None = None
    plan_year: int | None = None


class TargetIn(BaseModel):
    baseline_year: int
    target_year: int
    target_kg_co2e: str | None = None
    baseline_kg_co2e: str | None = None
    reduction_pct: float | None = None
    facility_id: int | None = None
    note: str = ""


@router.get("")
def list_plans(con=Depends(get_con), user: Auth = Depends(current_user)):
    return rows_list(con.execute("SELECT * FROM reduction_plans ORDER BY plan_id DESC").fetchall())


@router.get("/insights")
def insights(con=Depends(get_con), user: Auth = Depends(current_user),
             company_id: int | None = None, facility_id: int | None = None, year: int | None = None,
             date_from: str | None = None, date_to: str | None = None):
    """Data-driven prioritisation for the caller's scope: highest scope/facilities/activities."""
    cid, fid = resolve_scope(user, company_id, facility_id)
    df = L.fetch_records(con, company_id=cid, facility_id=fid, year=year,
                         date_from=date_from or None, date_to=date_to or None)
    s = L.summarize(df)
    calc = df[df["calc_status"] == "calculated"] if not df.empty else df
    by_fac, by_cat, by_act = [], [], []
    if not calc.empty:
        for name, g in calc.groupby("facility_name", dropna=False):
            by_fac.append({"facility_name": name or "—", "kg": str(L._sum(g["kg"]))})
        for key, g in calc.groupby("category_key", dropna=False):
            by_cat.append({"category_key": key or "other", "kg": str(L._sum(g["kg"]))})
        for name, g in calc.groupby("activity_name"):
            by_act.append({"activity_name": name, "kg": str(L._sum(g["kg"]))})
    by_fac.sort(key=lambda x: -float(x["kg"]))
    by_cat.sort(key=lambda x: -float(x["kg"]))
    by_act.sort(key=lambda x: -float(x["kg"]))
    scopes = {k: str(v) for k, v in s["by_scope_kg"].items()}
    top_scope = max(scopes.items(), key=lambda kv: Decimal(kv[1]))[0] if any(
        Decimal(v) > 0 for v in scopes.values()) else None

    templates = {
        "electricity": dict(area="Electricity efficiency", reference="GHG Protocol Scope 2 Guidance; IEA energy-efficiency indicators",
                            methodology="Meter consumption before/after each measure; the achievable reduction must be established by a site energy audit - no generic percentage is assumed."),
        "stationary_fuel": dict(area="Fuel efficiency", reference="IPCC 2006 Guidelines (fuel combustion); manufacturer performance data",
                                methodology="Track fuel per unit of useful output before/after (boiler tune-up, burner upgrade); savings require measurement."),
        "mobile_fuel": dict(area="Transport & freight", reference="GHG Protocol Scope 1 mobile combustion; DEFRA fleet guidance",
                            methodology="Compare litres/100 km and tonnes-km before/after; route and driver measures measured over time."),
        "transport_freight": dict(area="Transport & freight", reference="GHG Protocol Scope 3 Category 4/9; DEFRA freight factors",
                                  methodology="Mode shift and load-factor studies; reduction depends on contracted carriers, verify with measured tonne-km."),
        "refrigerant": dict(area="Refrigerant leakage prevention", reference="GHG Protocol Scope 1 fugitive emissions; EPA refrigerant management",
                            methodology="Leak detection + inventory (top-up quantities) establishes the baseline; savings = avoided top-up x GWP."),
        "waste": dict(area="Waste reduction", reference="GHG Protocol Scope 3 Category 5; IPCC waste model",
                      methodology="Weigh waste streams by destination; reductions from diversion measured per stream."),
        "water": dict(area="Water efficiency", reference="GHG Protocol Scope 3 (water supply); utility data",
                      methodology="Sub-meter pumping energy and water losses; savings measured per m3."),
        "purchased_goods": dict(area="Procurement review", reference="GHG Protocol Scope 3 Category 1; supplier-specific factors",
                                methodology="Supplier engagement and spend-based screening; requires supplier data before claiming reductions."),
    }
    suggestions = []
    for c in by_cat[:4]:
        t = templates.get(c["category_key"])
        if not t:
            continue
        suggestions.append({
            "area": t["area"], "category_key": c["category_key"], "baseline_kg": c["kg"],
            "rationale": f"Category accounts for {c['kg']} kg CO2e in the selected scope.",
            "reference": t["reference"], "methodology": t["methodology"],
            "priority": "high" if Decimal(c["kg"]) > Decimal(str(s["total_kg"])) / 3 else "medium",
        })
    return {"total_kg": str(s["total_kg"]), "top_scope": top_scope,
            "by_scope": scopes, "facilities": by_fac[:6], "categories": by_cat[:6],
            "activities": by_act[:6], "suggestions": suggestions,
            "disclaimer": "Recommendations are derived from actual calculated emissions; projected "
                          "reductions are not guaranteed and require a site-specific audit."}


@router.post("", status_code=201)
def create_plan(body: PlanIn, con=Depends(get_con),
                user: Auth = Depends(require("admin", "head_office", "factory_manager"))):
    _validate_plan(body)
    with transaction(con):
        cur = con.execute(
            "INSERT INTO reduction_plans(area,description,owner,target_date,status,linked_category_key,"
            "assumptions,created_at,target_scope,target_facility_id,activity,baseline_kg,"
            "expected_reduction_pct,kpi,priority,reference_source,plan_year) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (body.area.strip(), body.description, body.owner, body.target_date, body.status,
             body.linked_category_key, body.assumptions, now_iso(), body.target_scope,
             body.target_facility_id, body.activity, body.baseline_kg,
             body.expected_reduction_pct, body.kpi, body.priority, body.reference_source,
             body.plan_year))
    return con.execute("SELECT * FROM reduction_plans WHERE plan_id=?", (cur.lastrowid,)).fetchone()


@router.patch("/{plan_id}")
def update_plan(plan_id: int, body: PlanIn, con=Depends(get_con),
                user: Auth = Depends(require("admin", "head_office", "factory_manager"))):
    row = con.execute("SELECT plan_id FROM reduction_plans WHERE plan_id=?", (plan_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "plan not found")
    _validate_plan(body)
    with transaction(con):
        con.execute(
            "UPDATE reduction_plans SET area=?, description=?, owner=?, target_date=?, status=?, "
            "linked_category_key=?, assumptions=?, target_scope=?, target_facility_id=?, activity=?, "
            "baseline_kg=?, expected_reduction_pct=?, kpi=?, priority=?, reference_source=?, plan_year=? "
            "WHERE plan_id=?",
            (body.area.strip(), body.description, body.owner, body.target_date, body.status,
             body.linked_category_key, body.assumptions, body.target_scope, body.target_facility_id,
             body.activity, body.baseline_kg, body.expected_reduction_pct, body.kpi, body.priority,
             body.reference_source, body.plan_year, plan_id))
    return con.execute("SELECT * FROM reduction_plans WHERE plan_id=?", (plan_id,)).fetchone()


def _validate_plan(body: PlanIn) -> None:
    if body.status not in STATUSES:
        raise HTTPException(400, f"status must be one of {', '.join(STATUSES)}")
    if body.priority and body.priority not in PRIORITIES:
        raise HTTPException(400, f"priority must be one of {', '.join(PRIORITIES)}")
    if not body.area.strip():
        raise HTTPException(400, "area is required")
    if body.expected_reduction_pct is not None:
        if not (0 < body.expected_reduction_pct <= 100):
            raise HTTPException(400, "expected_reduction_pct must be in (0, 100]")
        if not (body.reference_source or "").strip() or not (body.kpi or "").strip():
            raise HTTPException(400, "an expected reduction percentage requires a reference source "
                                     "and a monitoring KPI (no unsupported percentages)")


# ---------------- targets & roadmap ----------------

@router.get("/targets")
def list_targets(con=Depends(get_con), user: Auth = Depends(current_user)):
    return rows_list(con.execute("SELECT * FROM reduction_targets ORDER BY target_year").fetchall())


@router.post("/targets", status_code=201)
def create_target(body: TargetIn, con=Depends(get_con),
                  user: Auth = Depends(require("admin", "head_office"))):
    if body.target_year <= body.baseline_year:
        raise HTTPException(400, "target_year must be after baseline_year")
    cid, fid = resolve_scope(user, None, body.facility_id)
    if any(v is None for v in (body.target_kg_co2e, body.baseline_kg_co2e, body.reduction_pct)):
        base_df = L.fetch_records(con, company_id=cid, facility_id=fid, year=body.baseline_year)
        base = L.summarize(base_df)["total_kg"]
        if body.baseline_kg_co2e:
            base = Decimal(body.baseline_kg_co2e)
        if body.reduction_pct is not None:
            if not (0 < body.reduction_pct <= 100):
                raise HTTPException(400, "reduction_pct must be in (0, 100]")
            target = base * (Decimal(1) - Decimal(str(body.reduction_pct)) / Decimal(100))
        elif body.target_kg_co2e:
            target = Decimal(body.target_kg_co2e)
        else:
            raise HTTPException(400, "provide target_kg_co2e or reduction_pct")
    else:
        base, target = Decimal(body.baseline_kg_co2e), Decimal(body.target_kg_co2e)
    if base <= 0:
        raise HTTPException(400, "baseline emissions are zero for that year/scope; cannot set a target")
    pct = float((base - target) / base * 100)
    existing = con.execute(
        "SELECT target_id FROM reduction_targets WHERE IFNULL(company_id,0)=IFNULL(?,0) "
        "AND IFNULL(facility_id,0)=IFNULL(?,0) AND target_year=?",
        (cid, fid, body.target_year)).fetchone()
    with transaction(con):
        if existing:
            con.execute(
                "UPDATE reduction_targets SET baseline_year=?, baseline_kg_co2e=?, target_kg_co2e=?, "
                "target_reduction_pct=?, note=? WHERE target_id=?",
                (body.baseline_year, str(base), str(target), pct, body.note, existing["target_id"]))
            tid = existing["target_id"]
        else:
            cur = con.execute(
                "INSERT INTO reduction_targets(company_id,facility_id,baseline_year,baseline_kg_co2e,"
                "target_year,target_kg_co2e,target_reduction_pct,note,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (cid, fid, body.baseline_year, str(base), body.target_year, str(target), pct,
                 body.note, now_iso()))
            tid = cur.lastrowid
    return con.execute("SELECT * FROM reduction_targets WHERE target_id=?", (tid,)).fetchone()


@router.get("/roadmap")
def roadmap(company_id: int | None = None, facility_id: int | None = None,
            con=Depends(get_con), user: Auth = Depends(current_user)):
    """Historical actuals + targets + gap, for the multi-year reduction roadmap chart."""
    cid, fid = resolve_scope(user, company_id, facility_id)
    df = L.fetch_records(con, company_id=cid, facility_id=fid)
    yearly = {int(y): str(v) for y, v in L.yearly_totals(df).items()}
    targets = con.execute(
        "SELECT * FROM reduction_targets WHERE IFNULL(company_id,0)=IFNULL(?,0) "
        "AND IFNULL(facility_id,0)=IFNULL(?,0) ORDER BY target_year", (cid, fid)).fetchall()
    tmap = {int(t["target_year"]): t for t in targets}
    years = sorted(set(yearly) | set(tmap))
    rows = []
    for y in years:
        actual = yearly.get(y)
        t = tmap.get(y)
        row = {"year": y, "actual_kg": actual, "target_kg": None if t is None else t["target_kg_co2e"],
               "target_reduction_pct": None if t is None else t["target_reduction_pct"],
               "gap_kg": None}
        if actual is not None and t is not None:
            row["gap_kg"] = str(Decimal(actual) - Decimal(t["target_kg_co2e"]))
        rows.append(row)
    return {"years": rows, "targets": rows_list(targets),
            "note": "actual = calculated ledger emissions for that year; target = approved reduction target."}


def _plan_result(con, plan, *, cid: int | None, fid: int | None) -> dict:
    """Measured results for one plan (baseline vs actual ledger emissions; no predictions)."""
    from decimal import Decimal as _D
    year = plan["plan_year"] or int(str(plan["created_at"])[:4])
    cat = plan["linked_category_key"]
    actual_df = L.fetch_records(con, company_id=cid, facility_id=fid, year=year, category_key=cat)
    actual = L.summarize(actual_df)["total_kg"]
    baseline = None
    if plan["baseline_kg"] not in (None, ""):
        baseline = _D(str(plan["baseline_kg"]))
        baseline_source = "stored baseline on the plan"
    else:
        prev_df = L.fetch_records(con, company_id=cid, facility_id=fid, year=year - 1, category_key=cat)
        prev = L.summarize(prev_df)["total_kg"]
        if prev > 0:
            baseline = prev
            baseline_source = f"previous year ({year - 1}) for the same facility/category"
        else:
            baseline_source = "unavailable: no stored baseline and no previous-year data"
    reduction_pct = None
    if baseline and baseline > 0:
        reduction_pct = round(float((baseline - actual) / baseline * 100), 1)
    target_pct = plan["expected_reduction_pct"]
    target_source = "user"
    if target_pct is None and reduction_pct is not None:
        # approved rule: when the user entered no target, compute it from measured data
        target_pct = reduction_pct
        target_source = "computed_from_measured"
    if baseline is None:
        status = "insufficient_data"
    elif plan["expected_reduction_pct"] is None:
        status = "no_target_set"
    elif reduction_pct is not None and reduction_pct >= plan["expected_reduction_pct"]:
        status = "achieved"
    elif reduction_pct is not None and reduction_pct > 0:
        status = "partial"
    else:
        status = "not_achieved"
    return {"plan_id": plan["plan_id"], "area": plan["area"], "plan_year": year,
            "baseline_kg": None if baseline is None else str(baseline),
            "baseline_source": baseline_source, "actual_kg": str(actual),
            "savings_kg": None if baseline is None else str(baseline - actual),
            "reduction_pct": reduction_pct,
            "target_reduction_pct": plan["expected_reduction_pct"],
            "target_reduction_pct_computed": None if target_source == "user" else target_pct,
            "target_reduction_pct_source": target_source,
            "status": status, "measured": True,
            "note": "Actual values come from calculated ledger records of the plan year; "
                    "predictions are never used here."}


@router.get("/results-overview")
def results_overview(con=Depends(get_con), user: Auth = Depends(current_user),
                     company_id: int | None = None, facility_id: int | None = None):
    """Weighted overall reduction across plans, from MEASURED data.

    Per plan the effective target % is the user-entered target when present, otherwise the
    measured reduction (computed). The overall % is weighted by each plan's baseline volume."""
    from decimal import Decimal as _D
    cid, fid = resolve_scope(user, company_id, facility_id)
    plans = con.execute("SELECT * FROM reduction_plans ORDER BY plan_id").fetchall()
    results = []
    for plan in plans:
        fid_p = plan["target_facility_id"] if "target_facility_id" in plan.keys() else None
        if user.is_factory_scoped and fid_p != user.facility_id:
            continue
        if user.role == "head_office" and fid_p:
            fac = con.execute("SELECT company_id FROM facilities WHERE facility_id=?", (fid_p,)).fetchone()
            if fac is None or fac["company_id"] != user.company_id:
                continue
        results.append(_plan_result(con, plan, cid=cid, fid=fid_p))
    tot_base = _D(0)
    tot_actual = _D(0)
    tgt_weighted = _D(0)
    tgt_base = _D(0)
    computed_used = 0
    for r in results:
        if r["baseline_kg"] is None:
            continue
        b = _D(r["baseline_kg"])
        a = _D(r["actual_kg"])
        tot_base += b
        tot_actual += a
        eff = r["target_reduction_pct"]
        if eff is None:
            eff = r["target_reduction_pct_computed"]
            if eff is not None:
                computed_used += 1
        if eff is not None:
            tgt_weighted += b * _D(str(eff))
            tgt_base += b
    overall_measured = round(float((tot_base - tot_actual) / tot_base * 100), 1) if tot_base > 0 else None
    overall_target = round(float(tgt_weighted / tgt_base), 1) if tgt_base > 0 else None
    return {"plans_evaluated": len(results),
            "with_baseline": sum(1 for r in results if r["baseline_kg"] is not None),
            "overall_baseline_kg": str(tot_base), "overall_actual_kg": str(tot_actual),
            "overall_measured_reduction_pct": overall_measured,
            "overall_target_reduction_pct": overall_target,
            "overall_target_basis": (f"weighted by baseline emission volume; "
                                     f"{computed_used} plan(s) used a computed target"),
            "plans": results}


@router.get("/{plan_id}/results")
def plan_results(plan_id: int, con=Depends(get_con), user: Auth = Depends(current_user)):
    """Measured results for a plan: baseline vs actual ledger emissions (no predictions)."""
    plan = con.execute("SELECT * FROM reduction_plans WHERE plan_id=?", (plan_id,)).fetchone()
    if plan is None:
        raise HTTPException(404, "plan not found")
    fid_p = plan["target_facility_id"] if "target_facility_id" in plan.keys() else None
    cid, fid = resolve_scope(user, None, fid_p)
    return _plan_result(con, plan, cid=cid, fid=fid)
