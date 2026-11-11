"""Reference library API (international standards/methodologies + Egyptian official sources)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.deps import Auth, current_user, get_con, require
from services import cooling as C

router = APIRouter(prefix="/api/references", tags=["references"])

KINDS = ("standard", "methodology", "factor_database", "gwp", "national_inventory")


@router.get("")
def list_references(kind: str | None = None, country: str | None = None, q: str | None = None,
                    con=Depends(get_con),
                    user: Auth = Depends(require("admin", "head_office", "factory_manager", "viewer"))):
    if kind and kind not in KINDS:
        raise HTTPException(400, f"kind must be one of {', '.join(KINDS)}")
    return C.list_references(con, kind=kind, country=country, q=q)


@router.get("/groups")
def groups(con=Depends(get_con),
           user: Auth = Depends(require("admin", "head_office", "factory_manager", "viewer"))):
    rows = C.list_references(con)
    out: dict[str, list] = {}
    for r in rows:
        out.setdefault(r["kind"], []).append(r)
    return {"counts": {k: len(v) for k, v in out.items()},
            "by_country": {"EG": sum(1 for r in rows if r["country_applicability"] == "EG"),
                           "GLOBAL": sum(1 for r in rows if r["country_applicability"] == "GLOBAL")},
            "groups": out}
