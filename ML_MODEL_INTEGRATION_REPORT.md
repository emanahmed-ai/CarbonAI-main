# ML Model Integration Report

**Date:** 2026-11-11 · What exists, what was verified, and what is honestly unavailable.

## 1. Inspection result — is there a trained emissions model?

| Question | Answer |
|---|---|
| Is there a `.pkl`/model artifact inside the repository? | **No.** Full search of the project tree: none. |
| Are the PKLs found elsewhere (Downloads) usable? | **No.** They belong to unrelated sales/classification exercises (features like `lag_1`, `rolling_mean_7`, `dayofweek_sin`) and one requires `catboost`. They are not emission models and were not used. |
| Does the code contain training + prediction implementations? | **Yes** — `services/ml_model.py` (row estimate), `scripts/train_emission_model.py`, `services/forecast.py` (monthly/annual forecasting), plus APIs and an ML page. |
| Is any model shipped/active? | **No.** `models/emission_model.pkl` is absent by design; the API returns an explicit no-model status and 404s predictions instead of inventing numbers. |
| Can the existing implementations be trained on CarbonAI data? | **Yes**, from calculated ledger records. The row model needs ≥40 records; the forecasting lifecycle needs ≥12 consecutive months. |
| Do demo metrics exist? | Earlier runtime verification (now-deleted temporary DB): row model R²≈0.88 on a 60-record fixture; forecast demo (14 months, linear trend) with seasonal-naive MAE ≈ 17,018 kg. These were **demo-only**; no artifact ships and no metric is claimed for production. |

## 2. What was reused (not replaced)

* The existing row-estimate registry format (`carbonai.ml/1`), loader, feature contract and
  `/api/ml/predict` behaviour.
* The existing forecasting lifecycle: dataset fingerprint, chronological split, seasonal-naive
  baseline comparison, staged→admin activation, `/api/ml/forecast` with error band.
* Training scripts (`scripts/train_emission_model.py`) and APIs; no new algorithm was introduced
  for the sake of it.

## 3. Inputs, target, features

* **Row model** — target kg CO₂e per record; features: quantity, month, one-hot category, scope,
  unit dimension (exact order stored in the bundle).
* **Forecast** — target monthly kg CO₂e; features: time index, sin/cos month, lag1, lag2,
  rolling-mean 3; chronological holdout; candidates: seasonal naive, linear trend, gradient
  boosting; the best test MAE wins (baseline reported alongside).
* Data source: `activity_records` with `calc_status='calculated'` only; gaps are not filled with
  zeros and the contiguous window stops at the first gap.

## 4. Guardrails verified by tests

* Insufficient data → 409 `INSUFFICIENT_DATA` with months available and the requirement.
* No active model → forecasts return `NO_ACTIVE_MODEL`; predictions never fabricated.
* Training/activation are admin-only (403 otherwise).
* Retraining with an unchanged dataset fingerprint is skipped (`skipped: true`).
* Predictions are never written to the ledger and are labelled as estimates; plan results use
  measured records only.

## 5. How to run (operations)

```
# row-estimate model (≥40 calculated records)
python scripts\train_emission_model.py

# forecasting lifecycle (admin, ≥12 consecutive months)
POST /api/ml/train            {"facility_id": null, "scope": null, "force": false}
GET  /api/ml/models
POST /api/ml/models/{id}/activate
GET  /api/ml/forecast?horizon=1|3|6|12
```

## 6. Limitations

* With 12–24 monthly points only simple candidates are competitive; the model is univariate
  (no production volume/weather drivers — those columns do not exist yet).
* No production model exists until the organisation trains one; this is the correct state, not an
  omission to be faked.
* The earlier demo artifact was deleted so nothing trained on synthetic fixtures ships.
