"""Train the CarbonAI emission estimation model from the organisation's own ledger data.

What it does
    * Reads CALCULATED activity records from the local database (needs >= 40 rows; refuses otherwise).
    * Builds features: quantity, month, one-hot category/scope/unit-dimension (aligned with
      services.ml_model.feature_names).
    * Trains a GradientBoostingRegressor on a stratified-ish 80/20 split, reports MAE / R2.
    * Saves the bundle to models/emission_model.pkl (+ human-readable meta JSON).

Usage:
    python scripts/train_emission_model.py            # uses data/carbonai.db (or CARBONAI_DB_PATH)
    python scripts/train_emission_model.py --min-rows 60

The model NEVER replaces the deterministic engine; it only powers the ML estimate endpoints.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from db.connection import connect  # noqa: E402
from services import ledger as L  # noqa: E402
from services import ml_model as M  # noqa: E402

MIN_ROWS_DEFAULT = 40


def build_dataset(con) -> pd.DataFrame:
    df = L.fetch_records(con)
    df = df[df["calc_status"] == "calculated"].copy()
    df = df[df["kg"].notna()]
    out = pd.DataFrame({
        "quantity": pd.to_numeric(df["quantity"], errors="coerce"),
        "unit": df["unit"].astype(str),
        "category_key": df["category_key"].fillna("other").astype(str),
        "scope": df["scope"].fillna("unscoped").astype(str),
        "activity_month": df["activity_month"],
        "y": df["kg"].astype(float),
    })
    return out.dropna(subset=["quantity", "y"])


def train(*, min_rows: int = MIN_ROWS_DEFAULT, seed: int = 42) -> dict:
    con = connect()
    try:
        data = build_dataset(con)
    finally:
        con.close()
    if len(data) < min_rows:
        return {"ok": False,
                "reason": f"only {len(data)} calculated records with known emissions; need at least {min_rows}. "
                          "Enter/collect more data first - the model must learn from real records."}

    cat_maps = {
        "category_key": sorted(data["category_key"].unique().tolist()),
        "scope": sorted(data["scope"].unique().tolist()),
        "unit_dimension": sorted({M.unit_dimension(u) for u in data["unit"].unique()}),
    }
    feats = M.feature_names(cat_maps["category_key"], cat_maps["scope"], cat_maps["unit_dimension"])

    def row_to_x(r) -> list[float]:
        row = {"quantity": r.quantity, "unit": r.unit, "category_key": r.category_key,
               "scope": r.scope, "activity_month": r.activity_month}
        return M.vectorize(row, {"features": feats, "categorical_maps": cat_maps})

    X = pd.DataFrame([row_to_x(r) for r in data.itertuples()], columns=feats)
    y = data["y"].to_numpy()

    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.metrics import mean_absolute_error, r2_score
    from sklearn.model_selection import train_test_split

    test_n = max(2, int(len(X) * 0.2))
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=test_n, random_state=seed)
    model = GradientBoostingRegressor(random_state=seed)
    model.fit(X_tr, y_tr)
    pred = model.predict(X_te)
    metrics = {"mae_kg": round(float(mean_absolute_error(y_te, pred)), 3),
               "r2": round(float(r2_score(y_te, pred)), 4),
               "test_rows": int(len(y_te)), "train_rows": int(len(y_tr))}
    path = M.save_bundle(model, features=feats, categorical_maps=cat_maps, metrics=metrics,
                         train_rows=int(len(X)),
                         notes="Trained from this organisation's calculated ledger records. "
                               "Estimates only; the deterministic engine stays authoritative.")
    return {"ok": True, "path": str(path), "rows": int(len(X)), "features": feats,
            "metrics": metrics}


def main() -> int:
    ap = argparse.ArgumentParser(description="Train the CarbonAI emission estimation model")
    ap.add_argument("--min-rows", type=int, default=MIN_ROWS_DEFAULT)
    args = ap.parse_args()
    result = train(min_rows=args.min_rows)
    if result["ok"]:
        print("Model trained and saved:", result["path"])
        print("Rows:", result["rows"], "| metrics:", result["metrics"])
        return 0
    print("Training refused:", result["reason"])
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
