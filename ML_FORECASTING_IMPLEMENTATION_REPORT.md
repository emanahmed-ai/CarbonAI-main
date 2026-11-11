# ML Forecasting — Implementation Report

**Date:** 2026-11-03 · **Status:** lifecycle complete and verified; **no production model ships**
(by design — a model exists only after an administrator trains it on real ledger data).

## 1. What existed before this round (verified, not assumed)

* `services/ml_model.py` — row-level estimate registry (`models/emission_model.pkl`), honest
  "no model loaded" behaviour, 404 instead of fake predictions.
* `scripts/train_emission_model.py` — trains a GradientBoosting regressor from calculated
  ledger records (≥40 rows), saves a versioned bundle + meta JSON.
* `/api/ml/status`, `/api/ml/predict`; the ML page showed status + row prediction.
* **No forecast capability existed.** No PKL model was ever present in the repository (the PKLs
  found in `Downloads/` belong to unrelated sales exercises — verified by inspecting their
  feature sets).

## 2. What was added: monthly/annual forecasting lifecycle

### Dataset preparation (`services/forecast.py`)
* Aggregates **calculated** ledger records per (year, month), scoped to facility/company/scope.
* Requires **≥ 12 consecutive months**; missing months are gaps, never zeros; the window stops at
  the first gap so the model sees a continuous timeline.
* Insufficient data → `{"ok": false, "status": "INSUFFICIENT_DATA", "reason": "...", "months_available": N}`
  (the UI and API surface exactly what is missing).

### Evaluation (chronological, baseline-compared)
* Holdout = last 20% of the series (min 3 points), **never shuffled** (no data leakage).
* Candidates: **seasonal naive** (y[t−12], the mandatory baseline), **linear trend**, **gradient
  boosting** on time/lag features (`t`, month sin/cos, lag1, lag2, rolling mean 3).
* Metrics: MAE, RMSE, R² (null when the test set is constant), residual std for the error band.
* The candidate with the lowest test MAE wins; if none beats the seasonal naive, **the naive
  model is selected** (documented in `notes`).

### Registry & activation (`model_registry` table)
* Each training run stores: name (`monthly_forecast:facility:<id>` / `:company:<id>` / `:org` /
  scope suffix), version, artifact path, **dataset fingerprint** (SHA-256 of the series + config),
  date range, record count, features, config, full metrics JSON, status (`staged|active|archived`),
  trainer, approver.
* Training creates a **staged** model. Only an admin can **activate** it; activation archives the
  previous active version. Rollback = activate an older version.
* Retraining with an **unchanged dataset fingerprint** returns `{skipped: true}` — the system
  never retrains on every page load. `force=true` allows a deliberate retrain.
* **Prediction never trains.** `/ml/forecast` only reads the active model artifact.

### Forecast output
* Horizons 1/3/6/12 months; monthly series + annual forecast (sum of the next 12 months, or
  horizon-scaled when shorter — labelled as such).
* Error band = ±1.96 × residual std, explicitly described as **an empirical error band, not a
  statistical confidence guarantee**.
* Scoping: factory users → own facility only; head office → own company; consolidated forecasts
  are built from company-level totals (no double counting). Historical actuals and future
  predictions are visually separated (solid vs dashed line).

## 3. Verified behaviour (automated tests)

`tests/unit/test_api_v3.py::ForecastLifecycle`:
* insufficient data → 409 `INSUFFICIENT_DATA` with reason and months count;
* train → `staged` v1 with metrics for all candidates;
* forecast before activation → `NO_ACTIVE_MODEL` (nothing fabricated);
* activate → forecast 6 months, model id matches, annual forecast present, band note present;
* immediate retrain → `skipped: true`;
* factory manager → 403 on train/activate.

Manual demo run (temporary DB, 14 months of daily-path records, then deleted): model
`linear_trend` v1, **baseline (seasonal-naive) MAE 17,018 kg**, annual forecast ≈ 1,055,792 kg.
The demo DB was removed — **no artifact from demo data ships in the repository**.

## 4. Honest limitations

* With 12–24 monthly points, only non-seasonal models are typically competitive; the gradient
  boosting candidate activates only with ≥ 20 lag-complete rows.
* The forecast is univariate (monthly totals). Production volume, weather or fuel-price drivers
  would require additional historical columns that do not exist yet.
* Annual forecasts are sums of monthly predictions (with the same error band note), not a
  separate annual model.
* No production model can exist until the organisation accumulates ≥ 12 months of calculated
  emissions and an admin trains + activates one.

## 5. Admin runbook

```
POST /api/ml/train        {"facility_id": null, "scope": null, "force": false}   # admin
GET  /api/ml/models                                                              # admin/head office
POST /api/ml/models/{id}/activate                                                # admin
GET  /api/ml/forecast?horizon=12                                                 # scoped by role
```
CLI equivalent for the row-estimate model: `python scripts\train_emission_model.py`.
