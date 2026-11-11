"""Intelligent spreadsheet column recognition for CSV/Excel imports.

Recognises equivalent columns across Arabic/English naming conventions instead of relying on
exact header names. Scoring combines:
    * exact normalised alias match      (score 100)
    * synonym token containment         (score 60-90)
    * fuzzy similarity (difflib)        (score up to ~60)
    * data-type / sample-value evidence (+10..25 boost; dates, numeric ratios)
The result is a SUGGESTION; the API returns confidence + alternatives and never silently
commits an ambiguous critical field - the user confirms the mapping in the UI.
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

import pandas as pd

FIELD_ALIASES: dict[str, list[str]] = {
    "activity": ["activity", "activity name", "activity description", "description", "item", "line item",
                 "النشاط", "اسم النشاط", "وصف النشاط", "البند", "البيان", "بيان"],
    "quantity": ["quantity", "qty", "consumption", "usage", "amount consumed", "consumed",
                 "الكمية", "كمية", "الاستهلاك", "استهلاك", "الكمية المستهلكة", "الكمية المستخدمة"],
    "unit": ["unit", "uom", "unit of measure", "measure", "measurement unit",
             "الوحدة", "وحدة", "وحدة القياس"],
    "date": ["date", "activity date", "invoice date", "transaction date", "period", "month",
             "التاريخ", "تاريخ النشاط", "تاريخ الفاتورة", "الفترة", "الشهر"],
    "scope": ["scope", "ghg scope", "النطاق", "نطاق", "نطاق الانبعاث"],
    "factor": ["factor", "emission factor", "ef", "co2 factor", "معامل الانبعاث", "معامل", "معامل الانبعاثات"],
    "source": ["source", "supplier", "vendor", "reference", "doc reference",
               "المصدر", "المورد", "المرجع", "اسم المورد"],
    "country": ["country", "country code", "iso", "الدولة", "كود الدولة", "البلد"],
    "company": ["company", "organization", "organisation", "entity", "الشركة", "المنشأة", "المؤسسة"],
    "facility": ["facility", "branch", "factory", "plant", "site", "location",
                 "الفرع", "المصنع", "الموقع", "المنشأة الفرعية", "الموقع/الفرع"],
    "category": ["category", "activity category", "activity type", "energy type", "الفئة", "فئة النشاط",
                 "نوع النشاط", "نوع الطاقة"],
    "fuel": ["fuel", "fuel type", "material", "الوقود", "نوع الوقود", "المادة", "نوع المادة"],
    "description": ["description", "notes", "comment", "الوصف", "ملاحظات", "تعليق"],
    "scope2_method": ["scope2 method", "scope 2 method", "طريقة النطاق الثاني", "طريقة النطاق 2"],
    "control": ["ownership", "control", "control status", "السيطرة", "الملكية", "حالة السيطرة"],
    "energy_purchased": ["energy purchased", "purchased", "مشتراة", "طاقة مشتراة"],
    "relation": ["relation", "value chain", "value chain relation", "العلاقة", "سلسلة القيمة"],
    "invoice_number": ["invoice number", "invoice no", "invoice #", "رقم الفاتورة", "رقم الفاتوره"],
    "amount": ["amount", "total", "grand total", "cost", "value", "المبلغ", "الإجمالي", "القيمة", "التكلفة"],
    "supplier": ["supplier", "vendor", "merchant", "المورد", "اسم المورد", "التاجر"],
}

CANONICAL = list(FIELD_ALIASES)
REQUIRED_FIELDS = ("activity", "quantity", "unit")
CRITICAL_AMBIGUITY = 45  # below this the mapping is flagged as ambiguous and must be confirmed

_AR_NORM = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه", "ـ": "", "ؤ": "و", "ئ": "ي"})


def normalize(text: str) -> str:
    s = unicodedata.normalize("NFKC", str(text or "")).strip().lower().translate(_AR_NORM)
    s = re.sub(r"[^\w\u0600-\u06FF]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _tokens(s: str) -> set[str]:
    return set(normalize(s).split())


def _alias_sets():
    return {f: [normalize(a) for a in aliases] for f, aliases in FIELD_ALIASES.items()}


_ALIASES = _alias_sets()


def _score_column(col: str, values: list, field: str) -> tuple[float, str] | None:
    ncol = normalize(col)
    if not ncol:
        return None
    best, how = 0.0, ""
    for a in _ALIASES[field]:
        if ncol == a:
            return 100.0, "exact synonym"
        at, ct = set(a.split()), set(ncol.split())
        if at and at <= ct:
            cand = 85.0 + min(len(at), 3)
            if cand > best:
                best, how = cand, "synonym contains"
        elif ct and ct <= at and len(ct) >= 2:
            cand = 75.0
            if cand > best:
                best, how = cand, "synonym partial"
        else:
            ratio = SequenceMatcher(None, ncol, a).ratio()
            cand = ratio * 65.0
            if cand > best and ratio >= 0.72:
                best, how = cand, "fuzzy similarity"

    # data-evidence boosts
    vals = [str(v).strip() for v in values if str(v).strip() not in ("", "nan", "None")]
    if vals:
        if field == "date":
            parsed = pd.to_datetime(pd.Series(vals), errors="coerce", dayfirst=True)
            if parsed.notna().mean() >= 0.7:
                best += 25; how = (how + " + date-like values").strip(" +")
        if field in ("quantity", "amount", "factor"):
            nums = pd.to_numeric(pd.Series(vals), errors="coerce")
            if nums.notna().mean() >= 0.8:
                best += 12; how = (how + " + numeric values").strip(" +")
        if field == "unit":
            uniq = {v.lower() for v in vals}
            if uniq and uniq <= {"kwh", "mwh", "gj", "mj", "l", "litre", "liter", "m3", "kg", "tonne",
                                 "km", "tkm", "pkm", "unit", "room_night"}:
                best += 20; how = (how + " + unit vocabulary").strip(" +")
    if best <= 0:
        return None
    return min(best, 100.0), how


def analyze(df: pd.DataFrame, *, sample_rows: int = 8) -> dict:
    """Suggest a mapping canonical_field -> column with confidence + alternatives."""
    cols = [str(c) for c in df.columns]
    values_by_col = {c: df[c].head(sample_rows).tolist() for c in cols}
    suggestions: dict[str, dict] = {}
    for field in CANONICAL:
        scored = []
        for c in cols:
            r = _score_column(c, values_by_col[c], field)
            if r:
                scored.append((r[0], c, r[1]))
        scored.sort(reverse=True)
        if not scored:
            continue
        top_score, top_col, how = scored[0]
        if top_score < 25:
            continue
        suggestions[field] = {
            "column": top_col, "confidence": round(top_score / 100.0, 2), "method": how,
            "ambiguous": top_score < CRITICAL_AMBIGUITY,
            "alternatives": [{"column": c, "confidence": round(s / 100.0, 2)} for s, c, _ in scored[1:4]],
        }
    used = [v["column"] for v in suggestions.values()]
    return {
        "columns": cols,
        "sample": {c: values_by_col[c] for c in cols},
        "suggestions": suggestions,
        "unmapped_columns": [c for c in cols if c not in used],
        "required_missing": [f for f in REQUIRED_FIELDS if f not in suggestions],
        "critical_ambiguous": [f for f, v in suggestions.items()
                               if v["ambiguous"] and f in REQUIRED_FIELDS],
    }


def apply_mapping(df: pd.DataFrame, mapping: dict[str, str]) -> tuple[pd.DataFrame, list[str]]:
    """Rename mapped source columns to canonical names. Returns (df, problems)."""
    problems = []
    inv: dict[str, str] = {}
    for field, col in (mapping or {}).items():
        if not col or col not in df.columns:
            problems.append(f"column {col!r} for {field} not found")
            continue
        inv[col] = field
    out = df.rename(columns=inv)
    missing = [f for f in REQUIRED_FIELDS if f not in out.columns]
    if missing:
        problems.append("missing required fields: " + ", ".join(missing))
    return out, problems
