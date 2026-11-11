"""Monthly/annual emissions forecasting with a proper training lifecycle.

Lifecycle: prepare dataset -> evaluate candidates (chronological split, baseline comparison)
-> register a versioned model (staged) -> admin activation -> forecast only from the ACTIVE
model. Prediction requests NEVER retrain.

Eligibility: at least 12 consecutive months of calculated emissions (gaps end the contiguous
window; missing months are never treated as zero). Insufficient data returns an explicit
INSUFFICIENT_DATA payload describing exactly what is missing - no invented forecasts.

Evaluation: last 20% of the series is held out chronologically (min 3 points). Candidates:
seasonal naive (y[t-12]), linear trend, gradient boosting on time/lag features. The best MAE
wins; the naive baseline's metrics are always reported. Forecasts carry an empirical residual
band (labelled as an error band, not a statistical guarantee).
"""
from __future__ import annotations

import hashlib
import json
import pickle
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from db.connection import connect, now_iso, transaction
from services import ledger as L

ROOT = Path(__file__).resolve().parent.parent
MODEL_DIR = ROOT / "models"
MIN_MONTHS = 12
TEST_FRACTION = 0.2
HORIZONS = (1, 3, 6, 12)


class ForecastError(ValueError):
    pass


# ---------------- dataset ----------------

def monthly_series(con, *, company_id=None, facility_id=None, scope=None) -> dict:
    """Contiguous monthly series ending at the latest calculated month. Missing months are gaps,
    never zeros; the window stops at the first gap so the model sees a continuous timeline."""
    df = L.fetch_records(con, company_id=company_id, facility_id=facility_id, scope=scope)
    if df.empty:
        return {"points": [], "reason": "no records", "records": 0}
    calc = df[(df["calc_status"] == "calculated") & df["activity_year"].notna()
              & df["activity_month"].notna()].copy()
    calc["kg"] = calc["kg"].apply(lambda v: float(v) if v is not None else None)
    calc = calc[calc["kg"].notna()]
    if calc.empty:
        return {"points": [], "reason": "no calculated records with period data", "records": 0}
    per = calc.groupby(["activity_year", "activity_month"])["kg"].sum().sort_index()
    idx = [(int(y), int(m)) for y, m in per.index]
    latest = idx[-1]
    # walk backwards to build the contiguous window
    window = []
    y, m = latest
    while True:
        if (y, m) in per.index:
            window.append(((y, m), float(per.loc[(y, m)])))
            m -= 1
            if m == 0:
                y, m = y - 1, 12
            if y < 2000:
                break
        else:
            break
    window.reverse()
    return {"points": window, "records": int(len(calc)), "latest": latest,
            "reason": "" if len(window) >= MIN_MONTHS else f"only {len(window)} contiguous months"}


def fingerprint(points: list, config: dict) -> str:
    payload = json.dumps({"points": [(f"{y}-{m:02d}", round(v, 6)) for (y, m), v in points],
                          "config": config}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


# ---------------- features / candidates ----------------

def _add_months(y: int, m: int, k: int) -> tuple[int, int]:
    total = (y * 12 + (m - 1)) + k
    return total // 12, total % 12 + 1


def _features(points: list) -> tuple[np.ndarray, np.ndarray, list]:
    """Rows need lag>=2; features: t, sin/cos month, lag1, lag2, roll3."""
    vals = np.array([v for _, v in points], dtype=float)
    months = np.array([m for (_, m), _ in points])
    X, y, meta = [], [], []
    for i in range(len(vals)):
        if i < 3:
            continue
        X.append([i, np.sin(2 * np.pi * months[i] / 12), np.cos(2 * np.pi * months[i] / 12),
                  vals[i - 1], vals[i - 2], float(np.mean(vals[i - 3:i]))])
        y.append(vals[i])
        meta.append(points[i])
    return np.array(X), np.array(y), meta


def _seasonal_naive(vals: np.ndarray, k: int = 1) -> float:
    return float(vals[-12]) if len(vals) >= 12 else float(vals[-1])


def _evaluate(points: list) -> dict:
    vals = np.array([v for _, v in points], dtype=float)
    n = len(vals)
    test_n = max(3, int(round(n * TEST_FRACTION)))
    split = n - test_n
    train_vals, test_vals = vals[:split], vals[split:]
    results = {}

    # candidate 1: seasonal naive (baseline)
    pred_naive = []
    hist = list(train_vals)
    for actual in test_vals:
        pred = hist[-12] if len(hist) >= 12 else hist[-1]
        pred_naive.append(pred)
        hist.append(actual)
    results["seasonal_naive"] = _metrics(test_vals, np.array(pred_naive))

    # candidate 2: linear trend (fit on t)
    t_tr = np.arange(split, dtype=float).reshape(-1, 1)
    from sklearn.linear_model import LinearRegression
    lr = LinearRegression().fit(t_tr, train_vals)
    t_te = np.arange(split, n, dtype=float).reshape(-1, 1)
    results["linear_trend"] = _metrics(test_vals, lr.predict(t_te))

    # candidate 3: gradient boosting on time/lag features (needs enough rows)
    X, y, meta = _features(points)
    if len(X) >= 20:
        cut = max(8, int(len(X) * (1 - TEST_FRACTION)))
        from sklearn.ensemble import GradientBoostingRegressor
        gb = GradientBoostingRegressor(random_state=42, n_estimators=150, max_depth=2)
        gb.fit(X[:cut], y[:cut])
        results["gradient_boosting"] = _metrics(y[cut:], gb.predict(X[cut:]))
    return results


def _metrics(actual, pred) -> dict:
    actual, pred = np.asarray(actual, float), np.asarray(pred, float)
    mae = float(np.mean(np.abs(actual - pred)))
    rmse = float(np.sqrt(np.mean((actual - pred) ** 2)))
    denom = float(np.sum((actual - np.mean(actual)) ** 2))
    r2 = float(1 - np.sum((actual - pred) ** 2) / denom) if denom > 0 else None
    resid_std = float(np.std(actual - pred))
    return {"mae_kg": round(mae, 2), "rmse_kg": round(rmse, 2),
            "r2": None if r2 is None else round(r2, 4),
            "residual_std_kg": round(resid_std, 2), "test_points": int(len(actual))}


# ---------------- training / registry ----------------

def model_name(*, company_id=None, facility_id=None, scope=None) -> str:
    if facility_id:
        base = f"monthly_forecast:facility:{facility_id}"
    elif company_id:
        base = f"monthly_forecast:company:{company_id}"
    else:
        base = "monthly_forecast:org"
    return base if not scope else f"{base}:{scope.replace(' ', '').lower()}"


def train(con, *, company_id=None, facility_id=None, scope=None, force=False,
          trained_by="system") -> dict:
    name = model_name(company_id=company_id, facility_id=facility_id, scope=scope)
    series = monthly_series(con, company_id=company_id, facility_id=facility_id, scope=scope)
    if len(series["points"]) < MIN_MONTHS:
        return {"ok": False, "status": "INSUFFICIENT_DATA",
                "reason": f"Need at least {MIN_MONTHS} consecutive months of calculated emissions; "
                          f"found {len(series['points'])} ({series['reason'] or 'ok'}).",
                "months_available": len(series["points"]), "records": series.get("records", 0)}
    config = {"min_months": MIN_MONTHS, "test_fraction": TEST_FRACTION, "features_version": 1}
    fp = fingerprint(series["points"], config)
    active = con.execute("SELECT * FROM model_registry WHERE name=? AND status='active' "
                         "ORDER BY version DESC LIMIT 1", (name,)).fetchone()
    if active and active["dataset_fingerprint"] == fp and not force:
        return {"ok": True, "skipped": True, "reason": "dataset and configuration unchanged; reusing the active model",
                "model_id": active["model_id"], "version": active["version"]}
    metrics = _evaluate(series["points"])
    best = min((k for k in metrics if k != "seasonal_naive"),
               key=lambda k: metrics[k]["mae_kg"], default="seasonal_naive")
    if best != "seasonal_naive" and metrics[best]["mae_kg"] > metrics["seasonal_naive"]["mae_kg"]:
        best = "seasonal_naive"
    vals = np.array([v for _, v in series["points"]], dtype=float)
    artifact = {
        "format": "carbonai.forecast/1", "name": name, "candidate": best,
        "points": [(y, m, v) for (y, m), v in series["points"]],
        "residual_std_kg": metrics[best]["residual_std_kg"],
        "trained_at": now_iso(), "config": config,
    }
    if best == "linear_trend":
        from sklearn.linear_model import LinearRegression
        t = np.arange(len(vals), dtype=float).reshape(-1, 1)
        artifact["model"] = LinearRegression().fit(t, vals)
        artifact["last_t"] = len(vals)
    elif best == "gradient_boosting":
        X, y, _ = _features(series["points"])
        from sklearn.ensemble import GradientBoostingRegressor
        artifact["model"] = GradientBoostingRegressor(random_state=42, n_estimators=150,
                                                      max_depth=2).fit(X, y)
        artifact["history_tail"] = [float(v) for v in vals[-6:]]
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    ver = (con.execute("SELECT MAX(version) v FROM model_registry WHERE name=?", (name,)).fetchone()["v"] or 0) + 1
    path = MODEL_DIR / f"forecast_{name.replace(':', '_')}_v{ver}.pkl"
    with open(path, "wb") as fh:
        pickle.dump(artifact, fh)
    with transaction(con):
        cur = con.execute(
            "INSERT INTO model_registry(name,version,artifact_path,dataset_fingerprint,train_date_from,"
            "train_date_to,n_records,features_json,config_json,metrics_json,status,created_at,created_by,notes) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,'staged',?,?,?)",
            (name, ver, str(path), fp, f"{series['points'][0][0][0]}-{series['points'][0][0][1]:02d}",
             f"{series['points'][-1][0][0]}-{series['points'][-1][0][1]:02d}",
             len(series["points"]),
             json.dumps(["t", "sin_month", "cos_month", "lag1", "lag2", "roll3"]),
             json.dumps(config), json.dumps(metrics), now_iso(), trained_by,
             f"selected={best}; baseline_mae={metrics['seasonal_naive']['mae_kg']}"))
        model_id = cur.lastrowid
    return {"ok": True, "skipped": False, "model_id": model_id, "name": name, "version": ver,
            "candidate": best, "metrics": metrics, "months": len(series["points"]),
            "range": [f"{series['points'][0][0][0]}-{series['points'][0][0][1]:02d}",
                      f"{series['points'][-1][0][0]}-{series['points'][-1][0][1]:02d}"],
            "fingerprint": fp, "status": "staged"}


def activate(con, model_id: int, *, approved_by: str) -> dict:
    m = con.execute("SELECT * FROM model_registry WHERE model_id=?", (model_id,)).fetchone()
    if m is None:
        raise LookupError("model not found")
    with transaction(con):
        con.execute("UPDATE model_registry SET status='archived' WHERE name=? AND status='active'", (m["name"],))
        con.execute("UPDATE model_registry SET status='active', approved_by=?, approved_at=? WHERE model_id=?",
                    (approved_by, now_iso(), model_id))
    return {"model_id": model_id, "status": "active", "name": m["name"], "version": m["version"]}


def active_model(con, *, company_id=None, facility_id=None, scope=None):
    name = model_name(company_id=company_id, facility_id=facility_id, scope=scope)
    return con.execute("SELECT * FROM model_registry WHERE name=? AND status='active' "
                       "ORDER BY version DESC LIMIT 1", (name,)).fetchone()


def registry(con, *, name_prefix="monthly_forecast") -> list[dict]:
    rows = con.execute("SELECT * FROM model_registry WHERE name LIKE ? ORDER BY model_id DESC",
                       (f"{name_prefix}%",)).fetchall()
    return [{**_dict(r), "metrics": json.loads(r["metrics_json"] or "{}"),
             "config": json.loads(r["config_json"] or "{}")} for r in rows]


def _dict(r) -> dict:
    return {k: r[k] for k in r.keys() if k not in ("metrics_json", "config_json", "features_json")}


# ---------------- forecasting ----------------

def _load_artifact(path: str) -> dict:
    with open(path, "rb") as fh:
        art = pickle.load(fh)
    if art.get("format") != "carbonai.forecast/1":
        raise ForecastError("unsupported forecast artifact")
    return art


def forecast(con, *, company_id=None, facility_id=None, scope=None, horizon=12) -> dict:
    if horizon not in HORIZONS:
        raise ForecastError(f"horizon must be one of {HORIZONS}")
    series = monthly_series(con, company_id=company_id, facility_id=facility_id, scope=scope)
    model = active_model(con, company_id=company_id, facility_id=facility_id, scope=scope)
    payload = {
        "scope": {"company_id": company_id, "facility_id": facility_id, "scope": scope},
        "horizon": horizon,
        "data": {"months_available": len(series["points"]), "records": series.get("records", 0),
                 "latest": None if not series["points"] else f"{series['points'][-1][0][0]}-"
                                                            f"{series['points'][-1][0][1]:02d}",
                 "ready": len(series["points"]) >= MIN_MONTHS},
        "actual": [{"month": f"{y}-{m:02d}", "kg": round(v, 2)} for (y, m), v in series["points"]],
        "model": None, "forecast": [], "annual_forecast_kg": None,
        "disclaimer": "Forecasts are estimates produced by a model trained on this organisation's "
                      "own calculated records; they never replace the deterministic engine.",
    }
    if not series["points"]:
        payload["status"] = "INSUFFICIENT_DATA"
        payload["reason"] = "No calculated emissions with a reporting month yet."
        return payload
    if model is None:
        payload["status"] = "NO_ACTIVE_MODEL"
        payload["reason"] = ("No active forecast model for this scope. An administrator must train and "
                             "activate one (POST /api/ml/train then /activate).")
        return payload
    art = _load_artifact(model["artifact_path"])
    pts = [(int(y), int(m), float(v)) for y, m, v in art["points"]]
    candidate = art["candidate"]
    vals = np.array([v for _, _, v in pts], dtype=float)
    last_y, last_m = pts[-1][0], pts[-1][1]
    preds = []
    history = list(vals)
    for step in range(1, horizon + 1):
        y, m = _add_months(last_y, last_m, step)
        if candidate == "linear_trend":
            t = np.array([[art["last_t"] + step - 1]], dtype=float)
            p = float(art["model"].predict(t)[0])
        elif candidate == "gradient_boosting":
            tail = history[-6:]
            i = len(history)
            feats = [[i, np.sin(2 * np.pi * m / 12), np.cos(2 * np.pi * m / 12),
                      history[-1], history[-2], float(np.mean(tail[-3:]))]]
            p = float(art["model"].predict(np.array(feats))[0])
        else:
            p = float(history[-12]) if len(history) >= 12 else float(history[-1])
        p = max(0.0, p)
        history.append(p)
        band = 1.96 * float(art.get("residual_std_kg") or 0)
        preds.append({"month": f"{y}-{m:02d}", "kg": round(p, 2),
                      "lo_kg": round(max(0.0, p - band), 2), "hi_kg": round(p + band, 2)})
    payload["model"] = {"model_id": model["model_id"], "version": model["version"],
                        "candidate": candidate, "trained_at": model["created_at"],
                        "metrics": json.loads(model["metrics_json"] or "{}"),
                        "train_range": [model["train_date_from"], model["train_date_to"]],
                        "status": model["status"]}
    payload["status"] = "OK"
    payload["forecast"] = preds
    payload["annual_forecast_kg"] = round(float(sum(p["kg"] for p in preds[:12])), 2) \
        if horizon >= 12 else None
    if horizon < 12:
        payload["annual_forecast_kg"] = round(float(sum(p["kg"] for p in preds)) * 12 / horizon, 2)
    payload["band_note"] = ("lo/hi are ±1.96 × the model's empirical test residuals - an error band, "
                            "not a statistical confidence guarantee.")
    return payload
