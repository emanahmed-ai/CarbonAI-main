# Sources and verification log

Nothing in this build was verified against a live website (no network in the build sandbox).

| Reference | Role | Link recorded | Reachability checked | Factors loaded |
|---|---|---|---|---|
| NZ MfE "Measuring emissions" 2023 (ME 1764) | official national, NZ | none in the PDF (not invented) | n/a | 37 (UNVERIFIED) |
| GHG Protocol standards / Scope 3 / tools | methodology | see `database/seed/reference_sources.json` | no | 0 |
| IPCC EFDB, 2006 GL, 2019 Refinement | international | same file | no | 0 |
| UNFCCC inventories / NCs, IEA (licence-restricted), EEA, UK DESNZ, US EPA | various | same file | no | 0 |
| EEAA (Egypt) | national portal | homepage only: NOT evidence of any factor | no | 0 |
| KPMG handbook | methodology guidance | none | n/a | 0 |

NZ values were parsed from the supplied PDF and cross-checked with `scripts/validate_reference_data.py` (0 mismatches,
done in the earlier build). They stay `unverified` until a named reviewer promotes them in
"Emission Factors & Sources > Add/Verify". Table-3 NZ fuels are seeded with year 2021 (see known_limitations).
