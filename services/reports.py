"""CSV and PDF reports. Same filters + same ledger.summarize() as the Dashboard."""
from __future__ import annotations

import io
import os
from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd

from services import ledger as L

CSV_COLUMNS = [  # (internal column, Arabic header)
    ("activity_date", "تاريخ النشاط"), ("activity_month", "الشهر"), ("activity_year", "السنة"),
    ("country_code", "الدولة"), ("company_name", "الشركة"), ("facility_name", "الفرع"),
    ("activity_name", "النشاط"), ("industry_sector", "القطاع"), ("scope", "النطاق"),
    ("scope_subcategory", "الفئة الفرعية"), ("scope_status", "حالة تصنيف النطاق"),
    ("quantity", "الكمية"), ("unit", "الوحدة"), ("factor_value", "معامل الانبعاث"), ("factor_unit", "وحدة المعامل"),
    ("kg_co2e", "الانبعاثات (kg CO2e)"), ("t_co2e", "الانبعاثات (tonne CO2e)"),
    ("factor_source", "مصدر المعامل"), ("factor_source_url", "رابط المرجع"),
    ("factor_class", "نوع المعامل"), ("factor_verification", "حالة التحقق من المعامل"),
    ("calc_status", "حالة الحساب"), ("calc_notes", "ملاحظات الحساب"),
]


def period_label(year=None, month=None, date_from=None, date_to=None) -> str:
    if date_from or date_to:
        return f"{date_from or 'start'}_to_{date_to or 'end'}"
    if year and month:
        return f"{year}-{int(month):02d}"
    return str(year) if year else "all-periods"


def report_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame({ar: df[c] if c in df.columns else "" for c, ar in CSV_COLUMNS})
    return out


def csv_bytes(df: pd.DataFrame) -> bytes:
    return report_dataframe(df).to_csv(index=False).encode("utf-8-sig")


def monthly_summary_df(df: pd.DataFrame) -> pd.DataFrame:
    s = L.summarize(df)
    rows = []
    for (y, m), kg in s["monthly_kg"].items():
        sub = df[(df["calc_status"] == "calculated") & (df["activity_year"] == y) & (df["activity_month"] == m)]
        row = {"السنة": y, "الشهر": m, "الإجمالي (kg CO2e)": str(kg), "الإجمالي (tonne CO2e)": str(kg / 1000)}
        for sc in ("Scope 1", "Scope 2", "Scope 3"):
            row[f"{sc} (kg CO2e)"] = str(L._sum(sub.loc[sub["scope"] == sc, "kg"]))
        rows.append(row)
    return pd.DataFrame(rows)


def csv_filename(kind: str, *, year=None, month=None, date_from=None, date_to=None) -> str:
    return f"carbonai_{kind}_{period_label(year, month, date_from, date_to)}.csv"


# ------------------------------------------------------------------ PDF
def _find_font() -> str | None:
    env = os.environ.get("CARBONAI_FONT")
    cands = [env] if env else []
    cands += [r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\tahoma.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/Library/Fonts/Arial.ttf",
              "/System/Library/Fonts/Supplemental/Arial.ttf"]
    return next((c for c in cands if c and Path(c).exists()), None)


def arabic_pdf_supported() -> tuple[bool, str]:
    try:
        import arabic_reshaper  # noqa: F401
        from bidi.algorithm import get_display  # noqa: F401
    except ImportError:
        return False, "Install 'arabic-reshaper' and 'python-bidi' for Arabic PDF text."
    if _find_font() is None:
        return False, "No Arabic-capable TTF font found (set CARBONAI_FONT to a .ttf path)."
    return True, ""


class PdfUnavailable(RuntimeError):
    pass


def pdf_bytes(df: pd.DataFrame, *, title_company="", title_facility="", country="", period="", lang="en") -> bytes:
    """lang='ar' needs arabic-reshaper + python-bidi + a TTF font; otherwise raises PdfUnavailable
    (caller shows a message - the app never crashes). lang='en' uses the built-in Helvetica unless a TTF exists."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError as e:  # pragma: no cover
        raise PdfUnavailable("reportlab is not installed") from e

    ar = lang == "ar"
    font = "Helvetica"
    if ar:
        ok, why = arabic_pdf_supported()
        if not ok:
            raise PdfUnavailable(why)
        import arabic_reshaper
        from bidi.algorithm import get_display
        pdfmetrics.registerFont(TTFont("CarbonFont", _find_font()))
        font = "CarbonFont"
        shape = lambda t: get_display(arabic_reshaper.reshape(str(t)))
    else:
        shape = lambda t: str(t)

    T = {  # (en, ar)
        "title": ("CarbonAI Carbon Emissions Report", "تقرير انبعاثات الكربون - CarbonAI"),
        "company": ("Company", "الشركة"), "facility": ("Facility", "الفرع"), "country": ("Country", "الدولة"),
        "period": ("Period", "الفترة"), "generated": ("Generated on", "تاريخ الإنشاء"),
        "total": ("Total emissions", "إجمالي الانبعاثات"), "scopes": ("By scope", "التوزيع حسب النطاق"),
        "monthly": ("Monthly summary", "الملخص الشهري"), "details": ("Activity details", "تفاصيل الأنشطة"),
        "status": ("Data verification status", "حالة التحقق من البيانات"),
        "notes": ("Assumptions and limitations", "الافتراضات والقيود"),
    }
    t = lambda k: shape(T[k][1 if ar else 0])
    align = 2 if ar else 0
    st = ParagraphStyle("b", fontName=font, fontSize=9, leading=12, alignment=align)
    h1 = ParagraphStyle("h1", fontName=font, fontSize=16, leading=20, alignment=align)
    h2 = ParagraphStyle("h2", fontName=font, fontSize=12, leading=15, alignment=align, spaceBefore=8)

    s = L.summarize(df)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=24, rightMargin=24, topMargin=24, bottomMargin=24,
                            title="CarbonAI report")
    el = [Paragraph(t("title"), h1), Spacer(1, 6)]
    meta = [(t("company"), title_company or "-"), (t("facility"), title_facility or "-"),
            (t("country"), country or "-"), (t("period"), period or "-"),
            (t("generated"), date.today().isoformat())]
    el.append(Table([[Paragraph(shape(v), st), Paragraph(k, st)] if ar else [Paragraph(k, st), Paragraph(shape(v), st)]
                     for k, v in meta], colWidths=[140, 300]))
    el += [Spacer(1, 6), Paragraph(t("total"), h2),
           Paragraph(f"{s['total_kg']:,.3f} kg CO2e  /  {s['total_t']:,.6f} tonne CO2e", st)]
    el += [Paragraph(t("scopes"), h2),
           Paragraph(" | ".join(f"{k}: {v:,.3f} kg" for k, v in s["by_scope_kg"].items())
                     + (f" | Unscoped: {s['unscoped_kg']:,.3f} kg" if s["unscoped_kg"] else ""), st)]
    if s["monthly_kg"]:
        el.append(Paragraph(t("monthly"), h2))
        data = [["Year-Month", "kg CO2e", "tonne CO2e"]] + [[f"{y}-{m:02d}", f"{v:,.3f}", f"{v/1000:,.6f}"]
                                                            for (y, m), v in s["monthly_kg"].items()]
        tb = Table(data, repeatRows=1, colWidths=[100, 120, 120])
        tb.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), font), ("FONTSIZE", (0, 0), (-1, -1), 8),
                                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#123d2b")),
                                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey)]))
        el.append(tb)
    el.append(Paragraph(t("details"), h2))
    hdr = ["Date", "Activity", "Scope", "Qty", "Unit", "Factor", "kg CO2e", "Factor source", "Status"]
    rows = [hdr]
    for _, r in df.iterrows():
        rows.append([shape(x) if ar else str(x) for x in (
            r["activity_date"] or "-", (r["activity_name"] or "")[:28], r["scope"] or "TBD", r["quantity"], r["unit"],
            f"{r['factor_value'] or '-'} {r['factor_unit'] or ''}".strip(), r["kg_co2e"] or "-",
            (r["factor_source"] or "")[:30], f"{r['calc_status']}/{r['factor_verification'] or '-'}")])
    tb = Table(rows, repeatRows=1, colWidths=[55, 120, 45, 45, 35, 95, 60, 130, 120], splitByRow=1)
    tb.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), font), ("FONTSIZE", (0, 0), (-1, -1), 7),
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#123d2b")),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f6f3")]),
                            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    el.append(tb)
    el.append(Paragraph(t("status"), h2))
    pct = "n/a" if s["verified_pct"] is None else f"{s['verified_pct']:.1f}%"
    el.append(Paragraph(f"Records: {s['records']} | calculated: {s['calculated']} | with verified factor: "
                        f"{s['verified_factor_records']} ({pct}; {s['verified_pct_definition']}) | "
                        f"not calculated / needs review: {s['needs_review']}", st))
    el.append(Paragraph(t("notes"), h2))
    el.append(Paragraph("Totals include only calculated records. Records that need a factor, date or review are listed "
                        "but are not counted as zero. Factors flagged unverified, user-supplied or proxy are estimates. "
                        "Scope assignments marked 'suggested' were derived by rules and should be reviewed.", st))
    doc.build(el)
    return buf.getvalue()
