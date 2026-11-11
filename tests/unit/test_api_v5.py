"""v5 tests: import background job, nearest-year factor selection, admin-only factor API,
settings backup ZIP, factory reset, plan measured results and the API 404 contract."""
from __future__ import annotations

import io
import json
import os
import tempfile
import time
import unittest
import zipfile
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
        self.fac_b = self.client.post("/api/org/facilities", headers=self.admin,
                                      json={"name": "Factory B", "country_code": "EG"}).json()

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

    def _record(self, headers=None, facility_id=None, name="diesel", date="2026-02-01", qty="1000",
                category="stationary_fuel", unit="litre", manual="2.68") -> dict:
        body = {"activity_name": name, "quantity": qty, "unit": unit, "activity_date": date,
                "category_key": category, "country_code": "EG",
                "ownership_control": "owned_controlled", "energy_purchased": "no",
                "manual_factor": {"value": manual, "source": "test"}}
        if facility_id:
            body["facility_id"] = facility_id
        r = self.client.post("/api/records", headers=headers or self.admin, json=body)
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()


class ImportJob(Base):
    def _csv(self, n=300, tag="a") -> bytes:
        lines = ["activity,qty,uom,date"]
        for i in range(n):
            lines.append(f"diesel {tag} {i},{100 + i % 7},litre,2026-03-15")
        return ("\n".join(lines)).encode()

    def test_background_job_progress_and_records(self):
        data = self._csv(300)
        r = self.client.post("/api/imports/jobs", headers=self.admin,
                             files={"file": ("job.csv", data, "text/csv")},
                             data={"mapping": json.dumps({"activity": "activity", "quantity": "qty",
                                                          "unit": "uom", "date": "date"}),
                                   "default_country": "EG"})
        self.assertEqual(r.status_code, 202, r.text)
        jid = r.json()["job_id"]
        job = None
        for _ in range(120):
            job = self.client.get(f"/api/imports/jobs/{jid}", headers=self.admin).json()
            if job["status"] in ("done", "error"):
                break
            time.sleep(0.1)
        self.assertEqual(job["status"], "done", job)
        self.assertEqual(job["total"], 300)
        self.assertEqual(job["added"], 300)
        self.assertEqual(job["percent"], 100.0)
        rows = self.client.get("/api/records", headers=self.admin, params={"page_size": 5}).json()
        self.assertEqual(rows["total"], 300)
        # identical file is rejected unless forced (and the batch hash is stored)
        dup = self.client.post("/api/imports/jobs", headers=self.admin,
                               files={"file": ("job.csv", data, "text/csv")},
                               data={"mapping": json.dumps({"activity": "activity", "quantity": "qty",
                                                            "unit": "uom", "date": "date"}),
                                     "default_country": "EG"})
        self.assertEqual(dup.status_code, 409)

    def test_raw_preview_pagination_and_sheets(self):
        data = self._csv(250, "b")
        r = self.client.post("/api/imports/raw-preview", headers=self.admin,
                             files={"file": ("p.csv", data, "text/csv")},
                             data={"page": "2", "page_size": "100"})
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["total"], 250)
        self.assertEqual(len(body["rows"]), 100)
        self.assertEqual(body["page"], 2)


class NearestYear(Base):
    def test_suggest_includes_nearest_year(self):
        sg = self.client.get("/api/factors/suggest", headers=self.admin,
                             params={"country": "EG", "category": "electricity", "year": 2026,
                                     "unit": "kWh"}).json()
        self.assertTrue(sg["nearest"], sg)
        near = sg["nearest"][0]
        self.assertEqual(near["factor_id"], "EG-EEHC-THERMAL-INTENSITY-FY2023-24")
        self.assertEqual(near["distance_years"], 2)

    def test_nearest_year_record_is_marked_estimated(self):
        r = self.client.post("/api/records", headers=self.admin, json={
            "activity_name": "EEHC nearest", "quantity": "1000", "unit": "kWh",
            "activity_date": "2026-02-01", "category_key": "electricity", "country_code": "EG",
            "facility_id": self.fac["facility_id"], "ownership_control": "owned_controlled",
            "energy_purchased": "yes",
            "factor": {"factor_id": "EG-EEHC-THERMAL-INTENSITY-FY2023-24", "nearest_ok": True}})
        self.assertEqual(r.status_code, 201, r.text)
        rec = r.json()["record"]
        self.assertEqual(float(rec["kg_co2e"]), 1000 * 0.3803)
        self.assertIn("ESTIMATED", rec["calc_notes"])
        # without nearest_ok the engine still enforces the validity year
        bad = self.client.post("/api/records", headers=self.admin, json={
            "activity_name": "EEHC strict", "quantity": "1", "unit": "kWh",
            "activity_date": "2026-02-01", "category_key": "electricity", "country_code": "EG",
            "facility_id": self.fac["facility_id"],
            "factor": {"factor_id": "EG-EEHC-THERMAL-INTENSITY-FY2023-24"}})
        self.assertEqual(bad.status_code, 201, bad.text)
        self.assertEqual(bad.json()["record"]["calc_status"], "needs_review")

    def test_factor_api_admin_only(self):
        hm = self._user("mgr_fx", self.fac["facility_id"])
        self.assertEqual(self.client.get("/api/factors", headers=hm).status_code, 403)
        self.assertEqual(self.client.get("/api/factors/egypt", headers=hm).status_code, 403)
        self.assertEqual(self.client.get("/api/factors/coverage-matrix", headers=hm).status_code, 403)
        # factor suggestion stays available for calculations
        self.assertEqual(self.client.get("/api/factors/suggest", headers=hm,
                                         params={"country": "EG", "category": "electricity",
                                                 "year": 2024, "unit": "kWh"}).status_code, 200)


class SettingsOps(Base):
    def test_backup_zip_contains_factory_data(self):
        self._record(facility_id=self.fac["facility_id"])
        r = self.client.get("/api/settings/backup.zip", headers=self.admin,
                            params={"facility_id": self.fac["facility_id"]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.headers["content-type"], "application/zip")
        z = zipfile.ZipFile(io.BytesIO(r.content))
        self.assertIn("data.json", z.namelist())
        data = json.loads(z.read("data.json"))
        self.assertEqual(data["format"], "carbonai.factory-backup/1")
        self.assertEqual(len(data["activity_records"]), 1)

    def test_backup_cannot_cross_company_for_head_office(self):
        # second company + facility, created by admin
        self.client.post("/api/org/companies", headers=self.admin, json={"name": "Other Co"})
        self.client.post("/api/org/facilities", headers=self.admin,
                         json={"company_id": self.fac_b["company_id"], "name": "Own B"})
        self.client.post("/api/users", headers=self.admin, json={
            "username": "hq_ops", "password": "UserPass1!", "role": "head_office"})
        hh = {"Authorization": f"Bearer {self._login('hq_ops', 'UserPass1!')}"}
        # head office of company 1 cannot back up another company's facility
        r = self.client.get("/api/settings/backup.zip", headers=hh,
                            params={"facility_id": 999999})
        self.assertIn(r.status_code, (403, 404))

    def test_factory_reset_requires_password_and_preserves_others(self):
        self._record(facility_id=self.fac["facility_id"], name="A record")
        self._record(facility_id=self.fac_b["facility_id"], name="B record")
        inv = self.client.post("/api/invoices", headers=self.admin, data={
            "invoice_name": "inv A", "facility_id": str(self.fac["facility_id"]),
            "invoice_number": "INV-A", "supplier": "S", "invoice_date": "2026-01-31",
            "category_key": "electricity", "quantity": "10", "unit": "kWh"})
        self.assertEqual(inv.status_code, 201, inv.text)
        # wrong password
        bad = self.client.post("/api/settings/factory-reset", headers=self.admin, json={
            "password": "wrong", "facility_id": self.fac["facility_id"], "confirm": "DELETE"})
        self.assertEqual(bad.status_code, 403)
        # missing confirmation
        no_conf = self.client.post("/api/settings/factory-reset", headers=self.admin, json={
            "password": ADMIN_PW, "facility_id": self.fac["facility_id"], "confirm": ""})
        self.assertEqual(no_conf.status_code, 400)
        ok = self.client.post("/api/settings/factory-reset", headers=self.admin, json={
            "password": ADMIN_PW, "facility_id": self.fac["facility_id"],
            "confirm": "DELETE", "reason": "test reset"})
        self.assertEqual(ok.status_code, 200, ok.text)
        body = ok.json()
        self.assertGreaterEqual(body["deleted"]["records"], 1)
        self.assertGreaterEqual(body["deleted"]["invoices"], 1)
        self.assertTrue(Path(body["backup"]).exists())
        a_rows = self.client.get("/api/records", headers=self.admin,
                                 params={"facility_id": self.fac["facility_id"]}).json()
        b_rows = self.client.get("/api/records", headers=self.admin,
                                 params={"facility_id": self.fac_b["facility_id"]}).json()
        self.assertEqual(a_rows["total"], 0)
        self.assertEqual(b_rows["total"], 1, "other factory data must be untouched")
        # users and factors survived
        self.assertEqual(self.client.get("/api/users", headers=self.admin).status_code, 200)
        factors = self.client.get("/api/factors/egypt", headers=self.admin).json()
        ids = {f["factor_id"] for f in factors}
        self.assertIn("EG-EEHC-THERMAL-INTENSITY-FY2023-24", ids)
        self.assertFalse(any(i.startswith("NZ-") for i in ids))


class PlanResults(Base):
    def test_measured_results_from_ledger(self):
        self._record(facility_id=self.fac["facility_id"], date="2025-06-01", qty="1000")  # 2680 kg baseline year
        self._record(facility_id=self.fac["facility_id"], date="2026-06-01", qty="900")   # 2412 kg plan year
        plan = self.client.post("/api/plans", headers=self.admin, json={
            "area": "Fuel efficiency", "linked_category_key": "stationary_fuel",
            "plan_year": 2026, "expected_reduction_pct": 5, "kpi": "litre/tonne",
            "reference_source": "internal audit", "status": "in_progress"})
        self.assertEqual(plan.status_code, 201, plan.text)
        pid = plan.json()["plan_id"]
        res = self.client.get(f"/api/plans/{pid}/results", headers=self.admin).json()
        self.assertEqual(res["measured"], True)
        self.assertEqual(float(res["baseline_kg"]), 2680.0)
        self.assertEqual(float(res["actual_kg"]), 2412.0)
        self.assertAlmostEqual(res["reduction_pct"], 10.0, places=1)
        self.assertEqual(res["status"], "achieved")

    def test_unknown_api_path_is_json_404(self):
        r = self.client.get("/api/does-not-exist", headers=self.admin)
        self.assertEqual(r.status_code, 404)
        self.assertIn("detail", r.json())


if __name__ == "__main__":
    unittest.main()
