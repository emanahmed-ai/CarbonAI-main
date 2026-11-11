"""Integration tests for the v3 upgrade: Egypt factor database, intelligent import,
invoices, forecasting lifecycle, detailed reports, reduction plans and admin-only safeguards.
Uses isolated temp databases (same convention as test_api.py)."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from api.main import app

ADMIN_PW = "AdminPass1!"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["CARBONAI_DB_PATH"] = str(Path(self.tmp.name) / "t.db")
        os.environ["CARBONAI_ADMIN_PASSWORD"] = ADMIN_PW
        from api import security
        security.reset_secret_cache()
        self.client = TestClient(app)
        self.client.__enter__()
        self.admin = {"Authorization": f"Bearer {self._login('admin', ADMIN_PW)}"}
        r = self.client.post("/api/org/facilities", headers=self.admin,
                             json={"name": "Factory A", "country_code": "EG"})
        self.fac = r.json()
        r2 = self.client.post("/api/org/facilities", headers=self.admin,
                              json={"name": "Factory B", "country_code": "EG"})
        self.fac_b = r2.json()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.tmp.cleanup()

    def _login(self, username: str, password: str) -> str:
        r = self.client.post("/api/auth/login", json={"username": username, "password": password})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["token"]

    def _user(self, username: str, facility_id: int, role: str = "factory_manager") -> dict:
        r = self.client.post("/api/users", headers=self.admin, json={
            "username": username, "password": "UserPass1!", "role": role, "facility_id": facility_id})
        self.assertEqual(r.status_code, 201, r.text)
        return {"Authorization": f"Bearer {self._login(username, 'UserPass1!')}"}

    def _record(self, headers, *, facility_id=None, name="fuel", qty="1000", date="2025-03-15",
                control="owned_controlled", energy="no", fval="2.68", category="stationary_fuel",
                unit="litre") -> dict:
        body = {"activity_name": name, "quantity": qty, "unit": unit, "activity_date": date,
                "category_key": category, "country_code": "EG", "ownership_control": control,
                "energy_purchased": energy,
                "manual_factor": {"value": fval, "source": "test source"}}
        if facility_id is not None:
            body["facility_id"] = facility_id
        r = self.client.post("/api/records", headers=headers, json=body)
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()


class EgyptFactorDatabase(Base):
    def test_seed_has_official_and_defaults_no_legacy_nz(self):
        rows = self.client.get("/api/factors/egypt", headers=self.admin).json()
        ids = [r["factor_id"] for r in rows]
        self.assertIn("EG-EEHC-THERMAL-INTENSITY-FY2023-24", ids)
        self.assertFalse(any(i.startswith("NZ-") for i in ids), "no NZ factors on a fresh install")
        ee = next(r for r in rows if r["factor_id"].startswith("EG-EEHC"))
        self.assertEqual(ee["country_scope"], "egypt_official")
        self.assertEqual(ee["co2e_factor_value"], "0.3803")
        self.assertIn("EEHC", ee["source_organization"])
        self.assertIn("380.3", ee["source_page"] + ee["methodology"] + ee["source_locator"])
        # every factor carries a source organization and document
        for r in rows:
            self.assertTrue(r["source_organization"], r["factor_id"])
            self.assertTrue(r["source_document"], r["factor_id"])

    def test_only_four_classifications_used(self):
        rows = self.client.get("/api/factors/egypt", headers=self.admin).json()
        scopes = {r["country_scope"] for r in rows}
        self.assertTrue(scopes <= {"egypt_official", "egypt_research",
                                   "international_egypt_specific", "international_default"},
                        scopes)
        self.assertNotIn("international_default", {r["country_scope"] for r in rows
                                                   if r["country_code"] == "EG"})

    def test_coverage_matrix_every_year(self):
        m = self.client.get("/api/factors/coverage-matrix", headers=self.admin).json()
        self.assertEqual(len(m["summary"]), 21)
        self.assertEqual([y["year"] for y in m["summary"]], list(range(2006, 2027)))
        for y in m["summary"]:
            self.assertTrue(y["statuses"], f"year {y['year']} has no status")
        y2024 = next(y for y in m["summary"] if y["year"] == 2024)
        self.assertEqual(y2024["statuses"].get("available"), 1)
        y2025 = next(y for y in m["summary"] if y["year"] == 2025)
        y2026 = next(y for y in m["summary"] if y["year"] == 2026)
        self.assertEqual(y2025["statuses"].get("available", 0), 0)
        self.assertEqual(y2026["statuses"].get("available", 0), 0)
        self.assertGreater(y2025["statuses"].get("pending", 0), 0)
        self.assertGreater(y2026["statuses"].get("pending", 0), 0)

    def test_default_country_is_egypt(self):
        s = self.client.get("/api/settings", headers=self.admin).json()
        self.assertEqual(s.get("default_country"), "EG")

    def test_factor_management_is_admin_only(self):
        hm = self._user("mgr_f", self.fac["facility_id"])
        body = {"factor_id": "TEST-X", "country_code": "EG", "factor_class": "official_national",
                "category": "electricity", "activity": "test", "unit": "kWh", "value": "0.5",
                "year_from": 2024, "year_to": 2025, "source_organization": "X",
                "source_document": "Y", "source_locator": "p.1", "reason": "test"}
        self.assertEqual(self.client.post("/api/factors", headers=hm, json=body).status_code, 403)
        # head office is also denied (admin-only per specification)
        r = self.client.post("/api/users", headers=self.admin,
                             json={"username": "hq_f", "password": "UserPass1!", "role": "head_office"})
        hh = {"Authorization": f"Bearer {self._login('hq_f', 'UserPass1!')}"}
        self.assertEqual(self.client.post("/api/factors", headers=hh, json=body).status_code, 403)
        self.assertEqual(self.client.post("/api/factors", headers=self.admin, json=body).status_code, 201)
        # verify is admin-only, and now REQUIRES EVIDENCE: without a registered reference or
        # reviewer range the verification is refused (400) instead of silently passing
        self.assertEqual(self.client.post("/api/factors/TEST-X/1/verify", headers=hh,
                                          json={"status": "verified", "reviewer_reason": "r"}).status_code, 403)
        no_evidence = self.client.post("/api/factors/TEST-X/1/verify", headers=self.admin,
                                       json={"status": "verified", "reviewer_reason": "checked"})
        self.assertEqual(no_evidence.status_code, 400)
        self.assertEqual(no_evidence.json()["detail"]["comparison"]["status_overall"],
                         "no_reference_available")
        with_range = self.client.post("/api/factors/TEST-X/1/verify", headers=self.admin, json={
            "status": "verified", "reviewer_reason": "checked",
            "expected_min": "0.4", "expected_max": "0.6"})
        self.assertEqual(with_range.status_code, 200, with_range.text)
        self.assertEqual(with_range.json()["comparison"]["status_overall"], "within_range")


class SmartImport(Base):
    def _csv(self) -> bytes:
        # messy Arabic + English headers, none matching the internal template exactly
        return ("بيان البند,كمية الاستهلاك,وحدة القياس,تاريخ الفاتورة,اسم المورد\n"
                "وقود ديزل,500,litre,2026-02-01,مورد الوقود\n"
                "كهرباء,12000,kWh,2026-02-05,شركة الكهرباء\n").encode("utf-8-sig")

    def test_analyze_recognises_synonyms(self):
        a = self.client.post("/api/imports/analyze", headers=self.admin,
                             files={"file": ("messy.csv", self._csv(), "text/csv")}).json()
        s = a["suggestions"]
        self.assertEqual(s["quantity"]["column"], "كمية الاستهلاك")
        self.assertEqual(s["unit"]["column"], "وحدة القياس")
        self.assertEqual(s["date"]["column"], "تاريخ الفاتورة")
        self.assertGreaterEqual(s["quantity"]["confidence"], 0.9)
        self.assertIn("file_hash", a)
        self.assertIsNone(a["duplicate_file"])

    def test_preview_and_commit_mapped(self):
        a = self.client.post("/api/imports/analyze", headers=self.admin,
                             files={"file": ("messy.csv", self._csv(), "text/csv")}).json()
        mp = {k: v["column"] for k, v in a["suggestions"].items()}
        pv = self.client.post("/api/imports/preview-mapped", headers=self.admin,
                              files={"file": ("messy.csv", self._csv(), "text/csv")},
                              data={"mapping": json.dumps(mp), "default_country": "EG"}).json()
        self.assertEqual(len(pv["accepted"]), 2)
        self.assertEqual(pv["accepted"][0]["quantity"], "500.0")
        cm = self.client.post("/api/imports/commit-mapped", headers=self.admin,
                              files={"file": ("messy.csv", self._csv(), "text/csv")},
                              data={"mapping": json.dumps(mp), "default_country": "EG"})
        self.assertEqual(cm.status_code, 200, cm.text)
        self.assertEqual(cm.json()["added"], 2)
        rows = self.client.get("/api/records", headers=self.admin).json()
        self.assertEqual(rows["total"], 2)

    def test_same_file_hash_blocked(self):
        self.client.post("/api/imports/commit-mapped", headers=self.admin,
                         files={"file": ("a.csv", self._csv(), "text/csv")},
                         data={"mapping": json.dumps({"activity": "بيان البند", "quantity": "كمية الاستهلاك",
                                                      "unit": "وحدة القياس", "date": "تاريخ الفاتورة"}),
                               "default_country": "EG"})
        dup = self.client.post("/api/imports/commit-mapped", headers=self.admin,
                               files={"file": ("a.csv", self._csv(), "text/csv")},
                               data={"mapping": json.dumps({"activity": "بيان البند", "quantity": "كمية الاستهلاك",
                                                            "unit": "وحدة القياس", "date": "تاريخ الفاتورة"}),
                                     "default_country": "EG"})
        self.assertEqual(dup.status_code, 409)
        forced = self.client.post("/api/imports/commit-mapped", headers=self.admin,
                                  files={"file": ("a.csv", self._csv(), "text/csv")},
                                  data={"mapping": json.dumps({"activity": "بيان البند", "quantity": "كمية الاستهلاك",
                                                               "unit": "وحدة القياس", "date": "تاريخ الفاتورة"}),
                                        "default_country": "EG", "force": "true"})
        self.assertEqual(forced.status_code, 200)  # rows themselves are duplicates -> skipped


class Invoices(Base):
    def _create(self, headers=None, **over):
        data = {"invoice_name": "Electricity Jan", "facility_id": str(self.fac["facility_id"]),
                "invoice_number": "INV-001", "supplier": "Utility Co", "invoice_date": "2026-01-31",
                "period_year": "2026", "period_month": "1", "category_key": "electricity",
                "quantity": "1000", "unit": "kWh", "amount": "2500"}
        data.update(over)
        return self.client.post("/api/invoices", headers=headers or self.admin, data=data)

    def test_create_calculate_link_and_audit(self):
        r = self._create()
        self.assertEqual(r.status_code, 201, r.text)
        iid = r.json()["invoice_id"]
        # no manual factor: the Core selects the Egyptian factor by invoice year (2026 -> nearest 2024)
        calc = self.client.post(f"/api/invoices/{iid}/calculate", headers=self.admin,
                                json={"ownership_control": "owned_controlled", "energy_purchased": "yes"})
        self.assertEqual(calc.status_code, 200, calc.text)
        self.assertAlmostEqual(float(calc.json()["kg_co2e"]), 1000 * 0.3803, places=3)
        self.assertEqual(calc.json()["factor"]["factor_id"], "EG-EEHC-THERMAL-INTENSITY-FY2023-24")
        d = self.client.get(f"/api/invoices/{iid}", headers=self.admin).json()
        self.assertEqual(d["status"], "calculated")
        self.assertEqual(d["scope"], "Scope 2")
        self.assertEqual(len(d["audit"]), 2)  # created + calculated
        # the activity record is linked both ways
        rec = self.client.get(f"/api/records/{d['record_id']}", headers=self.admin).json()
        self.assertEqual(rec["invoice_id"], iid)

    def test_duplicate_metadata_blocked_and_forced(self):
        self._create()
        dup = self._create(invoice_name="same again")
        self.assertEqual(dup.status_code, 409)
        self.assertEqual(dup.json()["detail"]["kind"], "same_metadata")
        forced = self._create(invoice_name="same again", confirm_duplicate="true")
        self.assertEqual(forced.status_code, 201)

    def test_factory_isolation(self):
        hm = self._user("mgr_inv", self.fac["facility_id"])
        r = self._create(headers=hm)
        self.assertEqual(r.status_code, 201)
        iid = r.json()["invoice_id"]
        hb = self._user("mgr_invb", self.fac_b["facility_id"])
        self.assertEqual(self.client.get(f"/api/invoices/{iid}", headers=hb).status_code, 403)
        self.assertEqual(self.client.get("/api/invoices", headers=hb).json(), [])

    def test_search_filters(self):
        self._create()
        self.assertEqual(len(self.client.get("/api/invoices", headers=self.admin,
                                             params={"search": "INV-001"}).json()), 1)
        self.assertEqual(len(self.client.get("/api/invoices", headers=self.admin,
                                             params={"year": 2025}).json()), 0)

    def test_void_keeps_record_and_audit(self):
        iid = self._create().json()["invoice_id"]
        self.client.post(f"/api/invoices/{iid}/calculate", headers=self.admin, json={})
        v = self.client.post(f"/api/invoices/{iid}/void", headers=self.admin,
                             json={"reason": "duplicate entry"})
        self.assertEqual(v.status_code, 200)
        d = self.client.get(f"/api/invoices/{iid}", headers=self.admin).json()
        self.assertEqual(d["status"], "void")
        self.assertTrue(any(a["action"] == "voided" for a in d["audit"]))
        # voiding does not delete the linked ledger record (audit trail preserved)
        self.assertIsNotNone(d["record_id"])


class ForecastLifecycle(Base):
    def _seed_months(self, n=14):
        months = [(2025, m) for m in range(1, 13)] + [(2026, m) for m in range(1, 3)]
        for i, (y, m) in enumerate(months[:n]):
            self._record(self.admin, facility_id=self.fac["facility_id"],
                         name=f"fuel {y}-{m:02d}", date=f"{y}-{m:02d}-10",
                         qty=str(1000 + i * 50))

    def test_insufficient_data_is_explicit(self):
        self._record(self.admin, facility_id=self.fac["facility_id"])
        st = self.client.get("/api/ml/forecast", headers=self.admin).json()
        self.assertIn(st["status"], ("INSUFFICIENT_DATA", "NO_ACTIVE_MODEL"))
        tr = self.client.post("/api/ml/train", headers=self.admin, json={})
        self.assertEqual(tr.status_code, 409)
        self.assertEqual(tr.json()["detail"]["status"], "INSUFFICIENT_DATA")

    def test_train_activate_forecast_no_retrain(self):
        self._seed_months()
        tr = self.client.post("/api/ml/train", headers=self.admin, json={})
        self.assertEqual(tr.status_code, 200, tr.text)
        body = tr.json()
        self.assertFalse(body["skipped"])
        self.assertEqual(body["status"], "staged")
        mid = body["model_id"]
        # prediction without an active model must not fabricate a forecast
        st = self.client.get("/api/ml/forecast", headers=self.admin).json()
        self.assertEqual(st["status"], "NO_ACTIVE_MODEL")
        act = self.client.post(f"/api/ml/models/{mid}/activate", headers=self.admin)
        self.assertEqual(act.status_code, 200)
        fc = self.client.get("/api/ml/forecast", headers=self.admin, params={"horizon": 6}).json()
        self.assertEqual(fc["status"], "OK")
        self.assertEqual(len(fc["forecast"]), 6)
        self.assertEqual(fc["model"]["model_id"], mid)
        self.assertIsNotNone(fc["annual_forecast_kg"])
        self.assertIn("band_note", fc)
        # training again with unchanged data must reuse the active model
        tr2 = self.client.post("/api/ml/train", headers=self.admin, json={})
        self.assertEqual(tr2.status_code, 200)
        self.assertTrue(tr2.json()["skipped"])
        # metrics include the seasonal-naive baseline comparison
        self.assertIn("seasonal_naive", body["metrics"])
        # factory users cannot train or activate
        hm = self._user("mgr_ml", self.fac["facility_id"])
        self.assertEqual(self.client.post("/api/ml/train", headers=hm, json={}).status_code, 403)
        self.assertEqual(self.client.post(f"/api/ml/models/{mid}/activate", headers=hm).status_code, 403)


class ReportsPlans(Base):
    def test_detailed_and_annual_pdfs(self):
        self._record(self.admin, facility_id=self.fac["facility_id"], date="2026-01-15")
        d = self.client.get("/api/reports/pdf-detailed", headers=self.admin, params={"year": 2026})
        self.assertEqual(d.status_code, 200)
        self.assertTrue(d.content.startswith(b"%PDF"))
        a = self.client.get("/api/reports/annual", headers=self.admin, params={"year": 2026})
        self.assertEqual(a.status_code, 200)
        self.assertTrue(a.content.startswith(b"%PDF"))

    def test_plan_percentage_requires_source_and_kpi(self):
        base = {"area": "Electricity efficiency", "description": "audit", "status": "planned",
                "expected_reduction_pct": 12}
        r1 = self.client.post("/api/plans", headers=self.admin, json=base)
        self.assertEqual(r1.status_code, 400)
        r2 = self.client.post("/api/plans", headers=self.admin,
                              json={**base, "reference_source": "ISO 50001 audit", "kpi": "kWh/unit"})
        self.assertEqual(r2.status_code, 201)

    def test_targets_and_roadmap(self):
        self._record(self.admin, facility_id=self.fac["facility_id"], date="2025-06-15", qty="1000")
        t = self.client.post("/api/plans/targets", headers=self.admin,
                             json={"baseline_year": 2025, "target_year": 2026, "reduction_pct": 10})
        self.assertEqual(t.status_code, 201, t.text)
        self.assertAlmostEqual(t.json()["target_reduction_pct"], 10.0, places=1)
        rm = self.client.get("/api/plans/roadmap", headers=self.admin).json()
        years = {r["year"]: r for r in rm["years"]}
        self.assertIn(2026, years)
        self.assertIsNotNone(years[2026]["target_kg"])
        self.assertEqual(years[2025]["actual_kg"], "2680")  # 1000 litre x 2.68

    def test_insights_use_actual_data(self):
        self._record(self.admin, facility_id=self.fac["facility_id"], qty="1000")
        ins = self.client.get("/api/plans/insights", headers=self.admin).json()
        self.assertEqual(ins["top_scope"], "Scope 1")
        self.assertTrue(any(s["category_key"] == "stationary_fuel" for s in ins["suggestions"]))
        self.assertIn("disclaimer", ins)

    def test_dashboard_scope_kpi_and_comparison(self):
        self._record(self.admin, facility_id=self.fac["facility_id"], date="2026-01-15", qty="1000")
        s = self.client.get("/api/dashboard/summary", headers=self.admin,
                            params={"year": 2026, "month": 1}).json()
        shares = {k["scope"]: k["share_pct"] for k in s["scopes_kpi"]}
        self.assertAlmostEqual(shares["Scope 1"], 100.0, places=1)
        self.assertFalse(s["comparison"]["comparable"])  # 2025-01 has no data
        self.assertIsNone(s["comparison"]["change_pct"])


if __name__ == "__main__":
    unittest.main()
