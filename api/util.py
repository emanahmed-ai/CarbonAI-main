"""JSON-safe serialization helpers (Decimal -> str keeps exactness; the frontend formats)."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

import pandas as pd


def jsonable(v: Any) -> Any:
    if isinstance(v, Decimal):
        return format(v, "f")
    if isinstance(v, (pd.Timestamp, )):
        return v.isoformat()
    if isinstance(v, bytes):
        return v.decode("utf-8", "replace")
    if isinstance(v, dict):
        return {k: jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [jsonable(x) for x in v]
    return v


def row_dict(r) -> dict:
    return {k: jsonable(v) for k, v in dict(r).items()}


def rows_list(rows) -> list[dict]:
    return [row_dict(r) for r in rows]


def df_records(df: pd.DataFrame) -> list[dict]:
    if df is None or df.empty:
        return []
    out = []
    for _, r in df.iterrows():
        d = {}
        for k, v in r.items():
            if k == "kg":
                continue
            if v is None or (isinstance(v, float) and pd.isna(v)) or (not isinstance(v, (list, dict, str, int, float, bool)) and pd.isna(v)):
                d[k] = None
            else:
                d[k] = jsonable(v)
        out.append(d)
    return out
