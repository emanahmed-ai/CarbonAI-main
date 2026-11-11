"""Rule-based GHG Protocol scope suggestion. Pure Python, no DB.

It never returns a confident scope when the decisive facts (control, whether energy is purchased,
value-chain relationship) are missing: it returns status 'needs_review' / 'undetermined' plus the
list of missing information. Scope depends on organisational boundary + relationship, NOT on the
emission factor, so this module takes no factor as input.

Method references: GHG Protocol Corporate Standard (operational boundaries), Scope 2 Guidance,
Scope 3 Standard (15 categories). Rules here are a decision aid; the user can always override
(override is logged by the ledger).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from db.reference_data import SCOPE3_CATEGORIES

CONTROLLED = {"owned_controlled", "leased_controlled", "controlled"}
NOT_CONTROLLED = {"not_controlled", "leased_not_controlled"}
REF_S1 = "GHG Protocol Corporate Standard, Ch.4 (operational boundaries)"
REF_S2 = "GHG Protocol Scope 2 Guidance"
REF_S3 = "GHG Protocol Corporate Value Chain (Scope 3) Standard"


@dataclass
class ScopeSuggestion:
    scope: str | None            # 'Scope 1' | 'Scope 2' | 'Scope 3' | None
    subcategory: str | None
    scope3_category: int | None
    status: str                  # suggested | needs_review | undetermined
    confidence: str              # high | medium | low | none
    reason_en: str
    reason_ar: str
    reference: str
    missing: list = field(default_factory=list)

    @property
    def reason(self) -> str:
        return f"{self.reason_ar} | {self.reason_en}"


def _s3(cat, why_en, why_ar, conf="high", status="suggested", missing=None):
    en, ar = SCOPE3_CATEGORIES[cat]
    return ScopeSuggestion("Scope 3", f"Category {cat}: {en}", cat, status, conf, why_en, why_ar, REF_S3, missing or [])


def _need(missing, why_en, why_ar, scope=None, sub=None, conf="none", status="needs_review", ref=REF_S1):
    return ScopeSuggestion(scope, sub, None, status, conf, why_en, why_ar, ref, missing)


def classify(*, category_key: str | None, ownership_control: str = "unknown", energy_purchased: str = "unknown",
             value_chain_relation: str = "unknown", description: str = "") -> ScopeSuggestion:
    """ownership_control: owned_controlled|leased_controlled|leased_not_controlled|not_controlled|unknown
    energy_purchased: yes|no|unknown
    value_chain_relation: own_fleet|on_site_controlled|third_party_upstream|third_party_downstream|
                          employee|business_travel|unknown"""
    cat = (category_key or "").strip() or "other"
    ctl = ownership_control or "unknown"
    rel = value_chain_relation or "unknown"
    controlled, uncontrolled = ctl in CONTROLLED, ctl in NOT_CONTROLLED

    if cat in ("electricity", "purchased_heat_steam"):
        if energy_purchased == "unknown":
            return _need(["energy_purchased"], "Cannot tell whether the energy is purchased (Scope 2) or self-generated "
                         "(fuel burned on site is Scope 1).", "لا يمكن الحسم: هل الطاقة مشتراة (النطاق 2) أم مولَّدة ذاتيًا (وقود النطاق 1)؟", ref=REF_S2)
        if energy_purchased == "no":
            return _need(["fuel_activity_data"], "Self-generated energy: record the fuel burned as Scope 1 instead of "
                         "an energy-consumption record.", "طاقة مولَّدة ذاتيًا: سجّل الوقود المحترق ضمن النطاق 1.", ref=REF_S1)
        if uncontrolled:
            return _s3(8 if ctl == "leased_not_controlled" else 1,
                       "Energy purchased for a facility the company does not control falls outside Scope 2; confirm lease "
                       "terms (upstream leased assets) or other relationship.",
                       "الطاقة لمنشأة لا تسيطر عليها الشركة خارج النطاق 2؛ تحقق من عقد الإيجار.", "low", "needs_review",
                       ["lease_terms_or_relationship"])
        if controlled:
            return ScopeSuggestion("Scope 2", "Purchased electricity" if cat == "electricity" else "Purchased steam/heat/cooling",
                                   None, "suggested", "high", "Purchased energy consumed in operations the company controls.",
                                   "طاقة مشتراة تُستهلك في عمليات تخضع لسيطرة الشركة.", REF_S2)
        return ScopeSuggestion("Scope 2", "Purchased energy", None, "needs_review", "medium",
                               "Purchased energy is normally Scope 2, but control of the facility is unknown.",
                               "الطاقة المشتراة عادةً النطاق 2 لكن حالة السيطرة على المنشأة غير معروفة.", REF_S2, ["ownership_control"])

    if cat in ("stationary_fuel", "refrigerant", "process_emissions"):
        label = {"stationary_fuel": "Stationary combustion", "refrigerant": "Fugitive (refrigerant)",
                 "process_emissions": "Process emissions"}[cat]
        if controlled:
            return ScopeSuggestion("Scope 1", label, None, "suggested", "high",
                                   "Direct emissions from a source the company owns or controls.",
                                   "انبعاثات مباشرة من مصدر تملكه الشركة أو تسيطر عليه.", REF_S1)
        if uncontrolled:
            return _need(["value_chain_relationship"], "Source is not controlled by the company, so it is not Scope 1; "
                         "its Scope 3 category depends on the relationship (e.g. purchased goods, leased assets).",
                         "المصدر خارج سيطرة الشركة فليس النطاق 1؛ فئة النطاق 3 تعتمد على طبيعة العلاقة.", ref=REF_S3)
        return _need(["ownership_control"], "Control over the source is unknown; Scope 1 requires ownership or control.",
                     "حالة الملكية/السيطرة غير معروفة؛ النطاق 1 يتطلب ملكية أو سيطرة.")

    if cat in ("mobile_fuel", "transport_freight"):
        if rel == "own_fleet" or (rel == "unknown" and cat == "mobile_fuel" and controlled):
            if controlled:
                return ScopeSuggestion("Scope 1", "Mobile combustion (company-controlled vehicles)", None, "suggested", "high",
                                       "Fuel burned in vehicles the company owns or controls.",
                                       "وقود يُحترق في مركبات تملكها الشركة أو تسيطر عليها.", REF_S1)
            return _need(["ownership_control"], "Own-fleet claim needs confirmation of ownership/control.",
                         "ادّعاء أسطول مملوك يحتاج تأكيد الملكية/السيطرة.")
        if rel == "third_party_upstream":
            return _s3(4, "Transport/distribution by a third party for inbound goods (or paid by the company).",
                       "نقل/توزيع بواسطة طرف ثالث للمدخلات (فئة 4).")
        if rel == "third_party_downstream":
            return _s3(9, "Transport/distribution of sold products after sale, not paid for by the company.",
                       "نقل وتوزيع المنتجات المباعة بعد البيع (فئة 9).", "medium", "suggested")
        if rel == "business_travel":
            return _s3(6, "Vehicle travel for business purposes in vehicles not controlled by the company.", "سفر أعمال (فئة 6).")
        if rel == "employee":
            return _s3(7, "Employee commuting in vehicles not controlled by the company.", "تنقل الموظفين (فئة 7).")
        return _need(["value_chain_relationship", "ownership_control"],
                     "Transport can be Scope 1 (own fleet) or Scope 3 (cat 4, 6, 7, 9) depending on who controls the "
                     "vehicle and the commercial relationship.",
                     "النقل قد يكون النطاق 1 أو 3 حسب من يسيطر على المركبة وطبيعة العلاقة.", ref=REF_S3)

    if cat == "business_travel":
        return _s3(6, "Business travel on transport not controlled by the company.", "سفر الأعمال (فئة 6).")
    if cat == "employee_commuting":
        return _s3(7, "Employee commuting.", "تنقل الموظفين (فئة 7).")
    if cat == "purchased_goods":
        return _s3(1, "Purchased goods and services.", "سلع وخدمات مشتراة (فئة 1).")
    if cat == "capital_goods":
        return _s3(2, "Capital goods.", "سلع رأسمالية (فئة 2).")
    if cat == "waste":
        if rel == "on_site_controlled" and controlled:
            return ScopeSuggestion("Scope 1", "On-site waste treatment (controlled)", None, "suggested", "medium",
                                   "Waste treated on site in equipment the company controls.",
                                   "معالجة مخلفات في الموقع بمعدات تخضع للسيطرة.", REF_S1)
        if rel in ("third_party_upstream", "unknown") and not controlled:
            return _s3(5, "Waste from operations treated by a third party.", "مخلفات العمليات التي يعالجها طرف ثالث (فئة 5).",
                       "medium" if rel == "unknown" else "high", "suggested")
        return _need(["waste_treatment_location"], "Waste scope depends on where/by whom it is treated.",
                     "نطاق المخلفات يعتمد على مكان/جهة المعالجة.", ref=REF_S3)
    if cat == "water":
        return _s3(1, "Purchased water supply/treatment is commonly reported under purchased goods and services; confirm "
                      "against your reporting boundary.", "إمدادات المياه تُدرج عادةً في فئة 1؛ تحقق من حدود التقرير.",
                   "medium", "needs_review", ["reporting_boundary_confirmation"])
    return _need(["category", "ownership_control", "value_chain_relationship"],
                 "Not enough information to determine the scope.", "المعلومات غير كافية لتحديد النطاق.")
