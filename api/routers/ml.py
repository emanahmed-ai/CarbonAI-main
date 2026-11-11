"""ML endpoints: truthful status, versioned forecasting lifecycle (train -> staged -> admin
activation -> forecast), and the row-level estimate. Prediction requests never retrain."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import Auth, get_con, require, resolve_scope
from services import forecast as F
from services import ml_model as M

router = APIRouter(prefix="/api/ml", tags=["ml"])


class PredictIn(BaseModel):
    quantity: float
    unit: str
    category_key: str | None = None
    scope: str | None = None
    activity_month: int | None = None


class TrainIn(BaseModel):
    facility_id: int | None = None
    scope: str | None = None
    horizon: int = 12
    force: bool = False


@router.get("/status")
def status(con=Depends(get_con), user: Auth = Depends(require("admin", "head_office", "factory_manager", "viewer"))):
    row_model = M.registry_status()
    return {
        "row_estimate_model": row_model,
        "forecast_models": F.registry(con),
        "data_readiness": {
            "min_months_required": F.MIN_MONTHS,
            "note": "Forecast eligibility requires consecutive monthly calculated emissions.",
        },
    }


@router.post("/train")
def train(body: TrainIn, con=Depends(get_con), user: Auth = Depends(require("admin"))):
    cid, fid = resolve_scope(user, None, body.facility_id)
    result = F.train(con, company_id=cid, facility_id=fid, scope=body.scope,
                     force=body.force, trained_by=user.username)
    if not result.get("ok"):
        raise HTTPException(409, result)
    return result


@router.get("/models")
def models(con=Depends(get_con), user: Auth = Depends(require("admin", "head_office"))):
    return F.registry(con)


@router.post("/models/{model_id}/activate")
def activate(model_id: int, con=Depends(get_con), user: Auth = Depends(require("admin"))):
    try:
        return F.activate(con, model_id, approved_by=user.username)
    except LookupError as e:
        raise HTTPException(404, str(e))


@router.get("/forecast")
def forecast(facility_id: int | None = None, scope: str | None = None, horizon: int = 12,
             con=Depends(get_con), user: Auth = Depends(require("admin", "head_office", "factory_manager", "viewer"))):
    cid, fid = resolve_scope(user, None, facility_id)
    if scope not in (None, "Scope 1", "Scope 2", "Scope 3"):
        raise HTTPException(400, "scope must be Scope 1/2/3 or empty")
    try:
        return F.forecast(con, company_id=cid, facility_id=fid, scope=scope, horizon=horizon)
    except F.ForecastError as e:
        raise HTTPException(400, str(e))


@router.post("/predict")
def predict(body: PredictIn, user: Auth = Depends(require("admin", "head_office", "factory_manager", "viewer"))):
    try:
        return M.predict({"quantity": body.quantity, "unit": body.unit,
                          "category_key": body.category_key, "scope": body.scope,
                          "activity_month": body.activity_month})
    except FileNotFoundError:
        raise HTTPException(404, "No trained row-estimate model is loaded. Train one first "
                                 "(python scripts/train_emission_model.py).")
    except Exception as e:
        raise HTTPException(400, f"prediction failed: {e}")
