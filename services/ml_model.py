"""Emission ML model registry: loads, validates and serves a trained model bundle.

There is NO model file shipped with the project (nothing to fake): when models/emission_model.pkl
is absent every function degrades explicitly (registry returns {'loaded': False}), and the API
answers with 404-style payloads instead of invented predictions.

A model bundle is a versioned dict produced by scripts/train_emission_model.py:
    {
      "format": "carbonai.ml/1",
      "model": <sklearn-compatible estimator with .predict(X)>,
      "features": ["quantity", ...one-hot columns...],   # exact order expected by the model
      "categorical_maps": {"category_key": [...], "scope": [...], "unit_dimension": [...]},
      "target": "kg_co2e",
      "metrics": {"mae_kg": float, "r2": float},
      "trained_at": iso, "train_rows": int, "sklearn_version": str,
      "notes": str
    }
Predictions are estimates for planning/anomaly-spotting only; they never replace the
deterministic factor-based calculation engine and are never written to the ledger.
"""
from __future__ import annotations

import json
import pickle
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL_DIR = Path(__file__).resolve().parent.parent / "models"
BUNDLE_PATH = MODEL_DIR / "emission_model.pkl"
META_PATH = MODEL_DIR / "emission_model_meta.json"

UNIT_DIMENSIONS = {  # same families as services.unit_conversion
    "kg": "mass", "g": "mass", "tonne": "mass", "t": "mass",
    "litre": "volume", "l": "volume", "ml": "volume", "m3": "volume",
    "kwh": "energy", "mwh": "energy", "mj": "energy", "gj": "energy",
    "km": "distance", "m": "distance", "mile": "distance",
    "pkm": "passenger_distance", "tkm": "freight_distance",
    "room_night": "room_night", "unit": "count",
}
SCOPES = ("Scope 1", "Scope 2", "Scope 3")


def unit_dimension(unit: str) -> str:
    return UNIT_DIMENSIONS.get((unit or "").strip().lower(), "other")


def registry_status() -> dict:
    """What is loaded right now - used by GET /api/ml/status. Never claims a model that is absent."""
    if not BUNDLE_PATH.exists():
        return {"loaded": False, "path": str(BUNDLE_PATH),
                "reason": "No trained model file found. Train one with scripts/train_emission_model.py "
                          "once enough calculated records exist."}
    try:
        bundle = _load_bundle()
        return {"loaded": True, "path": str(BUNDLE_PATH), "format": bundle.get("format"),
                "target": bundle.get("target"), "features": bundle.get("features"),
                "metrics": bundle.get("metrics"), "trained_at": bundle.get("trained_at"),
                "train_rows": bundle.get("train_rows"), "sklearn_version": bundle.get("sklearn_version"),
                "notes": bundle.get("notes")}
    except Exception as e:  # corrupt file, sklearn version drift, ...
        return {"loaded": False, "path": str(BUNDLE_PATH), "reason": f"Model file present but not loadable: {e}"}


def _load_bundle() -> dict:
    with open(BUNDLE_PATH, "rb") as fh:
        bundle = pickle.load(fh)
    if not isinstance(bundle, dict) or bundle.get("format") != "carbonai.ml/1":
        raise ValueError("unsupported bundle format (expected carbonai.ml/1)")
    if not hasattr(bundle.get("model"), "predict") or not bundle.get("features"):
        raise ValueError("bundle is missing a predict()-capable model or its feature list")
    return bundle


def feature_names(category_values: list[str], scope_values: list[str],
                  dimension_values: list[str]) -> list[str]:
    return (["quantity", "month"]
            + [f"category={c}" for c in category_values]
            + [f"scope={s}" for s in scope_values]
            + [f"dim={d}" for d in dimension_values])


def vectorize(row: dict, bundle: dict) -> list[float]:
    """row: {quantity, unit, category_key, scope, activity_month}. Unknown categorical values map to
    all-zero one-hot columns (documented behaviour; the model still sees quantity/month/dimension)."""
    feats = bundle["features"]
    maps = bundle.get("categorical_maps", {})
    vec = dict.fromkeys(feats, 0.0)
    vec["quantity"] = float(row.get("quantity") or 0)
    m = row.get("activity_month")
    vec["month"] = float(m) if m else 0.0
    for col, value in (("category_key", row.get("category_key")),
                       ("scope", row.get("scope")),
                       ("unit_dimension", unit_dimension(row.get("unit")))):
        for v in maps.get(col, []):
            key = f"{col.replace('_key','')}={v}" if col != "unit_dimension" else f"dim={v}"
            if key in vec and value == v:
                vec[key] = 1.0
    return [vec[f] for f in feats]


def predict(row: dict) -> dict:
    """One-row prediction. Raises FileNotFoundError when no model is loaded (caller decides the HTTP
    answer); returns estimate + the model's identity, never a stored/authoritative result."""
    bundle = _load_bundle()
    x = [vectorize(row, bundle)]
    pred = float(bundle["model"].predict(x)[0])
    return {"predicted_kg_co2e": max(0.0, round(pred, 3)),
            "predicted_t_co2e": round(max(0.0, pred) / 1000.0, 6),
            "model": {"trained_at": bundle.get("trained_at"), "train_rows": bundle.get("train_rows"),
                      "metrics": bundle.get("metrics")},
            "disclaimer": "ML estimate for planning/anomaly review only; never a substitute for the "
                          "factor-based calculation engine."}


def save_bundle(model, *, features: list[str], categorical_maps: dict, metrics: dict,
                train_rows: int, notes: str = "") -> Path:
    """Persist a trained bundle + a human-readable meta JSON sidecar."""
    import sklearn
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    bundle = {"format": "carbonai.ml/1", "model": model, "features": features,
              "categorical_maps": categorical_maps, "target": "kg_co2e",
              "metrics": metrics, "trained_at": datetime.now().isoformat(timespec="seconds"),
              "train_rows": train_rows, "sklearn_version": sklearn.__version__, "notes": notes}
    tmp = BUNDLE_PATH.with_suffix(".pkl.tmp")
    with open(tmp, "wb") as fh:
        pickle.dump(bundle, fh)
    tmp.replace(BUNDLE_PATH)
    META_PATH.write_text(json.dumps({k: v for k, v in bundle.items() if k != "model"},
                                    indent=2, ensure_ascii=False), encoding="utf-8")
    return BUNDLE_PATH
