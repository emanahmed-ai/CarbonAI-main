# CarbonAI API — Reference (v3)

Base URL: `http://127.0.0.1:8000` · Auth: `Authorization: Bearer <JWT>` (12 h) · JSON
(exceptions: multipart uploads, file downloads). Errors: `400` bad input · `401` auth · `403`
role/tenancy · `404` not found · `409` conflict/duplicate · `413` too large · `422` schema · `500`.

## Auth & users
| Method | Path | Roles | Notes |
|---|---|---|---|
| POST | `/api/auth/login` | public | `{username,password}` → `{token,user}`; 5 failures → 30 s lockout |
| GET | `/api/auth/me` | any | current user/scope |
| POST | `/api/auth/change-password` | any | old + new (≥8 chars) |
| GET/POST | `/api/users` | admin, head_office | list/create (create forces password change) |
| PATCH | `/api/users/{id}` | admin, head_office | role/facility/locale/active |
| POST | `/api/users/{id}/password` | admin | reset |

## Organisation
`GET/POST /api/org/companies`, `GET/POST /api/org/facilities`, `PATCH /api/org/facilities/{id}`
— admin (all) / head_office (own company). Factory users see only their facility.

## Records & calculation
| Method | Path | Notes |
|---|---|---|
| GET | `/api/records` | filters: company_id, facility_id, year, month, date_from, date_to, scope, category_key, calc_status, search, sort, direction, page, page_size |
| GET | `/api/records/meta` | categories, countries, units, unit dimensions |
| GET | `/api/records/{id}` | tenancy-checked |
| POST | `/api/records` | calculator: library factor (`factor.factor_id`) or `manual_factor`; scope override requires reason; duplicate → 409 |
| POST | `/api/records/scope-preview` | rule-based scope suggestion with missing-info list |
| POST | `/api/records/{id}/scope-override` | manual scope correction (audited) |

## Factors
| Method | Path | Roles |
|---|---|---|
| GET | `/api/factors` | any (search: country, category, status, sector, activity_like, year…) |
| GET | `/api/factors/suggest` | any — ranked candidates with reasons/exclusions |
| GET | `/api/factors/egypt` | any — Egypt + GLOBAL defaults, filters incl. `country_scope`, `sector`, `gas`, `year` |
| GET | `/api/factors/coverage-matrix` | any — 2006–2026 statuses per year |
| GET | `/api/factors/coverage` | any — per-country counts |
| GET | `/api/factors/sources`, `/gwp-sets` | any |
| GET | `/api/factors/export.csv` | admin, head_office |
| POST | `/api/factors` | **admin only** |
| POST | `/api/factors/{id}/{version}/verify` | **admin only** |
| GET | `/api/factors/audit` | admin (full log) |

## Dashboard & reports
* `GET /api/dashboard/summary` — `scopes_kpi` (share %, previous-period change only when
  comparable), `comparison`, monthly/yearly, by facility/category, top sources.
* `GET /api/dashboard/comparison?year=` — facility comparison.
* `GET /api/reports/csv`, `/monthly-csv`, `/pdf?lang=en|ar` — original exports.
* `GET /api/reports/pdf-detailed?…&lang=` — management report with **embedded charts**.
* `GET /api/reports/annual?year=&lang=` — annual report + multi-year comparison.

## Imports
`POST /api/imports/analyze` → suggestions + file hash + duplicate flag ·
`POST /api/imports/preview-mapped` (mapping JSON + factor preview per row) ·
`POST /api/imports/commit-mapped` (`force=true` to override duplicate-file block) ·
`POST /api/imports/preview|commit` (legacy template) ·
`GET /api/imports/batches`, `/template.csv`.

## Invoices
| Method | Path | Notes |
|---|---|---|
| GET | `/api/invoices` | search, year, month, status, category |
| POST | `/api/invoices` | multipart: fields + optional file; 409 on duplicate hash/metadata |
| GET | `/api/invoices/{id}` | + audit trail |
| GET | `/api/invoices/{id}/file` | authenticated document stream |
| POST | `/api/invoices/{id}/calculate` | library factor or manual factor (source required) |
| POST | `/api/invoices/{id}/void` | admin/head_office; reason required |

## Submissions & consolidated
`POST /api/submissions` (factory: own facility) · `GET /api/submissions` ·
`POST /api/submissions/{id}/review` {approve|reject, note; rejection requires note} ·
`GET /api/submissions/consolidated?year=` (approved snapshots only) ·
`GET /api/submissions/{id}/audit`.

## Plans & targets
`GET/POST/PATCH /api/plans` · `GET /api/plans/insights` (actual-data prioritisation) ·
`GET/POST /api/plans/targets` · `GET /api/plans/roadmap` (actual vs target per year).
`expected_reduction_pct` requires `reference_source` + `kpi`.

## ML
`GET /api/ml/status` · `POST /api/ml/train` (admin; forecast model, staged) ·
`GET /api/ml/models` · `POST /api/ml/models/{id}/activate` (admin) ·
`GET /api/ml/forecast?facility_id&scope&horizon=1|3|6|12` · `POST /api/ml/predict` (row estimate;
404 when no model).

## Settings & admin
`GET/PUT /api/settings` (editable: default_country, scope2_method, display_unit, org_name_*) ·
`POST /api/settings/backup` · `GET /api/settings/db-info` · `GET /api/health`.

## Scoping rules (all endpoints)
* `factory_manager`/`viewer` → own facility only; foreign ids → 403.
* `head_office` → own company, all its facilities; reviews submissions/invoices in scope.
* `admin` → everything; the only role allowed to modify factors, train/activate models, reset
  passwords, change settings.
