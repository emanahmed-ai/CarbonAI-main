"""v6 tests: verify evidence comparison, references-for-country, weighted plan overview,
scope sanity with mixed data, and Dashboard/Plans number consistency."""
from __future__ import annotations

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
        self.fac = self.client.post("/api/org/facilities", headers=self.admin,
                                    json={"name": "Factory A", "country_code": "EG"}).json()

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

    def _record(self, *, facility_id=None, name="diesel", date="2026-02-01", qty="1000",
                category="stationary_fuel", unit="litre", manual="2.68",
                control="owned_controlled", energy="no", relation="unknown") -> dict:
        body = {"activity_name": name, "quantity": qty, "unit": unit, "activity_date": date,
                "category_key": category, "country_code": "EG",
                "ownership_control": control, "energy_purchased": energy,
                "value_chain_relation": relation,
                "manual_factor": {"value": manual, "source": "test"}}
        body["facility_id"] = facility_id or self.fac["facility_id"]
        r = self.client.post("/api/records", headers=self.admin, json=body)
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()


class VerifyEvidence(Base):
    def test_no_reference_blocks_verification(self):
        cmp = self.client.get("/api/factors/EG-EEHC-THERMAL-INTENSITY-FY2023-24/1/verify-preview",
                              headers=self.admin).json()
        self.assertEqual(cmp["status_overall"], "no_reference_available")
        self.assertIn("Manual source check", cmp["reason"])
        self.assertFalse(cmp["can_verify"])
        r = self.client.post("/api/factors/EG-EEHC-THERMAL-INTENSITY-FY2023-24/1/verify",
                             headers=self.admin,
                             json={"status": "verified", "reviewer_reason": "looks fine"})
        self.assertEqual(r.status_code, 400, r.text)
        self.assertEqual(r.json()["detail"]["comparison"]["status_overall"], "no_reference_available")
        self.assertIn("failure_reason", r.json()["detail"])

    def test_matched_against_registered_ipcc_default(self):
        # register a GLOBAL default with the exact same activity/unit/value as the EEHC factor
        self.client.post("/api/factors", headers=self.admin, json={
            "factor_id": "TEST-GRID-EG-GJ", "country_code": "GLOBAL",
            "factor_class": "global_default", "category": "electricity", "activity": "grid_test",
            "unit": "kWh", "value": "0.3803", "year_from": 2024, "year_to": 2026,
            "source_organization": "IPCC", "source_document": "test doc",
            "source_locator": "p.1", "reason": "test fixture"})
        # the EEHC factor has activity 'thermal_generation_intensity', so register the same
        # activity to make the comparison base match exactly
        self.client.post("/api/factors", headers=self.admin, json={
            "factor_id": "TEST-EEHC-BASE", "country_code": "GLOBAL",
            "factor_class": "global_default", "category": "electricity",
            "activity": "thermal_generation_intensity", "unit": "kWh", "value": "0.3803",
            "year_from": 2024, "year_to": 2026, "source_organization": "IPCC",
            "source_document": "test doc", "source_locator": "p.1", "reason": "test fixture"})
        cmp = self.client.get("/api/factors/EG-EEHC-THERMAL-INTENSITY-FY2023-24/1/verify-preview",
                              headers=self.admin).json()
        self.assertEqual(cmp["status_overall"], "matched", cmp)
        self.assertEqual(float(cmp["comparisons"][0]["difference"]), 0.0)
        self.assertTrue(cmp["can_verify"])
        r = self.client.post("/api/factors/EG-EEHC-THERMAL-INTENSITY-FY2023-24/1/verify",
                             headers=self.admin,
                             json={"status": "verified", "reviewer_reason": "matches registered IPCC value"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["comparison"]["status_overall"], "matched")
        audit = self.client.get("/api/factors/audit", headers=self.admin,
                                params={"factor_id": "EG-EEHC-THERMAL-INTENSITY-FY2023-24"}).json()
        self.assertTrue(any("comparison: matched" in (a["reason"] or "") for a in audit))

    def test_reviewer_range_within_and_out(self):
        self.client.post("/api/factors", headers=self.admin, json={
            "factor_id": "TEST-EEHC-BASE2", "country_code": "GLOBAL",
            "factor_class": "global_default", "category": "electricity",
            "activity": "thermal_generation_intensity", "unit": "kWh", "value": "0.5",
            "year_from": 2024, "year_to": 2026, "source_organization": "IPCC",
            "source_document": "test doc", "source_locator": "p.1", "reason": "fixture"})
        within = self.client.get("/api/factors/EG-EEHC-THERMAL-INTENSITY-FY2023-24/1/verify-preview",
                                 headers=self.admin,
                                 params={"expected_min": "0.3", "expected_max": "0.5"}).json()
        self.assertEqual(within["status_overall"], "within_range")
        self.assertTrue(within["can_verify"])
        self.assertAlmostEqual(within["comparisons"][0]["difference_pct"], -23.94, places=1)
        out = self.client.get("/api/factors/EG-EEHC-THERMAL-INTENSITY-FY2023-24/1/verify-preview",
                              headers=self.admin,
                              params={"expected_min": "0.5", "expected_max": "0.6"}).json()
        self.assertEqual(out["status_overall"], "out_of_range")
        self.assertFalse(out["can_verify"])

    def test_verify_still_requires_reason(self):
        r = self.client.post("/api/factors/EG-EEHC-THERMAL-INTENSITY-FY2023-24/1/verify",
                             headers=self.admin, json={"status": "pending_review", "reviewer_reason": ""})
        self.assertEqual(r.status_code, 400)


class RefsForCountry(Base):
    def test_lists_country_specific_and_ipcc(self):
        r = self.client.get("/api/factors/refs-for-country", headers=self.admin,
                            params={"country": "EG"}).json()
        cs_ids = [x["reference_id"] for x in r["country_specific"]]
        self.assertIn("EG-EEHC-AR-2023-24", cs_ids)
        ipcc_ids = [x["reference_id"] for x in r["ipcc_default"]]
        self.assertIn("IPCC-2006-GL", ipcc_ids)
        for x in r["country_specific"]:
            self.assertEqual(x["type"], "country_specific")
        for x in r["ipcc_default"]:
            self.assertEqual(x["type"], "ipcc_default")
            self.assertTrue(x["organization_name"])
        self.assertEqual(r["total"], len(r["country_specific"]) + len(r["ipcc_default"]))

    def test_non_admin_forbidden(self):
        hm = self._user("mgr_rf", self.fac["facility_id"])
        self.assertEqual(self.client.get("/api/factors/refs-for-country", headers=hm,
                                         params={"country": "EG"}).status_code, 403)


class PlanOverview(Base):
    def test_weighted_overall_and_computed_target(self):
        # plan 1: electricity, baseline 1000 stored, actual 500 -> measured 50%, no target
        self._record(category="electricity", unit="kWh", qty="500", manual="1",
                     control="owned_controlled", energy="yes", date="2026-05-01")
        p1 = self.client.post("/api/plans", headers=self.admin, json={
            "area": "Electricity efficiency", "linked_category_key": "electricity",
            "baseline_kg": "1000", "plan_year": 2026, "status": "in_progress"})
        self.assertEqual(p1.status_code, 201, p1.text)
        # plan 2: fuel, baseline 3000 stored, actual 3000 -> 0%, user target 10%
        self._record(category="stationary_fuel", qty="3000", manual="1", date="2026-06-01")
        p2 = self.client.post("/api/plans", headers=self.admin, json={
            "area": "Fuel efficiency", "linked_category_key": "stationary_fuel",
            "baseline_kg": "3000", "plan_year": 2026, "expected_reduction_pct": 10,
            "kpi": "l/t", "reference_source": "audit", "status": "in_progress"})
        self.assertEqual(p2.status_code, 201, p2.text)
        ov = self.client.get("/api/plans/results-overview", headers=self.admin).json()
        self.assertEqual(ov["plans_evaluated"], 2)
        self.assertEqual(float(ov["overall_baseline_kg"]), 4000.0)
        self.assertEqual(float(ov["overall_actual_kg"]), 3500.0)
        self.assertAlmostEqual(ov["overall_measured_reduction_pct"], 12.5, places=1)
        # weighted target: (1000*50 + 3000*10)/4000 = 20.0
        self.assertAlmostEqual(ov["overall_target_reduction_pct"], 20.0, places=1)
        self.assertEqual(ov["overall_target_basis"].split(";")[0],
                         "weighted by baseline emission volume")
        r1 = next(p for p in ov["plans"] if p["plan_id"] == p1.json()["plan_id"])
        self.assertEqual(r1["target_reduction_pct_source"], "computed_from_measured")
        self.assertEqual(r1["target_reduction_pct_computed"], 50.0)
        r2 = next(p for p in ov["plans"] if p["plan_id"] == p2.json()["plan_id"])
        self.assertEqual(r2["target_reduction_pct_source"], "user")

    def test_results_endpoint_includes_computed_target(self):
        self._record(category="electricity", unit="kWh", qty="500", manual="1",
                     control="owned_controlled", energy="yes", date="2026-05-01")
        plan = self.client.post("/api/plans", headers=self.admin, json={
            "area": "Electricity efficiency", "linked_category_key": "electricity",
            "baseline_kg": "1000", "plan_year": 2026}).json()
        res = self.client.get(f"/api/plans/{plan['plan_id']}/results", headers=self.admin).json()
        self.assertEqual(res["target_reduction_pct"], None)
        self.assertEqual(res["target_reduction_pct_computed"], 50.0)
        self.assertEqual(res["target_reduction_pct_source"], "computed_from_measured")


class SanityAndConsistency(Base):
    def test_scope_shares_with_mixed_data(self):
        self._record(category="stationary_fuel", qty="1000", manual="2.68",
                     date="2026-01-10")  # Scope 1: 2680
        self._record(category="electricity", unit="kWh", qty="1000", manual="0.45",
                     control="owned_controlled", energy="yes", date="2026-01-20")  # Scope 2: 450
        self._record(category="transport_freight", qty="100", manual="0.2",
                     control="not_controlled", relation="third_party_upstream",
                     date="2026-01-30")  # Scope 3 cat 4: 20
        s = self.client.get("/api/dashboard/summary", headers=self.admin).json()
        scopes = {k["scope"]: k for k in s["scopes_kpi"]}
        self.assertAlmostEqual(scopes["Scope 1"]["share_pct"], 85.06, places=1)
        self.assertAlmostEqual(scopes["Scope 2"]["share_pct"], 14.28, places=1)
        self.assertAlmostEqual(scopes["Scope 3"]["share_pct"], 0.63, places=1)
        self.assertAlmostEqual(sum(scopes[k]["share_pct"] for k in scopes), 100.0, places=1)

    def test_unscoped_record_counts_as_needs_review_not_emissions(self):
        self._record(category="stationary_fuel", qty="1000", manual="2.68",
                     control="unknown", date="2026-02-01")  # scope undetermined
        s = self.client.get("/api/dashboard/summary", headers=self.admin).json()
        self.assertEqual(s["needs_review"], 1)
        self.assertEqual(float(s["total_kg_co2e"]), 2680.0)
        self.assertEqual(float(s["by_scope_kg"]["Scope 1"]), 0.0)

    def test_dashboard_and_plans_identical_numbers(self):
        self._record(facility_id=self.fac["facility_id"], qty="1000")
        plan = self.client.post("/api/plans", headers=self.admin, json={
            "area": "Fuel efficiency", "linked_category_key": "stationary_fuel",
            "baseline_kg": "2680", "plan_year": 2026}).json()
        dash = self.client.get("/api/dashboard/summary", headers=self.admin).json()
        ins = self.client.get("/api/plans/insights", headers=self.admin).json()
        self.assertEqual(dash["total_kg_co2e"], ins["total_kg"])
        ov = self.client.get("/api/plans/results-overview", headers=self.admin).json()
        # overview aggregates per-plan measured actuals -> identical to the dashboard total
        self.assertEqual(float(ov["overall_actual_kg"]), float(dash["total_kg_co2e"]))


if __name__ == "__main__":
    unittest.main()
