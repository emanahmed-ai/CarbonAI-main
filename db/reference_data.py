"""Static reference lists: ISO 3166 countries (starter set), activity categories, Scope 3 categories.

Countries: names/ISO codes only. NO emission data lives here. The list is a *starter set*;
add more with db.seed.add_country(). Presence in this list does NOT mean factors exist for it.
"""

# (iso2, iso3, name_en, name_ar, region)
COUNTRIES = [
    ("EG","EGY","Egypt","مصر","Africa / MENA"), ("SA","SAU","Saudi Arabia","السعودية","Middle East / MENA"),
    ("AE","ARE","United Arab Emirates","الإمارات","Middle East / MENA"), ("JO","JOR","Jordan","الأردن","Middle East / MENA"),
    ("MA","MAR","Morocco","المغرب","Africa / MENA"), ("DZ","DZA","Algeria","الجزائر","Africa / MENA"),
    ("TN","TUN","Tunisia","تونس","Africa / MENA"), ("LY","LBY","Libya","ليبيا","Africa / MENA"),
    ("SD","SDN","Sudan","السودان","Africa / MENA"), ("IQ","IRQ","Iraq","العراق","Middle East / MENA"),
    ("SY","SYR","Syria","سوريا","Middle East / MENA"), ("LB","LBN","Lebanon","لبنان","Middle East / MENA"),
    ("PS","PSE","Palestine","فلسطين","Middle East / MENA"), ("KW","KWT","Kuwait","الكويت","Middle East / MENA"),
    ("QA","QAT","Qatar","قطر","Middle East / MENA"), ("BH","BHR","Bahrain","البحرين","Middle East / MENA"),
    ("OM","OMN","Oman","عُمان","Middle East / MENA"), ("YE","YEM","Yemen","اليمن","Middle East / MENA"),
    ("TR","TUR","Türkiye","تركيا","Europe / Asia"),
    ("DE","DEU","Germany","ألمانيا","Europe"), ("FR","FRA","France","فرنسا","Europe"),
    ("GB","GBR","United Kingdom","المملكة المتحدة","Europe"), ("IT","ITA","Italy","إيطاليا","Europe"),
    ("ES","ESP","Spain","إسبانيا","Europe"), ("NL","NLD","Netherlands","هولندا","Europe"),
    ("SE","SWE","Sweden","السويد","Europe"), ("CH","CHE","Switzerland","سويسرا","Europe"),
    ("US","USA","United States","الولايات المتحدة","North America"), ("CA","CAN","Canada","كندا","North America"),
    ("MX","MEX","Mexico","المكسيك","North America"), ("BR","BRA","Brazil","البرازيل","South America"),
    ("IN","IND","India","الهند","Asia"), ("CN","CHN","China","الصين","Asia"), ("JP","JPN","Japan","اليابان","Asia"),
    ("KR","KOR","South Korea","كوريا الجنوبية","Asia"), ("ID","IDN","Indonesia","إندونيسيا","Asia"),
    ("PK","PAK","Pakistan","باكستان","Asia"),
    ("AU","AUS","Australia","أستراليا","Oceania"), ("NZ","NZL","New Zealand","نيوزيلندا","Oceania"),
    ("ZA","ZAF","South Africa","جنوب أفريقيا","Africa"), ("NG","NGA","Nigeria","نيجيريا","Africa"),
    ("KE","KEN","Kenya","كينيا","Africa"),
]

# key, name_ar, name_en, unified_class, sector, fuels/materials, compatible units, expected scope hint
# expected_scope is only a HINT; the classifier decides from ownership/control/relationship.
CATEGORIES = [
    ("electricity","الكهرباء المشتراة","Purchased electricity","Energy","All","grid","kWh,MWh,MJ,GJ","Scope 2 if purchased & consumed in controlled operations"),
    ("purchased_heat_steam","البخار/التدفئة/التبريد المشترى","Purchased steam, heat, cooling","Energy","All","steam,heat,cooling","kWh,MWh,MJ,GJ","Scope 2 if purchased & consumed in controlled operations"),
    ("stationary_fuel","وقود ثابت (غلايات/أفران/مولدات)","Stationary combustion fuel","Fuel","All","diesel,lpg,natural_gas,coal,fuel_oil","kg,tonne,litre,m3,kWh,GJ","Scope 1 if source controlled by the company"),
    ("mobile_fuel","وقود متحرك (مركبات)","Mobile combustion fuel (vehicles)","Fuel","Transport","diesel,petrol","litre,kg,kWh","Scope 1 if vehicle controlled; otherwise Scope 3"),
    ("refrigerant","غازات التبريد (تسربات)","Refrigerant leakage","Fugitive","All","hfc,hcfc","kg","Scope 1 if equipment controlled"),
    ("process_emissions","عمليات صناعية","Industrial process emissions","Process","Industry","","tonne,kg","Scope 1 if process controlled"),
    ("transport_freight","نقل وشحن","Freight transport","Transport","Transport","road,rail,sea,air","tkm,km","Depends: own fleet S1; third party S3 cat 4/9"),
    ("business_travel","سفر الأعمال","Business travel","Travel","All","air,rail,car,hotel","pkm,km,room_night","Scope 3 cat 6"),
    ("employee_commuting","تنقل الموظفين","Employee commuting","Travel","All","car,bus,rail","pkm,km","Scope 3 cat 7"),
    ("waste","المخلفات","Waste generated in operations","Waste","All","landfill,recycling,incineration","kg,tonne","Scope 3 cat 5 if treated by third party"),
    ("water","المياه","Water supply and treatment","Water","All","supply,wastewater","m3,litre","Usually Scope 3 (confirm)"),
    ("purchased_goods","سلع وخدمات مشتراة","Purchased goods and services","Purchased","All","","kg,tonne,unit","Scope 3 cat 1"),
    ("capital_goods","سلع رأسمالية","Capital goods","Purchased","All","","kg,tonne,unit","Scope 3 cat 2"),
    ("other","أخرى / غير مصنف","Other / unclassified","Other","All","","","Undetermined"),
]

SCOPE3_CATEGORIES = {
    1: ("Purchased goods and services", "السلع والخدمات المشتراة"),
    2: ("Capital goods", "السلع الرأسمالية"),
    3: ("Fuel- and energy-related activities (not in Scope 1 or 2)", "أنشطة الوقود والطاقة غير الداخلة في النطاق 1 أو 2"),
    4: ("Upstream transportation and distribution", "النقل والتوزيع في المراحل السابقة"),
    5: ("Waste generated in operations", "المخلفات الناتجة عن العمليات"),
    6: ("Business travel", "سفر الأعمال"),
    7: ("Employee commuting", "تنقل الموظفين"),
    8: ("Upstream leased assets", "الأصول المستأجرة (المراحل السابقة)"),
    9: ("Downstream transportation and distribution", "النقل والتوزيع في المراحل اللاحقة"),
    10: ("Processing of sold products", "معالجة المنتجات المباعة"),
    11: ("Use of sold products", "استخدام المنتجات المباعة"),
    12: ("End-of-life treatment of sold products", "نهاية عمر المنتجات المباعة"),
    13: ("Downstream leased assets", "الأصول المؤجَّرة للغير"),
    14: ("Franchises", "الامتيازات التجارية"),
    15: ("Investments", "الاستثمارات"),
}
