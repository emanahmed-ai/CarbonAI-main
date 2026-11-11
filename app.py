import io
import csv
from datetime import date
from decimal import Decimal

import pandas as pd
import plotly.express as px
import streamlit as st

# =========================================================
# CarbonAI - Global Carbon Footprint Platform
# Original prototype UI preserved; persistent SQLite layer, scope classifier,
# factor library, monthly/annual accounting, import and reports added on top.
# NOTE: emission factors in the library are UNVERIFIED until a named reviewer
# promotes them. Demo rows below are illustrative only.
# =========================================================
from db.connection import backup_file, connect, db_path
from db.schema import init_db
from db.seed import seed_all
from db.reference_data import SCOPE3_CATEGORIES
from services import factor_library as FL
from services import importer as IM
from services import ledger as L
from services import library_update as LU
from services import reports as RP
from services import unit_conversion as uc

st.set_page_config(
    page_title="CarbonAI | Carbon Management",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------- Theme ----------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Cairo', sans-serif;
}
.stApp {
    background: #f5f8f5;
}
[data-testid="stSidebar"] {
    background: #123d2b;
}
[data-testid="stSidebar"] * {
    color: #ffffff !important;
}
[data-testid="stSidebar"] .stRadio label {
    padding: 7px 4px;
}
.hero {
    background: linear-gradient(120deg, #123d2b, #28734c);
    padding: 25px 28px;
    border-radius: 18px;
    color: white;
    margin-bottom: 20px;
}
.hero h1 {
    color: white;
    margin: 0;
    font-size: 30px;
}
.hero p {
    color: #e0f0e5;
    margin: 8px 0 0;
}
.kpi {
    background: white;
    padding: 18px;
    border-radius: 15px;
    border: 1px solid #e3ebe5;
    min-height: 128px;
}
.kpi-label {
    color: #627368;
    font-size: 14px;
}
.kpi-value {
    color: #173d2b;
    font-size: 27px;
    font-weight: 800;
    margin: 8px 0 3px;
}
.kpi-note {
    color: #68796e;
    font-size: 12px;
}
.section-title {
    color: #173d2b;
    font-size: 21px;
    font-weight: 800;
    margin: 12px 0;
}
.recommendation {
    background: #ffffff;
    border: 1px solid #e2ebe3;
    border-right: 4px solid #399568;
    border-radius: 12px;
    padding: 14px;
    margin-bottom: 10px;
}
.small-muted {
    color: #65756a;
    font-size: 12px;
}
div.stButton > button {
    border-radius: 9px;
}
</style>
""", unsafe_allow_html=True)

# ---------- Session state (original keys preserved) ----------
if "activities" not in st.session_state:
    st.session_state.activities = pd.DataFrame([
        {
            "النشاط": "استهلاك الكهرباء",
            "النطاق": "Scope 2",
            "الكمية": 12000.0,
            "الوحدة": "kWh",
            "معامل الانبعاث": 0.45,
            "المصدر": "عامل تجريبي للواجهة",
        },
        {
            "النشاط": "وقود الديزل",
            "النطاق": "Scope 1",
            "الكمية": 800.0,
            "الوحدة": "L",
            "معامل الانبعاث": 2.68,
            "المصدر": "عامل تجريبي للواجهة",
        },
        {
            "النشاط": "النقل والشحن",
            "النطاق": "Scope 3",
            "الكمية": 1500.0,
            "الوحدة": "km",
            "معامل الانبعاث": 0.12,
            "المصدر": "عامل تجريبي للواجهة",
        },
    ])
st.session_state.setdefault("legacy_saved_to_db", False)

# ---------- Database (additive init; never resets; failure does not stop the app) ----------
DB_ERROR = None
con = None
try:
    con = connect()
    if not st.session_state.get("_db_ready"):
        init_db(con)
        seed_all(con)          # INSERT OR IGNORE only
        st.session_state["_db_ready"] = True
except Exception as exc:       # the app keeps working in session-only mode
    DB_ERROR = str(exc)
    con = None

# ---------- Sidebar ----------
with st.sidebar:
    st.markdown("# 🌿 CarbonAI")
    st.caption("GLOBAL CARBON MANAGEMENT")
    st.divider()

    language = st.selectbox("اللغة / Language", ["العربية", "English"])
    is_en = language == "English"

    if is_en:
        menu_options = [
            "Dashboard",
            "Carbon Calculator",
            "Data Entry & Imports",
            "Invoices & Documents",
            "Emission Factors & Sources",
            "Companies & Facilities",
            "Reports",
            "Reduction Plans",
            "Settings",
        ]
        page = st.radio("MAIN MENU", menu_options)
        st.divider()
        st.caption("v0.2 (database layer added)")
    else:
        menu_options = [
            "لوحة التحكم",
            "حساب البصمة الكربونية",
            "إدخال البيانات والاستيراد",
            "الفواتير والمستندات",
            "معاملات الانبعاثات والمراجع",
            "الشركات والفروع",
            "التقارير",
            "خطط خفض الانبعاثات",
            "الإعدادات",
        ]
        page = st.radio("القائمة الرئيسية", menu_options)
        st.divider()
        st.caption("نسخة v0.2 (أُضيفت طبقة قاعدة البيانات)")

    if con is not None:
        st.markdown(
            '<div style="background:#24543d;padding:12px;border-radius:10px;font-size:12px">'
            '💾 السجلات المحفوظة عبر قاعدة البيانات تبقى بعد إعادة التشغيل. '
            'صفوف العرض السريع (الجلسة) مؤقتة.</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div style="background:#7a3b1d;padding:12px;border-radius:10px;font-size:12px">'
            '⚠️ قاعدة البيانات غير متاحة؛ التطبيق يعمل داخل الجلسة فقط.</div>',
            unsafe_allow_html=True,
        )


def tr(ar, en):
    return en if is_en else ar


if DB_ERROR:
    st.error(f"تعذر فتح قاعدة البيانات / Database unavailable: {DB_ERROR}")

# ---------- Reference lookups ----------
COUNTRY_ROWS = []
if con is not None:
    COUNTRY_ROWS = con.execute(
        "SELECT iso2_code, country_name_ar, country_name_en FROM countries WHERE is_active=1 "
        "ORDER BY country_name_en").fetchall()
ISO_BY_AR = {r["country_name_ar"]: r["iso2_code"] for r in COUNTRY_ROWS}
LABEL_BY_ISO = {r["iso2_code"]: (r["country_name_en"] if is_en else r["country_name_ar"]) for r in COUNTRY_ROWS}
CATEGORY_ROWS = con.execute("SELECT * FROM activity_categories ORDER BY name_en").fetchall() if con else []
CAT_LABEL = {r["category_key"]: (r["name_en"] if is_en else r["name_ar"]) for r in CATEGORY_ROWS}


def get_setting(key, default=None):
    if con is None:
        return default
    r = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return r["value"] if r else default


def set_setting(key, value):
    if con is not None:
        con.execute("INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (key, str(value)))
        con.commit()


def legacy_frame(df):
    """Original session rows -> same shape as ledger.fetch_records (undated, user-supplied, unverified)."""
    rows = []
    for _, r in df.iterrows():
        qty = pd.to_numeric(r["الكمية"], errors="coerce")
        fac = pd.to_numeric(r["معامل الانبعاث"], errors="coerce")
        if pd.isna(qty) or pd.isna(fac):
            continue
        kg = Decimal(str(qty)) * Decimal(str(fac))
        rows.append({
            "activity_name": r["النشاط"], "scope": r["النطاق"], "quantity": str(qty), "unit": r["الوحدة"],
            "factor_value": str(fac), "factor_source": r.get("المصدر", ""), "kg_co2e": str(kg), "kg": kg,
            "t_co2e": str(kg / 1000), "calc_status": "calculated", "scope_status": "confirmed",
            "factor_verification": "unverified", "factor_class": "user_supplied", "activity_year": None,
            "activity_month": None, "activity_date": None, "origin": "session",
        })
    out = pd.DataFrame(rows)
    return out


def money_unit(kg: Decimal):
    """Display value according to the saved Settings unit."""
    if get_setting("display_unit", "tonne") == "kg":
        return f"{kg:,.3f}", "kg CO₂e"
    return f"{kg / 1000:,.3f}", "طن CO₂e"


# ---------- Header ----------
if is_en:
    st.markdown("""
    <div class="hero">
        <h1>🌿 CarbonAI Dashboard</h1>
        <p>Global carbon accounting, source traceability and reduction planning</p>
    </div>
    """, unsafe_allow_html=True)
else:
    st.markdown("""
    <div class="hero">
        <h1>🌿 منصة CarbonAI للبصمة الكربونية</h1>
        <p>قياس الانبعاثات، توثيق المراجع، ومتابعة فرص خفض الكربون</p>
    </div>
    """, unsafe_allow_html=True)

if is_en:
    st.warning(
        "Demo rows and user-typed factors are illustrative. Library factors are UNVERIFIED until a named "
        "reviewer verifies them. No Egyptian or other Arab-country factor is loaded yet."
    )
else:
    st.warning(
        "صفوف العرض والمعاملات المُدخلة يدويًا للتوضيح فقط. معاملات المكتبة «غير متحقق منها» إلى أن يعتمدها "
        "مراجع مسمّى. لم يتم تحميل أي معامل مصري أو عربي بعد."
    )

# ---------- Common filters ----------
ALL = tr("الكل", "All")
company_rows = con.execute("SELECT company_id, name FROM companies ORDER BY name").fetchall() if con else []
company_names = ["شركة تجريبية", "مصنع تجريبي", "مؤسسة تجريبية"] + [r["name"] for r in company_rows]
company_id_by_name = {r["name"]: r["company_id"] for r in company_rows}

f1, f2, f3 = st.columns(3)

with f1:
    company = st.selectbox(
        "الشركة / Company",
        [ALL] + company_names,
    )

with f2:
    country_labels = [ALL] + [
        "مصر", "السعودية", "الإمارات", "الأردن", "المغرب",
        "ألمانيا", "فرنسا", "المملكة المتحدة", "الولايات المتحدة",
        "الهند", "نيوزيلندا", "أخرى",
    ]
    country = st.selectbox("الدولة / Country", country_labels)

with f3:
    report_year = st.selectbox(
        "سنة التقرير / Reporting year",
        [ALL] + list(range(date.today().year, date.today().year - 6, -1)),
    )

country_iso = ISO_BY_AR.get(country) if country not in (ALL, "أخرى") else None
company_filter_id = company_id_by_name.get(company)
year_filter = None if report_year == ALL else int(report_year)
st.divider()


def build_dataset(extra_filters=None):
    """ONE data path for Dashboard, Reports and exports: DB rows (filtered) + not-yet-saved session rows."""
    ef = extra_filters or {}
    frames = []
    if con is not None:
        frames.append(L.fetch_records(con, country=country_iso, company_id=company_filter_id,
                                      year=ef.get("year", year_filter), month=ef.get("month"),
                                      date_from=ef.get("date_from"), date_to=ef.get("date_to"),
                                      scope=ef.get("scope")))
    no_attr_filters = (country_iso is None and company_filter_id is None and ef.get("year", year_filter) is None
                       and not ef.get("month") and not ef.get("date_from") and not ef.get("date_to"))
    if no_attr_filters and not st.session_state.legacy_saved_to_db and not st.session_state.activities.empty:
        lf = legacy_frame(st.session_state.activities)
        if ef.get("scope"):
            lf = lf[lf["scope"] == ef["scope"]]
        frames.append(lf)
    frames = [f for f in frames if f is not None and not f.empty]
    if not frames:
        return L.fetch_records(con, year=-1) if con is not None else pd.DataFrame(
            columns=["kg", "calc_status", "scope", "activity_name"])
    return pd.concat(frames, ignore_index=True)


def to_legacy_view(df):
    """Same Arabic column names the original charts/tables use."""
    if df.empty:
        return pd.DataFrame(columns=["النشاط", "النطاق", "الكمية", "الوحدة", "معامل الانبعاث", "المصدر",
                                     "الانبعاثات (kg CO2e)"])
    out = pd.DataFrame({
        "النشاط": df["activity_name"], "النطاق": df["scope"].fillna(tr("يحتاج مراجعة", "Needs review")),
        "الكمية": pd.to_numeric(df["quantity"], errors="coerce"), "الوحدة": df["unit"],
        "معامل الانبعاث": pd.to_numeric(df["factor_value"], errors="coerce"),
        "المصدر": df["factor_source"].fillna(""),
        "الانبعاثات (kg CO2e)": df["kg"].apply(lambda v: float(v) if v is not None and not pd.isna(v) else float("nan")),
    })
    return out


# ---------- Dashboard ----------
if page in ["لوحة التحكم", "Dashboard"]:
    d1, d2, d3 = st.columns(3)
    with d1:
        month_choice = st.selectbox(tr("الشهر", "Month"), [ALL] + list(range(1, 13)))
    with d2:
        scope_choice = st.selectbox(tr("النطاق", "Scope"), [ALL, "Scope 1", "Scope 2", "Scope 3"])
    with d3:
        origin_choice = st.selectbox(
            tr("فئة النشاط", "Activity category"), [ALL] + list(CAT_LABEL.values()))

    ds = build_dataset({"month": None if month_choice == ALL else int(month_choice),
                        "scope": None if scope_choice == ALL else scope_choice})
    if origin_choice != ALL and not ds.empty and "category_key" in ds.columns:
        inv = {v: k for k, v in CAT_LABEL.items()}
        ds = ds[ds["category_key"] == inv[origin_choice]]
    summ = L.summarize(ds, year=year_filter)
    activities = to_legacy_view(ds)
    total_kg = float(summ["total_kg"])
    total_tonnes = total_kg / 1000
    scope_totals = {k: float(v) for k, v in summ["by_scope_kg"].items()}

    st.markdown(
        '<div class="section-title">مؤشرات الأداء الكربوني</div>',
        unsafe_allow_html=True,
    )

    cols = st.columns(4)
    kpis = [
        ("إجمالي الانبعاثات", f"{total_tonnes:,.3f}", "طن CO₂e", total_kg),
        ("النطاق الأول", f"{scope_totals['Scope 1']/1000:,.3f}", "طن CO₂e", scope_totals["Scope 1"]),
        ("النطاق الثاني", f"{scope_totals['Scope 2']/1000:,.3f}", "طن CO₂e", scope_totals["Scope 2"]),
        ("النطاق الثالث", f"{scope_totals['Scope 3']/1000:,.3f}", "طن CO₂e", scope_totals["Scope 3"]),
    ]

    for col, (label, value, unit, kg_val) in zip(cols, kpis):
        with col:
            st.markdown(
                f'<div class="kpi"><div class="kpi-label">{label}</div>'
                f'<div class="kpi-value">{value}</div>'
                f'<div class="kpi-note">{unit} · {kg_val:,.1f} kg</div></div>',
                unsafe_allow_html=True,
            )

    st.write("")
    k1, k2, k3, k4 = st.columns(4)
    pct = summ["verified_pct"]
    k1.metric(tr("عدد السجلات", "Records"), summ["records"])
    k2.metric(tr("سجلات محسوبة بمعامل موثق", "Records with verified factor"), summ["verified_factor_records"])
    k3.metric(tr("سجلات تحتاج مراجعة/معامل/تاريخ", "Records needing review"), summ["needs_review"])
    k4.metric(tr("نسبة البيانات الموثقة", "Verified share"), "—" if pct is None else f"{pct:.1f}%")
    st.caption(tr("التعريف: ", "Definition: ") + summ["verified_pct_definition"] +
               tr(" — المجاميع تشمل السجلات المحسوبة فقط، ولا تُحتسب السجلات الناقصة كأصفار.",
                  " — totals include calculated records only; incomplete records are not counted as zero."))
    if summ["undated_kg"]:
        st.info(tr(f"{float(summ['undated_kg']):,.1f} kg CO₂e من سجلات بلا تاريخ (تظهر في الإجمالي، لا في الشهري/السنوي).",
                   f"{float(summ['undated_kg']):,.1f} kg CO₂e comes from undated records (in the total, not in monthly/annual views)."))
    if summ["avg_monthly_active_kg"] is not None:
        st.caption(tr(
            f"متوسط الانبعاثات الشهري: {float(summ['avg_monthly_active_kg']):,.1f} kg (على {summ['months_with_data']} شهر فيه نشاط)"
            + (f"، و{float(summ['avg_monthly_12_kg']):,.1f} kg موزعًا على 12 شهرًا" if summ["avg_monthly_12_kg"] is not None else ""),
            f"Monthly average: {float(summ['avg_monthly_active_kg']):,.1f} kg over {summ['months_with_data']} active month(s)"
            + (f"; {float(summ['avg_monthly_12_kg']):,.1f} kg spread over 12 months" if summ["avg_monthly_12_kg"] is not None else "")))

    left, right = st.columns([1.45, 1])

    with left:
        st.markdown(
            '<div class="section-title">مصادر الانبعاثات</div>',
            unsafe_allow_html=True,
        )
        plot_df = activities.dropna(subset=["الانبعاثات (kg CO2e)"])
        if plot_df.empty:
            st.info("أضيفي نشاطًا لعرض الرسم البياني.")
        else:
            by_activity = plot_df.groupby(
                "النشاط", as_index=False
            )["الانبعاثات (kg CO2e)"].sum()
            fig = px.bar(
                by_activity,
                x="النشاط",
                y="الانبعاثات (kg CO2e)",
                color="النشاط",
                title="الانبعاثات حسب النشاط",
                labels={
                    "النشاط": "النشاط",
                    "الانبعاثات (kg CO2e)": "kg CO₂e",
                },
            )
            fig.update_layout(
                showlegend=False,
                plot_bgcolor="white",
                paper_bgcolor="white",
                margin=dict(l=15, r=15, t=55, b=15),
            )
            st.plotly_chart(fig, use_container_width=True)

    with right:
        st.markdown(
            '<div class="section-title">التوزيع حسب النطاق</div>',
            unsafe_allow_html=True,
        )
        scope_df = pd.DataFrame({
            "النطاق": ["Scope 1", "Scope 2", "Scope 3"],
            "الانبعاثات": [
                scope_totals["Scope 1"],
                scope_totals["Scope 2"],
                scope_totals["Scope 3"],
            ],
        })
        if scope_df["الانبعاثات"].sum() > 0:
            fig2 = px.pie(
                scope_df,
                names="النطاق",
                values="الانبعاثات",
                hole=0.58,
            )
            fig2.update_layout(
                margin=dict(l=5, r=5, t=20, b=5),
                legend_title_text="",
            )
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("لا توجد بيانات كافية للرسم.")

    # ---- added charts (same dataset, same summary) ----
    t1, t2 = st.columns(2)
    with t1:
        st.markdown(f'<div class="section-title">{tr("الاتجاه الشهري", "Monthly trend")}</div>', unsafe_allow_html=True)
        if summ["monthly_kg"]:
            mdf = pd.DataFrame([{"الفترة": f"{y}-{m:02d}", "kg CO₂e": float(v)} for (y, m), v in summ["monthly_kg"].items()])
            figm = px.line(mdf, x="الفترة", y="kg CO₂e", markers=True)
            figm.update_layout(plot_bgcolor="white", paper_bgcolor="white", margin=dict(l=15, r=15, t=20, b=15))
            st.plotly_chart(figm, use_container_width=True)
        else:
            st.info(tr("لا توجد سجلات مؤرخة في هذه الفترة.", "No dated records in this selection."))
    with t2:
        st.markdown(f'<div class="section-title">{tr("المقارنة السنوية", "Year-over-year")}</div>', unsafe_allow_html=True)
        all_years = L.yearly_totals(L.fetch_records(con, country=country_iso, company_id=company_filter_id)) if con else {}
        if all_years:
            ydf = pd.DataFrame([{"السنة": str(y), "kg CO₂e": float(v)} for y, v in sorted(all_years.items())])
            figy = px.bar(ydf, x="السنة", y="kg CO₂e")
            figy.update_layout(plot_bgcolor="white", paper_bgcolor="white", margin=dict(l=15, r=15, t=20, b=15))
            st.plotly_chart(figy, use_container_width=True)
        else:
            st.info(tr("لا توجد سنوات للمقارنة.", "No years to compare."))
    tops = L.top_sources(ds)
    if tops:
        st.markdown(f'<div class="section-title">{tr("أكبر مصادر الانبعاثات", "Top emission sources")}</div>', unsafe_allow_html=True)
        st.dataframe(pd.DataFrame([{"النشاط": a, "kg CO₂e": float(v)} for a, v in tops]),
                     use_container_width=True, hide_index=True)

    st.markdown(
        '<div class="section-title">سجل الأنشطة والحسابات</div>',
        unsafe_allow_html=True,
    )
    if not activities.empty:
        st.dataframe(
            activities,
            use_container_width=True,
            hide_index=True,
        )
    incomplete = ds[ds["calc_status"] != "calculated"] if not ds.empty else ds
    if not incomplete.empty:
        st.warning(tr("سجلات غير محسوبة (تحتاج معامل/تاريخ/مراجعة) — لا تدخل في المجاميع:",
                      "Records not calculated (need factor/date/review) — excluded from totals:"))
        st.dataframe(incomplete[["activity_name", "calc_status", "calc_notes"]], use_container_width=True, hide_index=True)

    st.markdown(
        '<div class="section-title">فرص خفض الانبعاثات</div>',
        unsafe_allow_html=True,
    )
    r1, r2, r3 = st.columns(3)
    with r1:
        st.markdown(
            '<div class="recommendation"><b>⚡ كفاءة الطاقة</b>'
            '<p>مراجعة استهلاك الكهرباء وتحديد المعدات الأعلى استهلاكًا.</p>'
            '<span class="small-muted">توصية أولية — تحتاج بيانات فعلية</span></div>',
            unsafe_allow_html=True,
        )
    with r2:
        st.markdown(
            '<div class="recommendation"><b>🚚 تحسين النقل</b>'
            '<p>مراجعة المسارات ومعدلات تحميل المركبات.</p>'
            '<span class="small-muted">توصية أولية — تحتاج بيانات فعلية</span></div>',
            unsafe_allow_html=True,
        )
    with r3:
        st.markdown(
            '<div class="recommendation"><b>♻️ إدارة المخلفات</b>'
            '<p>فصل المخلفات ومراجعة فرص إعادة الاستخدام والتدوير.</p>'
            '<span class="small-muted">توصية أولية — تحتاج بيانات فعلية</span></div>',
            unsafe_allow_html=True,
        )

# ---------- Carbon calculator ----------
elif page in ["حساب البصمة الكربونية", "Carbon Calculator"]:
    st.subheader("🧮 حساب البصمة الكربونية")
    st.write(
        tr("أدخلي نشاطًا بتاريخ صريح. يقترح النظام النطاق والمعامل ويشرح السبب، ويمكنك المراجعة والتعديل. "
           "النتائج تُحفظ في قاعدة البيانات مع لقطة من المعامل المستخدم.",
           "Enter an activity with an explicit date. The system suggests scope and factor with reasons; you can review "
           "and override. Results are saved with a snapshot of the factor used.")
    )
    if con is None:
        st.error(tr("قاعدة البيانات غير متاحة: استخدمي الإدخال السريع (الجلسة) أدناه.",
                    "Database unavailable: use the quick session entry below."))
    else:
        c1, c2, c3 = st.columns(3)
        with c1:
            a_name = st.text_input(tr("اسم النشاط", "Activity name"), key="a_name")
            a_desc = st.text_input(tr("وصف النشاط", "Description"), key="a_desc")
            iso_options = [r["iso2_code"] for r in COUNTRY_ROWS]
            default_iso = get_setting("default_country", "EG")
            a_country = st.selectbox(
                tr("الدولة", "Country"), iso_options,
                index=iso_options.index(default_iso) if default_iso in iso_options else 0,
                format_func=lambda c: f"{LABEL_BY_ISO.get(c, c)} ({c})", key="a_country")
        with c2:
            a_company = st.text_input(tr("الشركة (اختياري)", "Company (optional)"), key="a_company")
            a_facility = st.text_input(tr("الفرع/الموقع (اختياري)", "Facility (optional)"), key="a_facility")
            a_date = st.date_input(tr("تاريخ النشاط (اتركيه فارغًا إذا كان غير معروف)", "Activity date (leave empty if unknown)"),
                                   value=None, key="a_date")
        with c3:
            a_cat = st.selectbox(tr("فئة النشاط", "Activity category"), [r["category_key"] for r in CATEGORY_ROWS],
                                 format_func=lambda k: CAT_LABEL.get(k, k), key="a_cat")
            a_fuel = st.text_input(tr("نوع الوقود/المادة (مثال: diesel)", "Fuel/material (e.g. diesel)"), key="a_fuel")
            q1, q2 = st.columns(2)
            a_qty = q1.number_input(tr("الكمية", "Quantity"), min_value=0.0, value=0.0, step=1.0, key="a_qty")
            a_unit = q2.selectbox(tr("الوحدة", "Unit"),
                                  ["kWh", "MWh", "GJ", "MJ", "litre", "L", "m3", "kg", "tonne", "km", "tkm", "pkm",
                                   "room_night", "unit"], key="a_unit")

        st.markdown(f"**{tr('معلومات تحديد النطاق', 'Scope determination inputs')}**")
        s1, s2, s3 = st.columns(3)
        a_control = s1.selectbox(tr("ملكية/سيطرة المصدر", "Ownership / control of the source"),
                                 ["unknown", "owned_controlled", "leased_controlled", "leased_not_controlled", "not_controlled"],
                                 key="a_control")
        a_energy = s2.selectbox(tr("هل الطاقة مشتراة؟", "Is the energy purchased?"), ["unknown", "yes", "no"], key="a_energy")
        a_rel = s3.selectbox(tr("علاقة سلسلة القيمة", "Value-chain relationship"),
                             ["unknown", "own_fleet", "on_site_controlled", "third_party_upstream",
                              "third_party_downstream", "business_travel", "employee"], key="a_rel")
        from services.scope_classifier import classify
        sug_scope = classify(category_key=a_cat, ownership_control=a_control, energy_purchased=a_energy,
                             value_chain_relation=a_rel, description=a_desc)
        badge = {"suggested": "✅", "needs_review": "⚠️", "undetermined": "❓"}[sug_scope.status]
        st.info(f"{badge} **{sug_scope.scope or tr('غير محدد — يحتاج إلى مراجعة', 'Undetermined — needs review')}**"
                f"{' — ' + sug_scope.subcategory if sug_scope.subcategory else ''}  \n"
                f"{tr('الثقة', 'Confidence')}: {sug_scope.confidence} · {sug_scope.reason_ar if not is_en else sug_scope.reason_en}  \n"
                f"{tr('المرجع المنهجي', 'Methodology')}: {sug_scope.reference}"
                + (f"  \n{tr('معلومات ناقصة', 'Missing info')}: {', '.join(sug_scope.missing)}" if sug_scope.missing else ""))
        use_override = st.checkbox(tr("تعديل النطاق يدويًا", "Override scope manually"), key="a_override")
        override = None
        if use_override:
            o1, o2, o3 = st.columns(3)
            o_scope = o1.selectbox(tr("النطاق", "Scope"), ["Scope 1", "Scope 2", "Scope 3"], key="o_scope")
            o_sub = o2.text_input(tr("الفئة الفرعية (مثال: Category 6)", "Subcategory (e.g. Category 6)"), key="o_sub")
            o_reason = o3.text_input(tr("سبب التعديل (إلزامي)", "Reason (required)"), key="o_reason")
            override = (o_scope, o_sub or None, o_reason)

        eff_scope = override[0] if override else sug_scope.scope
        s2m = None
        if eff_scope == "Scope 2":
            s2m = st.radio(tr("طريقة حساب النطاق 2", "Scope 2 method"), ["location", "market"],
                           index=0 if get_setting("scope2_method", "location") == "location" else 1, horizontal=True)
            if s2m == "market":
                st.caption(tr("Market-based يتطلب معامل مورد/عقد/شهادات طاقة بإثبات؛ شراء الكهرباء وحده لا يكفي. "
                              "أدخلي معاملًا يدويًا مع مصدره.",
                              "Market-based needs supplier/contract/certificate evidence; buying power alone is not enough. "
                              "Enter a manual factor with its source."))

        st.markdown(f"**{tr('معامل الانبعاث', 'Emission factor')}**")
        mode = st.radio(tr("مصدر المعامل", "Factor source"), [tr("من المكتبة", "From library"), tr("إدخال يدوي", "Manual entry")],
                        horizontal=True, key="a_mode")
        chosen_factor, proxy_ok, sel_reason = None, False, ""
        if mode == tr("من المكتبة", "From library"):
            if a_date is None:
                st.info(tr("حدّدي تاريخ النشاط لأن صلاحية المعامل تعتمد على السنة.", "Set the activity date: factor validity depends on the year."))
            else:
                sg = FL.suggest(con, country=a_country, category=a_cat, year=a_date.year, unit=a_unit,
                                fuel=a_fuel.strip() or None)
                st.caption(sg.message)
                if sg.candidates:
                    labels = {c.factor.factor_id + f" v{c.factor.version}": c for c in sg.candidates}
                    cand_df = pd.DataFrame([{
                        tr("المعامل", "Factor"): k, tr("القيمة", "Value"): f"{c.factor.total_co2e} kg CO2e/{c.factor.denominator_unit}",
                        tr("الدولة", "Country"): c.factor.country, tr("المستوى", "Tier"): c.tier,
                        tr("الحالة", "Status"): c.factor.status.value, tr("السبب", "Reason"): c.reason}
                        for k, c in labels.items()])
                    st.dataframe(cand_df, use_container_width=True, hide_index=True)
                    default_idx = 1 if sg.chosen else 0
                    pick = st.selectbox(tr("اختاري المعامل", "Choose the factor"), [tr("— لا شيء —", "— none —")] + list(labels),
                                        index=default_idx, key="a_pick")
                    if pick in labels:
                        cand = labels[pick]
                        chosen_factor = cand.factor
                        sel_reason = cand.reason
                        if cand.needs_proxy_confirmation:
                            proxy_ok = st.checkbox(tr("أؤكد استخدام معامل بديل (ليس وطنيًا لهذه الدولة)",
                                                      "I confirm using a substitute (not national for this country)"), key="a_proxy")
                            why = st.text_input(tr("مبرر الاستخدام (إلزامي)", "Rationale (required)"), key="a_proxy_why")
                            if proxy_ok and not why.strip():
                                proxy_ok = False
                            sel_reason += f" | PROXY rationale: {why.strip()}" if why.strip() else ""
                        if not cand.verified:
                            st.warning(tr("هذا المعامل غير متحقق منه؛ ستُعلَّم النتيجة كتقدير.",
                                          "This factor is unverified; the result will be flagged as an estimate."))
                if sg.excluded:
                    with st.expander(tr("معاملات مستبعدة وأسباب الاستبعاد", "Excluded factors and why")):
                        st.dataframe(pd.DataFrame(sg.excluded, columns=["factor", "reason"]), use_container_width=True, hide_index=True)
        else:
            m1, m2, m3 = st.columns(3)
            m_val = m1.number_input(tr("معامل الانبعاث (kg CO2e لكل وحدة)", "Factor (kg CO2e per unit)"),
                                    min_value=0.0, value=0.0, step=0.01, key="m_val")
            m_src = m2.text_input(tr("اسم المصدر أو المرجع (إلزامي)", "Source / reference (required)"), key="m_src")
            m_url = m3.text_input(tr("رابط المرجع (اختياري)", "Reference URL (optional)"), key="m_url")
            if m_val > 0 and m_src.strip():
                chosen_factor = L.user_factor(str(m_val), country=a_country, category=a_cat, activity=(a_fuel.strip() or a_name or a_cat),
                                              unit=a_unit, year=(a_date.year if a_date else 0), source=m_src.strip(), url=m_url)
                sel_reason = "User-supplied factor (unverified)"
                proxy_ok = True
            elif m_val > 0:
                st.error(tr("أدخلي مصدر المعامل.", "Enter the factor source."))

        keep_dup = st.checkbox(tr("السماح بسجل مكرر إن وُجد", "Allow a duplicate record if one exists"), key="a_dup")
        if st.button(tr("حفظ النشاط وحساب الانبعاثات", "Save activity and calculate"), type="primary", use_container_width=True):
            if not a_name.strip():
                st.error(tr("اكتبي اسم النشاط.", "Enter the activity name."))
            elif a_qty <= 0:
                st.error(tr("أدخلي كمية أكبر من صفر.", "Quantity must be greater than zero."))
            elif override and not override[2].strip():
                st.error(tr("سبب تعديل النطاق إلزامي.", "A reason is required for a scope override."))
            else:
                cid = fid = None
                if a_company.strip():
                    cid = L.upsert_company(con, a_company, a_country)
                    if a_facility.strip():
                        fid = L.add_facility(con, cid, a_facility, a_country)
                res = L.add_record(
                    con, activity_name=a_name, quantity=str(a_qty), unit=a_unit, country_code=a_country,
                    activity_date=a_date, description=a_desc, company_id=cid, facility_id=fid, fuel_or_material=a_fuel or None,
                    category_key=a_cat, factor=chosen_factor, factor_selection_reason=sel_reason, proxy_confirmed=proxy_ok,
                    ownership_control=a_control, energy_purchased=a_energy, value_chain_relation=a_rel,
                    scope_override=override, scope2_method=s2m, origin="manual", allow_duplicate=keep_dup)
                if res["duplicate"]:
                    st.warning(tr(f"سجل مطابق موجود مسبقًا (رقم {res['record_id']}). لم يُضف. فعّلي «السماح بسجل مكرر» لإضافته.",
                                  f"An identical record exists (id {res['record_id']}). Not added. Tick 'allow duplicate' to add anyway."))
                elif res["status"] == "calculated":
                    _all = L.fetch_records(con)
                    row = _all[_all["record_id"] == res["record_id"]].iloc[0]
                    st.success(f"{row['kg_co2e']} kg CO₂e  =  {row['t_co2e']} tonne CO₂e")
                    if row["calc_notes"]:
                        st.caption(row["calc_notes"])
                else:
                    st.warning(tr(f"حُفظ السجل لكنه لم يُحسب: {res['status']} — {res.get('notes', '')}",
                                  f"Saved but not calculated: {res['status']} — {res.get('notes', '')}"))

    # ---- original quick demo entry (session only), unchanged behaviour ----
    with st.expander(tr("الإدخال السريع التجريبي (الأصلي) — يُحفظ في الجلسة فقط", "Quick demo entry (original) — session only")):
        st.write(
            "أدخلي بيانات نشاط. هذه النسخة تستخدم معاملًا تجريبيًا "
            "ولا تستبدل المعاملات الرسمية الخاصة بالدولة والسنة."
        )

        with st.form("activity_form", clear_on_submit=True):
            activity_name = st.text_input("اسم النشاط")
            scope = st.selectbox(
                "النطاق",
                ["Scope 1", "Scope 2", "Scope 3"],
            )
            quantity = st.number_input(
                "كمية النشاط", min_value=0.0, value=0.0, step=1.0
            )
            unit = st.selectbox(
                "الوحدة",
                ["kWh", "L", "m3", "kg", "tonne", "km", "tonne-km", "unit"],
            )
            factor = st.number_input(
                "معامل الانبعاث التجريبي (kg CO2e لكل وحدة)",
                min_value=0.0,
                value=0.0,
                step=0.01,
            )
            source = st.text_input(
                "اسم المصدر أو المرجع",
                value="معامل تجريبي — غير معتمد",
            )
            source_url = st.text_input("رابط المرجع (اختياري)")
            submitted = st.form_submit_button(
                "إضافة النشاط وحساب الانبعاثات",
                type="primary",
                use_container_width=True,
            )

        if submitted:
            if not activity_name.strip():
                st.error("اكتبي اسم النشاط أولًا.")
            elif quantity <= 0:
                st.error("أدخلي كمية أكبر من صفر.")
            elif factor <= 0:
                st.error("أدخلي معاملًا صالحًا. لا تستخدمي صفرًا كبديل عن معامل مفقود.")
            else:
                new_row = {
                    "النشاط": activity_name.strip(),
                    "النطاق": scope,
                    "الكمية": quantity,
                    "الوحدة": unit,
                    "معامل الانبعاث": factor,
                    "المصدر": source or "غير محدد",
                }
                st.session_state.activities = pd.concat(
                    [
                        st.session_state.activities,
                        pd.DataFrame([new_row]),
                    ],
                    ignore_index=True,
                )
                st.success(
                    f"تمت إضافة النشاط. الناتج التجريبي: "
                    f"{quantity * factor:,.3f} kg CO₂e"
                )
                if source_url:
                    st.markdown(f"[فتح المرجع المدخل]({source_url})")
                st.info("راجعي وحدة المعامل ومصدره قبل استخدام النتيجة رسميًا.")

        st.caption(tr("صفوف الجلسة مؤقتة: تختفي عند إعادة تشغيل التطبيق ما لم تُحفظ في قاعدة البيانات.",
                      "Session rows are temporary: they vanish on restart unless saved to the database."))
        if con is not None and not st.session_state.activities.empty and not st.session_state.legacy_saved_to_db:
            if st.button(tr("💾 حفظ صفوف الجلسة في قاعدة البيانات (بلا تواريخ، دون حذف شيء)",
                            "💾 Save session rows to the database (undated, nothing deleted)")):
                out = L.migrate_session_rows(con, st.session_state.activities)
                if out["failed"] == 0:
                    st.session_state.legacy_saved_to_db = True
                st.success(f"{out}")
        # original reset button: only touches session rows, never the database; now needs confirmation
        confirm_clear = st.checkbox(tr("أؤكد مسح صفوف الجلسة فقط (لا تُمس قاعدة البيانات)",
                                       "Confirm clearing session rows only (database untouched)"), key="confirm_clear")
        if st.button("مسح الأنشطة وإعادة بيانات العرض", disabled=not confirm_clear):
            st.session_state.activities = pd.DataFrame(
                columns=[
                    "النشاط", "النطاق", "الكمية", "الوحدة",
                    "معامل الانبعاث", "المصدر",
                ]
            )
            st.rerun()



# ---------- Data entry / imports ----------
elif page in ["إدخال البيانات والاستيراد", "Data Entry & Imports"]:
    st.subheader("📥 إدخال البيانات واستيراد الملفات")
    st.write("ارفعي ملف CSV أو Excel، راجعي المعاينة والصفوف المرفوضة، ثم ادمجي الصفوف المقبولة مع السجلات الحالية.")

    uploaded = st.file_uploader(
        "اختاري ملف البيانات",
        type=["csv", "xlsx"],
        key="activity_upload",
    )

    if uploaded:
        try:
            imported_df = IM.read_upload(uploaded.name, uploaded.getvalue())
            st.success(f"تم فتح الملف: {uploaded.name}")
            st.write("معاينة البيانات:")
            st.dataframe(imported_df.head(20), use_container_width=True)
            st.caption(
                "الأعمدة المطلوبة: النشاط، الكمية، الوحدة. اختيارية: النطاق، معامل الانبعاث، المصدر، التاريخ، الدولة، "
                "الشركة، الفرع، فئة النشاط، نوع الوقود، السيطرة، طاقة مشتراة، علاقة سلسلة القيمة. "
                "الملفات القديمة (النشاط، النطاق، الكمية، الوحدة، معامل الانبعاث[، المصدر]) ما زالت مدعومة."
            )
            o1, o2 = st.columns(2)
            use_default_date = o1.checkbox("تطبيق تاريخ افتراضي صريح على الصفوف التي بلا تاريخ")
            default_date = o1.date_input("التاريخ الافتراضي", value=date.today(), disabled=not use_default_date)
            default_country = o2.selectbox("دولة افتراضية للصفوف التي بلا دولة",
                                           [""] + [r["iso2_code"] for r in COUNTRY_ROWS])
            keep_dups = o2.checkbox("السماح بإضافة السجلات المكررة (الافتراضي: تُبلَّغ ولا تُضاف)")

            pv = IM.preview(imported_df, default_date=default_date if use_default_date else None,
                            default_country=default_country or None)
            if pv.missing_columns:
                st.error("الأعمدة المطلوبة غير موجودة: " + "، ".join(pv.missing_columns))
            else:
                st.markdown(f"**✅ مقبول: {len(pv.accepted)}  |  ❌ مرفوض: {len(pv.rejected)}  |  ⚠️ ملاحظات: {len(pv.warnings)}**")
                if pv.rejected:
                    st.dataframe(pd.DataFrame([{"الصف": n, "السبب": why} for n, why, _ in pv.rejected]),
                                 use_container_width=True, hide_index=True)
                if pv.warnings:
                    with st.expander("ملاحظات على الصفوف المقبولة"):
                        st.dataframe(pd.DataFrame(pv.warnings, columns=["الصف", "ملاحظة"]), use_container_width=True, hide_index=True)
                if con is None:
                    st.error("قاعدة البيانات غير متاحة؛ لا يمكن حفظ الاستيراد الدائم.")
                elif pv.accepted and st.button("✅ دمج الصفوف المقبولة مع السجلات الحالية", type="primary"):
                    out = IM.commit(con, pv, file_name=uploaded.name, keep_duplicates=keep_dups)
                    st.success(f"أُضيف {out['added']} سجل. مكرر (لم يُضف): {len(out['duplicates'])}. "
                               f"يحتاج معامل/مراجعة: {out['needs_review']}. مرفوض: {out['rejected']}.")
                    if out["duplicates"]:
                        st.dataframe(pd.DataFrame(out["duplicates"], columns=["الصف", "النشاط"]), use_container_width=True, hide_index=True)
                    if out["failed"]:
                        st.error(f"فشل صفوف: {out['failed']}")
                    st.info("افتحي لوحة التحكم لعرض النتائج. لم يُحذف أو يُستبدل أي سجل سابق.")

            st.download_button(
                "⬇️ تنزيل نسخة CSV من المعاينة",
                data=imported_df.to_csv(index=False).encode("utf-8-sig"),
                file_name="carbonai_import_preview.csv",
                mime="text/csv",
            )

        except Exception as exc:
            st.error(f"تعذر قراءة الملف. التفاصيل: {exc}")

    st.divider()
    st.subheader("قالب الأعمدة المطلوب")

    template = pd.DataFrame([
        {
            "النشاط": "استهلاك الكهرباء",
            "النطاق": "Scope 2",
            "الكمية": 1000,
            "الوحدة": "kWh",
            "معامل الانبعاث": 0.45,
            "المصدر": "مرجع تجريبي",
        }
    ])

    st.dataframe(template, use_container_width=True)

    st.download_button(
        "⬇️ تنزيل قالب CSV",
        data=template.to_csv(index=False).encode("utf-8-sig"),
        file_name="carbonai_template.csv",
        mime="text/csv",
    )
    full_template = pd.DataFrame([{c: "" for c in IM.TEMPLATE_COLUMNS}])
    st.download_button(
        "⬇️ تنزيل القالب الموسّع (تاريخ، دولة، شركة، فرع، فئة...)",
        data=full_template.to_csv(index=False).encode("utf-8-sig"),
        file_name="carbonai_template_full.csv",
        mime="text/csv",
    )

# ---------- Invoices ----------
elif page in ["الفواتير والمستندات", "Invoices & Documents"]:
    st.subheader("🧾 الفواتير والمستندات")
    st.write(
        "ارفعي فاتورة PDF أو صورة لحفظها ضمن جلسة العرض. "
        "استخراج البيانات آليًا وOCR غير مربوطين في هذه النسخة."
    )
    files = st.file_uploader(
        "رفع الفواتير",
        type=["pdf", "png", "jpg", "jpeg"],
        accept_multiple_files=True,
        key="invoice_upload",
    )
    if files:
        for file in files:
            st.write(f"📄 {file.name} — {file.size:,} bytes")
        st.info(
            "الخطوة التالية هي ربط OCR واستخراج الكميات والوحدات، "
            "ثم عرضها للمراجعة البشرية قبل الحساب."
        )
    st.caption("لا يوجد OCR ولا تخزين دائم للمرفقات في هذه النسخة. يمكن ربط رقم مرجعي لمستند ما بسجل نشاط عبر حقل «مرجع الإثبات» لاحقًا.")

# ---------- Emission factors and references ----------
elif page in ["معاملات الانبعاثات والمراجع", "Emission Factors & Sources"]:
    st.subheader("📚 مكتبة معاملات الانبعاثات والمراجع")
    st.warning(
        "المكتبة الحالية لا تحتوي إلا على معاملات نيوزيلندا (37 صفًا، غير متحقق منها بعد). "
        "لا توجد معاملات موثقة لمصر أو أي دولة أخرى. الروابط أدناه نقطة بداية للتحقق وليست إثباتًا لوجود معامل."
    )
    tab_lib, tab_cov, tab_src, tab_add, tab_upd, tab_log, tab_orig = st.tabs([
        "المعاملات", "تغطية الدول", "المراجع المسجلة", "إضافة/اعتماد", "تحديث من ملف", "سجل التغييرات", "الروابط الأصلية"])

    with tab_lib:
        if con is None:
            st.info("قاعدة البيانات غير متاحة.")
        else:
            a, b, c = st.columns(3)
            fc = a.selectbox("الدولة", [""] + [r["iso2_code"] for r in COUNTRY_ROWS] + ["GLOBAL"], key="lf_c")
            fcat = b.selectbox("الفئة", [""] + [r["category_key"] for r in CATEGORY_ROWS], key="lf_cat")
            fstat = c.selectbox("حالة التحقق", ["", "verified", "pending_review", "unverified", "superseded", "rejected"], key="lf_s")
            d_, e_, f_ = st.columns(3)
            fyear = d_.number_input("السنة (0 = الكل)", min_value=0, max_value=2100, value=0, key="lf_y")
            fact = e_.text_input("بحث في النشاط", key="lf_a")
            fclass = f_.selectbox("نوع المصدر", ["", "official_national", "regional", "global_default", "proxy", "user_supplied"], key="lf_cl")
            rows = FL.search_factors(con, country=fc or None, category=fcat or None, status=fstat or None,
                                     year=int(fyear) or None, activity_like=fact or None, factor_class=fclass or None)
            show = pd.DataFrame([{
                "factor_id": r["factor_id"], "v": r["version"], "الدولة": r["country_code"], "الفئة": r["activity_category"],
                "النشاط": r["activity"], "القيمة": r["co2e_factor_value"], "الوحدة": r["factor_unit"],
                "من": r["year_from"], "إلى": r["year_to"], "النوع": r["factor_class"],
                "التحقق": FL.VERIFICATION_LABELS.get(r["verification_status"], ("", r["verification_status"]))[0],
                "الجهة": r["source_organization"], "الموقع في الوثيقة": r["source_locator"]} for r in rows])
            st.caption(f"{len(show)} معامل")
            st.dataframe(show, use_container_width=True, hide_index=True)
            if len(rows):
                ids = [f"{r['factor_id']} v{r['version']}" for r in rows]
                pick = st.selectbox("عرض تفاصيل معامل", ids, key="lf_detail")
                fid, ver = pick.rsplit(" v", 1)
                r = next(x for x in rows if x["factor_id"] == fid and str(x["version"]) == ver)
                st.json({k: r[k] for k in r.keys() if k not in ("components_json",)})
                st.caption("تصنيف النطاق لا يُشتق من المعامل؛ يُحدَّد لكل نشاط حسب السيطرة والعلاقة (انظر الحاسبة).")

    with tab_cov:
        if con is not None:
            cov = pd.DataFrame([dict(r) for r in FL.countries_coverage(con)])
            cov.columns = ["ISO2", "Country", "الدولة", "عدد المعاملات", "منها متحقق منها"]
            st.dataframe(cov, use_container_width=True, hide_index=True)
            st.caption("دولة بعدد 0 = المكتبة لا تحتوي معاملات لها بعد. لا يعني وجودها في القائمة أن بياناتها محمّلة.")

    with tab_src:
        if con is not None:
            st.dataframe(pd.read_sql_query(
                "SELECT reference_id, organization_name, document_title, publication_year, source_url, geographic_scope, "
                "last_checked_at, verification_status, license_or_usage_notes FROM sources", con),
                use_container_width=True, hide_index=True)
            st.caption("`last_checked_at` فارغ = لم يُفحص الرابط (لا شبكة أثناء البناء). وجود الرابط ليس تحققًا من قيمة أي معامل.")

    with tab_add:
        if con is not None:
            st.markdown("**إضافة معامل جديد / نسخة جديدة** (تُحفظ «غير متحقق منها»؛ النسخة السابقة تبقى)")
            who = st.text_input("اسمك (المراجع) — لا توجد مصادقة في هذه النسخة، يُسجَّل الاسم كما كُتب", key="who")
            with st.form("add_factor"):
                x1, x2, x3 = st.columns(3)
                nf_id = x1.text_input("factor_id (مثال: EG-ELEC-GRID-2023)")
                nf_country = x2.text_input("رمز الدولة ISO2 أو GLOBAL").upper()
                nf_class = x3.selectbox("نوع المعامل", ["official_national", "regional", "global_default", "proxy"])
                y1, y2, y3, y4 = st.columns(4)
                nf_cat = y1.selectbox("الفئة", [r["category_key"] for r in CATEGORY_ROWS])
                nf_act = y2.text_input("النشاط/الوقود (مثال: grid_average)")
                nf_unit = y3.text_input("وحدة المقام (مثال: kWh)")
                nf_val = y4.text_input("القيمة (kg CO2e لكل وحدة)")
                z1, z2 = st.columns(2)
                nf_y0 = z1.number_input("سارٍ من سنة", 1990, 2100, 2023)
                nf_y1 = z2.number_input("سارٍ حتى سنة", 1990, 2100, 2023)
                w1, w2, w3 = st.columns(3)
                nf_org = w1.text_input("الجهة المصدِرة (إلزامي)")
                nf_doc = w2.text_input("عنوان الوثيقة (إلزامي)")
                nf_loc = w3.text_input("الجدول/الصفحة (إلزامي)")
                nf_url = st.text_input("رابط الوثيقة المحددة (إن وُجد)")
                nf_ref = st.selectbox("المرجع المسجل", [""] + [r[0] for r in con.execute("SELECT reference_id FROM sources")])
                nf_why = st.text_input("سبب الإضافة (إلزامي)")
                go = st.form_submit_button("إضافة كغير متحقق منه")
            if go:
                try:
                    uc.canon(nf_unit)
                    v = FL.add_factor(con, factor_id=nf_id.strip(), country_code=nf_country.strip(), factor_class=nf_class,
                                      category=nf_cat, activity=nf_act.strip(), unit=nf_unit.strip(), value=nf_val,
                                      year_from=int(nf_y0), year_to=int(nf_y1), reference_id=nf_ref or None,
                                      source_organization=nf_org, source_document=nf_doc, source_url=nf_url or None,
                                      source_locator=nf_loc, reason=nf_why, user=who or None)
                    st.success(f"أُضيف {nf_id} الإصدار {v} (غير متحقق منه).")
                except Exception as exc:
                    st.error(str(exc))
            st.divider()
            st.markdown("**اعتماد / تغيير حالة التحقق** — يلزم اسم مراجع وسبب، ويجب أن يكون المرجع/الموقع مسجلًا")
            vf1, vf2, vf3 = st.columns(3)
            vfid = vf1.text_input("factor_id", key="vf_id")
            vver = vf2.number_input("الإصدار", 1, 999, 1, key="vf_v")
            vstat = vf3.selectbox("الحالة الجديدة", ["verified", "pending_review", "unverified", "rejected"], key="vf_s")
            vwhy = st.text_input("سبب التغيير (مثال: طابقت القيمة مع الجدول X صفحة Y)", key="vf_why")
            if st.button("تطبيق تغيير الحالة"):
                try:
                    FL.set_verification(con, vfid.strip(), int(vver), vstat, reviewer=who, reason=vwhy)
                    st.success("تم، وسُجّل في سجل التغييرات.")
                except Exception as exc:
                    st.error(str(exc))

    with tab_upd:
        st.markdown("**تحديث المكتبة من ملف رسمي نزّلتِه (CSV/Excel)** — التنزيل الآلي من المواقع غير منفّذ.")
        st.caption("كل الصفوف تدخل «غير متحقق منها»، وتُنشأ نسخة جديدة للمعرّف الموجود دون حذف القديم. أي خطأ في الملف = لا يُستورد شيء.")
        st.download_button("⬇️ قالب ملف المعاملات", LU.factor_file_template().to_csv(index=False).encode("utf-8-sig"),
                           file_name="carbonai_factor_update_template.csv", mime="text/csv")
        upf = st.file_uploader("ملف المعاملات", type=["csv", "xlsx"], key="factor_file")
        if upf and con is not None:
            fdf = IM.read_upload(upf.name, upf.getvalue())
            good, problems = LU.validate(fdf)
            st.write(f"صالح: {len(good)} | مشاكل: {len(problems)}")
            if problems:
                st.dataframe(pd.DataFrame(problems, columns=["الصف", "المشكلة"]), use_container_width=True, hide_index=True)
            who2 = st.text_input("اسم المنفّذ", key="who2")
            why2 = st.text_input("سبب/وصف التحديث", key="why2")
            ref2 = st.selectbox("المرجع المسجل", [""] + [r[0] for r in con.execute("SELECT reference_id FROM sources")], key="ref2")
            if not problems and good and who2 and why2 and st.button("تطبيق التحديث"):
                out = LU.apply_file(con, fdf, reference_id=ref2 or None, user=who2, reason=why2, source_label=upf.name)
                st.success(f"أُضيف {out['imported']} معامل (غير متحقق منها).") if out["applied"] else st.error(str(out["problems"][:3]))
        if con is not None:
            st.markdown("**سجل عمليات التحديث**")
            st.dataframe(pd.read_sql_query("SELECT at, source, outcome, detail FROM update_log ORDER BY id DESC LIMIT 50", con),
                         use_container_width=True, hide_index=True)

    with tab_log:
        if con is not None:
            st.dataframe(pd.DataFrame([dict(r) for r in FL.audit_log(con)][-500:]), use_container_width=True, hide_index=True)

    with tab_orig:
        references = pd.DataFrame([
            {
                "الجهة": "GHG Protocol",
                "الموضوع": "معايير حساب انبعاثات الشركات",
                "الرابط": "https://ghgprotocol.org/standards-guidance",
                "الحالة": "مرجع منهجي",
            },
            {
                "الجهة": "GHG Protocol",
                "الموضوع": "انبعاثات سلسلة القيمة Scope 3",
                "الرابط": "https://ghgprotocol.org/corporate-value-chain-scope-3-standard",
                "الحالة": "مرجع منهجي",
            },
            {
                "الجهة": "IPCC",
                "الموضوع": "قاعدة معاملات الانبعاثات",
                "الرابط": "https://www.ipcc-nggip.iges.or.jp/EFDB/main.php",
                "الحالة": "مرجع دولي",
            },
            {
                "الجهة": "IPCC",
                "الموضوع": "إرشادات الجرد الوطني",
                "الرابط": "https://www.ipcc-nggip.iges.or.jp/public/2006gl/",
                "الحالة": "منهجية دولية",
            },
            {
                "الجهة": "European Environment Agency",
                "الموضوع": "كثافة انبعاثات الكهرباء الأوروبية",
                "الرابط": "https://www.eea.europa.eu/en/analysis/indicators/greenhouse-gas-emission-intensity-of-1/",
                "الحالة": "بيانات أوروبية",
            },
            {
                "الجهة": "UK Government",
                "الموضوع": "معاملات إعداد تقارير غازات الدفيئة",
                "الرابط": "https://www.gov.uk/government/collections/government-conversion-factors-for-company-reporting",
                "الحالة": "مرجع وطني بريطاني",
            },
            {
                "الجهة": "US EPA",
                "الموضوع": "GHG Emission Factors Hub",
                "الرابط": "https://www.epa.gov/climateleadership/ghg-emission-factors-hub",
                "الحالة": "مرجع أمريكي",
            },
            {
                "الجهة": "EEAA",
                "الموضوع": "جهاز شؤون البيئة المصري",
                "الرابط": "https://www.eeaa.gov.eg/",
                "الحالة": "بوابة جهة وطنية — تحقق من الوثيقة المحددة",
            },
        ])
        st.dataframe(references, use_container_width=True, hide_index=True)

        for _, row in references.iterrows():
            st.markdown(f"- [{row['الجهة']} — {row['الموضوع']}]({row['الرابط']})")

# ---------- Companies and facilities ----------
elif page in ["الشركات والفروع", "Companies & Facilities"]:
    st.subheader("🏭 الشركات والفروع")
    st.info(
        "تُحفظ الشركات والفروع الآن في قاعدة البيانات. لا توجد مصادقة/إدارة مستخدمين بعد. "
        "بيانات السيطرة أدناه هي ما يعتمد عليه اقتراح النطاق، ولا تُفترض تلقائيًا."
    )
    with st.form("company_form"):
        org_name = st.text_input("اسم الشركة")
        org_country = st.selectbox(
            "دولة الشركة",
            [""] + [r["iso2_code"] for r in COUNTRY_ROWS],
            format_func=lambda c: f"{LABEL_BY_ISO.get(c, c)} ({c})" if c else "—",
        )
        org_sector = st.text_input("القطاع")
        boundary = st.selectbox("نهج حدود المؤسسة (يُحدده المستخدم)",
                                ["", "operational_control", "financial_control", "equity_share"])
        boundary_notes = st.text_area("ملاحظات الحدود التنظيمية للتقرير")
        facility_name = st.text_input("اسم المصنع أو الفرع")
        st.text_input("الرقم التعريفي الداخلي (اختياري)")
        fac_control = st.selectbox("حالة السيطرة على الفرع",
                                   ["unknown", "owned_controlled", "leased_controlled", "leased_not_controlled", "not_controlled"])
        save_company = st.form_submit_button("حفظ بيانات الشركة")

    if save_company:
        if org_name.strip() and con is not None:
            cid = L.upsert_company(con, org_name, org_country or None, org_sector or None, boundary or None,
                                   boundary_notes or None)
            if facility_name.strip():
                L.add_facility(con, cid, facility_name, org_country or None, None, fac_control)
            st.success("تم الحفظ (لا يُستبدل سجل موجود بنفس الاسم والدولة).")
        elif not org_name.strip():
            st.error("اسم الشركة مطلوب.")
    if con is not None:
        st.dataframe(pd.read_sql_query(
            "SELECT c.name AS الشركة, c.country_code AS الدولة, c.industry_sector AS القطاع, c.boundary_approach AS الحدود, "
            "f.name AS الفرع, f.control_status AS السيطرة FROM companies c LEFT JOIN facilities f ON f.company_id=c.company_id "
            "ORDER BY c.name, f.name", con), use_container_width=True, hide_index=True)

# ---------- Reports ----------
elif page in ["التقارير", "Reports"]:
    st.subheader("📊 التقارير")
    r1c, r2c, r3c = st.columns(3)
    mode_p = r1c.radio("الفترة", ["سنة", "شهر", "نطاق تواريخ"], horizontal=True)
    rep_month = r2c.selectbox("الشهر", list(range(1, 13)), disabled=mode_p != "شهر")
    rep_scope = r3c.selectbox("النطاق", ["الكل", "Scope 1", "Scope 2", "Scope 3"])
    dfrom = dto = None
    if mode_p == "نطاق تواريخ":
        dfrom, dto = st.date_input("من / إلى", value=(date(date.today().year, 1, 1), date.today()))
    filt = {"scope": None if rep_scope == "الكل" else rep_scope}
    if mode_p == "شهر":
        filt["month"] = int(rep_month)
    if mode_p == "نطاق تواريخ":
        filt.update(date_from=dfrom, date_to=dto, year=None)
    report_df = build_dataset(filt)
    summ = L.summarize(report_df, year=year_filter if mode_p != "نطاق تواريخ" else None)
    label_year = None if mode_p == "نطاق تواريخ" else year_filter
    label_month = int(rep_month) if mode_p == "شهر" else None
    period_txt = RP.period_label(label_year, label_month, dfrom, dto)
    st.caption(f"حدود التقرير: الفترة = {period_txt} | الدولة = {country} | الشركة = {company} | السجلات = {summ['records']}")

    if report_df.empty:
        st.info("لا توجد أنشطة لإنشاء تقرير.")
    else:
        m1, m2, m3 = st.columns(3)
        m1.metric("إجمالي الانبعاثات", f"{float(summ['total_t']):,.3f} طن CO₂e")
        m2.metric("kg CO₂e", f"{float(summ['total_kg']):,.1f}")
        m3.metric("سجلات تحتاج مراجعة", summ["needs_review"])
        sc = summ["by_scope_kg"]
        st.write(" | ".join(f"{k}: {float(v):,.1f} kg" for k, v in sc.items()))
        if summ["monthly_kg"]:
            st.markdown("**الملخص الشهري**")
            st.dataframe(RP.monthly_summary_df(report_df), use_container_width=True, hide_index=True)
        st.markdown("**تفاصيل الأنشطة (المعامل ومصدره وحالة التحقق)**")
        st.dataframe(RP.report_dataframe(report_df), use_container_width=True, hide_index=True)
        st.download_button(
            "⬇️ تنزيل التقرير بصيغة CSV",
            data=RP.csv_bytes(report_df),
            file_name=RP.csv_filename("report", year=label_year, month=label_month, date_from=dfrom, date_to=dto),
            mime="text/csv",
        )
        st.download_button(
            "⬇️ تنزيل الملخص الشهري CSV",
            data=RP.monthly_summary_df(report_df).to_csv(index=False).encode("utf-8-sig"),
            file_name=RP.csv_filename("monthly_summary", year=label_year, month=label_month, date_from=dfrom, date_to=dto),
            mime="text/csv",
        )
        pdf_lang = st.radio("لغة PDF", ["en", "ar"], horizontal=True,
                            format_func=lambda x: "English" if x == "en" else "العربية")
        ok_ar, why_ar = RP.arabic_pdf_supported()
        if pdf_lang == "ar" and not ok_ar:
            st.warning("PDF العربي غير متاح: " + why_ar)
        else:
            try:
                st.download_button(
                    "⬇️ تنزيل التقرير بصيغة PDF",
                    data=RP.pdf_bytes(report_df, title_company="" if company == ALL else company,
                                      country=country if country != ALL else "", period=period_txt, lang=pdf_lang),
                    file_name=RP.csv_filename("report", year=label_year, month=label_month, date_from=dfrom,
                                              date_to=dto).replace(".csv", f"_{pdf_lang}.pdf"),
                    mime="application/pdf",
                )
            except RP.PdfUnavailable as exc:
                st.warning(f"تعذر إنشاء PDF: {exc}")
            except Exception as exc:
                st.warning(f"تعذر إنشاء PDF: {exc}")

# ---------- Reduction plans ----------
elif page in ["خطط خفض الانبعاثات", "Reduction Plans"]:
    st.subheader("🌱 خطط خفض الانبعاثات")
    st.write(
        "التوصيات هنا أمثلة عامة وليست توقعات كمية أو ضمانًا للتوفير. "
        "سنربط لاحقًا كل إجراء ببيانات النشاط والتكلفة والأدلة المناسبة."
    )
    with st.form("reduction_form"):
        action = st.selectbox(
            "مجال التحسين",
            [
                "رفع كفاءة الكهرباء",
                "تحسين كفاءة الوقود",
                "تحسين النقل والشحن",
                "تقليل المخلفات",
                "تحسين كفاءة المياه",
                "مراجعة المشتريات",
            ],
        )
        description = st.text_area("وصف الإجراء المقترح")
        owner = st.text_input("المسؤول عن التنفيذ")
        target_date = st.date_input("التاريخ المستهدف")
        link_cat = st.selectbox("ربط بفئة نشاط (اختياري)", [""] + [r["category_key"] for r in CATEGORY_ROWS],
                                format_func=lambda k: CAT_LABEL.get(k, "—") if k else "—")
        assumptions = st.text_area("الافتراضات الموثقة لأي تقدير (إن وُجد)")
        plan_status = st.selectbox("حالة التنفيذ", ["planned", "in_progress", "done", "cancelled"])
        submitted_action = st.form_submit_button("حفظ خطة العمل")

    if submitted_action:
        if con is not None:
            from db.connection import now_iso as _now
            con.execute("INSERT INTO reduction_plans(area,description,owner,target_date,status,linked_category_key,"
                        "assumptions,created_at) VALUES (?,?,?,?,?,?,?,?)",
                        (action, description, owner, str(target_date), plan_status, link_cat or None, assumptions, _now()))
            con.commit()
            st.success("تم حفظ الخطة.")
        st.write({
            "الإجراء": action,
            "الوصف": description,
            "المسؤول": owner,
            "التاريخ المستهدف": str(target_date),
        })
        st.caption("الخطة لا تتضمن تخفيضًا مؤكدًا؛ أي رقم مستقبلي يحتاج افتراضات موثقة.")
    if con is not None:
        st.dataframe(pd.read_sql_query(
            "SELECT plan_id, area AS المجال, description AS الوصف, owner AS المسؤول, target_date AS التاريخ, status AS الحالة, "
            "linked_category_key AS الفئة, assumptions AS الافتراضات FROM reduction_plans ORDER BY plan_id DESC", con),
            use_container_width=True, hide_index=True)

# ---------- Settings ----------
elif page in ["الإعدادات", "Settings"]:
    st.subheader("⚙️ الإعدادات")
    unit_pick = st.selectbox("وحدة عرض الانبعاثات (مفعّلة في مؤشرات لوحة التحكم الإضافية)", ["طن CO₂e", "kg CO₂e"],
                             index=0 if get_setting("display_unit", "tonne") == "tonne" else 1)
    st.selectbox("تنسيق التاريخ (غير مطبّق بعد على الجداول)", ["YYYY-MM-DD", "DD/MM/YYYY"])
    if con is not None:
        iso_opts = [r["iso2_code"] for r in COUNTRY_ROWS]
        dc = st.selectbox("الدولة الافتراضية في الحاسبة", iso_opts,
                          index=iso_opts.index(get_setting("default_country", "EG")) if get_setting("default_country", "EG") in iso_opts else 0,
                          format_func=lambda c: f"{LABEL_BY_ISO.get(c, c)} ({c})")
        sm = st.radio("طريقة النطاق 2 الافتراضية في الحاسبة", ["location", "market"],
                      index=0 if get_setting("scope2_method", "location") == "location" else 1, horizontal=True)
        if st.button("حفظ الإعدادات"):
            set_setting("display_unit", "tonne" if unit_pick.startswith("طن") else "kg")
            set_setting("default_country", dc)
            set_setting("scope2_method", sm)
            st.success("تم الحفظ.")
        st.divider()
        st.markdown("**النسخ الاحتياطي**")
        st.caption(f"ملف قاعدة البيانات: {db_path()}")
        if st.button("إنشاء نسخة احتياطية الآن"):
            st.success(f"تم: {backup_file(label='manual')}")
        st.caption("الاستعادة تتم من سطر الأوامر عمدًا: python scripts\\db_admin.py restore <الملف> (تُحفظ النسخة الحالية أولًا).")
    st.info(
        "غير مفعّل بعد: إدارة الحسابات والصلاحيات، مفاتيح خدمات AI، تنسيق التاريخ. "
        "لا تُعرض إعدادات على أنها فعالة ما لم تكن مربوطة بالمنطق."
    )

# ---------- Footer ----------
st.divider()
st.caption(
    "CarbonAI | لا تستخدم النتائج لاتخاذ قرارات رسمية قبل التحقق من عوامل الانبعاث "
    "والمصادر وحدود الحساب."
)
if con is not None:
    con.close()
