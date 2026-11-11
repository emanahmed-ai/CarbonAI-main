"""Dashboard aggregation. One data path for every number: ledger.fetch_records + ledger.summarize
(same as the CSV/PDF reports), scoped to the caller's tenancy."""
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends

from api.deps import Auth, get_con, current_user, resolve_scope
from services import ledger as L

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _by_facility(df):
    out = []
    if df.empty:
        return out
    calc = df[df["calc_status"] == "calculated"]
    for name, g in calc.groupby(["facility_id", "facility_name"], dropna=False):
        sub = L.summarize(g)
        out.append({"facility_id": None if name[0] is None else int(name[0]),
                    "facility_name": name[1] or "—",
                    "total_kg_co2e": str(sub["total_kg"]),
                    "total_t_co2e": str(sub["total_t"]),
                    "records": int(len(g)),
                    "by_scope_kg": {k: str(v) for k, v in sub["by_scope_kg"].items()}})
    return sorted(out, key=lambda x: -float(x["total_kg_co2e"] or 0))


def _by_category(df):
    if df.empty:
        return []
    calc = df[df["calc_status"] == "calculated"]
    out = []
    for key, g in calc.groupby("category_key", dropna=False):
        out.append({"category_key": key or "other", "total_kg_co2e": str(L._sum(g["kg"]))})
    return sorted(out, key=lambda x: -float(x["total_kg_co2e"] or 0))


@router.get("/summary")
def summary(con=Depends(get_con), user: Auth = Depends(current_user),
            company_id: int | None = None, facility_id: int | None = None,
            year: int | None = None, month: int | None = None,
            date_from: str | None = None, date_to: str | None = None, scope: str | None = None,
            category_key: str | None = None):
    cid, fid = resolve_scope(user, company_id, facility_id)
    df = L.fetch_records(con, company_id=cid, facility_id=fid, year=year, month=month,
                         date_from=date_from or None, date_to=date_to or None, scope=scope,
                         category_key=category_key)
    s = L.summarize(df, year=year)
    total = float(s["total_kg"]) or 0.0

    # previous equivalent period: same month last year > previous year > previous equal range.
    # Change is reported ONLY when the baseline period has actual calculated emissions.
    prev = None
    if month and year:
        prev = ({"year": year - 1, "month": month}, f"{year - 1}-{month:02d}")
    elif year:
        prev = ({"year": year - 1}, str(year - 1))
    elif date_from and date_to:
        from datetime import date, timedelta
        try:
            d0 = date.fromisoformat(date_from); d1 = date.fromisoformat(date_to)
            span = (d1 - d0).days + 1
            prev = ({"date_from": str(d0 - timedelta(days=span)), "date_to": str(d0 - timedelta(days=1))},
                    f"{d0 - timedelta(days=span)} → {d0 - timedelta(days=1)}")
        except ValueError:
            prev = None
    comparison = None
    if prev:
        params, label = prev
        prev_df = L.fetch_records(con, company_id=cid, facility_id=fid, scope=scope,
                                  category_key=category_key, **params)
        ps = L.summarize(prev_df, year=params.get("year"))
        prev_total = float(ps["total_kg"]) or 0.0
        comparison = {
            "baseline_label": label,
            "prev_total_kg": str(ps["total_kg"]),
            "comparable": prev_total > 0,
            "change_pct": None if prev_total <= 0 else round((total - prev_total) / prev_total * 100, 1),
            "per_scope": {},
        }
        for sc in ("Scope 1", "Scope 2", "Scope 3"):
            pv = float(ps["by_scope_kg"][sc]) or 0.0
            cv = float(s["by_scope_kg"][sc]) or 0.0
            comparison["per_scope"][sc] = {
                "prev_kg": str(ps["by_scope_kg"][sc]),
                "change_pct": None if pv <= 0 else round((cv - pv) / pv * 100, 1),
                "comparable": pv > 0,
            }

    scopes_kpi = []
    for sc in ("Scope 1", "Scope 2", "Scope 3"):
        kg = float(s["by_scope_kg"][sc]) or 0.0
        scopes_kpi.append({
            "scope": sc, "kg": str(s["by_scope_kg"][sc]),
            "t": f"{kg / 1000:.6f}",
            "share_pct": None if total <= 0 else round(kg / total * 100, 1),
            "change_pct": None if not comparison else comparison["per_scope"][sc]["change_pct"],
            "comparable": False if not comparison else comparison["per_scope"][sc]["comparable"],
        })

    refrigerant = {"kg": "0", "share_of_scope1_pct": None, "records": 0, "by_equipment": []}
    if not df.empty and "category_key" in df.columns:
        rdf = df[(df["category_key"] == "refrigerant") & (df["calc_status"] == "calculated")]
        if not rdf.empty:
            rkg = L._sum(rdf["kg"])
            s1 = Decimal(s["by_scope_kg"]["Scope 1"] or 0)
            by_eq: dict[str, Decimal] = {}
            for _, row in rdf.iterrows():
                by_eq[row["activity_name"]] = by_eq.get(row["activity_name"], Decimal(0)) + row["kg"]
            refrigerant = {
                "kg": str(rkg), "share_of_scope1_pct":
                    None if s1 <= 0 else round(float(rkg / s1 * 100), 1),
                "records": int(len(rdf)),
                "by_equipment": sorted([{"equipment": k, "kg": str(v)} for k, v in by_eq.items()],
                                       key=lambda x: -float(x["kg"]))[:8],
            }

    return {
        "total_kg_co2e": str(s["total_kg"]), "total_t_co2e": str(s["total_t"]),
        "by_scope_kg": {k: str(v) for k, v in s["by_scope_kg"].items()},
        "scopes_kpi": scopes_kpi,
        "comparison": comparison,
        "unscoped_kg": str(s["unscoped_kg"]), "undated_kg": str(s["undated_kg"]),
        "monthly_kg": {f"{y}-{m:02d}": str(v) for (y, m), v in s["monthly_kg"].items()},
        "avg_monthly_active_kg": None if s["avg_monthly_active_kg"] is None else str(s["avg_monthly_active_kg"]),
        "avg_monthly_12_kg": None if s["avg_monthly_12_kg"] is None else str(s["avg_monthly_12_kg"]),
        "months_with_data": s["months_with_data"],
        "records": s["records"], "calculated": s["calculated"],
        "needs_review": s["needs_review"], "verified_pct": s["verified_pct"],
        "verified_factor_records": s["verified_factor_records"],
        "top_sources": [{"activity": a, "total_kg_co2e": str(v)} for a, v in L.top_sources(df)],
        "yearly_totals": {str(y): str(v) for y, v in L.yearly_totals(df).items()},
        "by_facility": _by_facility(df), "by_category": _by_category(df),
        "refrigerant": refrigerant,
        "scope": {"company_id": cid, "facility_id": fid},
    }


@router.get("/comparison")
def comparison(year: int | None = None, con=Depends(get_con), user: Auth = Depends(current_user)):
    """Facility-vs-facility totals (head office / admin view)."""
    cid, _ = resolve_scope(user, None, None)
    df = L.fetch_records(con, company_id=cid, year=year)
    return {"year": year, "facilities": _by_facility(df), "by_category": _by_category(df)}
