"""End-to-end API tests: auth, RBAC tenancy isolation, multi-factory workflow,
report submissions + consolidation, ML status/predict, reports and imports.

Each test class gets an isolated temp database via CARBONAI_DB_PATH (same convention as
test_db_layer). The FastAPI app is created fresh per class so lifespan seeding runs against it.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("CARBONAI_TESTING", "1")

from fastapi.testclient import TestClient  # noqa: E402

from api.main import app  # noqa: E402

ADMIN_PW = "AdminPass1!"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["CARBONAI_DB_PATH"] = str(Path(self.tmp.name) / "t.db")
        os.environ["CARBONAI_ADMIN_PASSWORD"] = ADMIN_PW
        # fresh app instance per test class so lifespan picks up the fresh DB
        from api import security
        security.reset_secret_cache()
        self.client = TestClient(app)
        # lifespan startup (TestClient context manager runs it)
        self.client.__enter__()
        self.admin = {"Authorization": f"Bearer {self._login('admin', ADMIN_PW)}"}

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.tmp.cleanup()

    def _login(self, username: str, password: str) -> str:
        r = self.client.post("/api/auth/login", json={"username": username, "password": password})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["token"]

    def _mk_facility(self, name: str, country: str = "EG") -> dict:
        r = self.client.post("/api/org/facilities", headers=self.admin,
                             json={"name": name, "country_code": country})
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()

    def _mk_user(self, username: str, facility_id: int, role: str = "factory_manager") -> None:
        r = self.client.post("/api/users", headers=self.admin, json={
            "username": username, "password": "UserPass1!", "role": role,
            "facility_id": facility_id})
        self.assertEqual(r.status_code, 201, r.text)

    def _mk_record(self, headers, *, facility_id=None, name="Gen", qty="100", unit="litre",
                   category="stationary_fuel", date="2025-03-15", control="owned_controlled",
                   factor_value="2.68") -> dict:
        body = {"activity_name": name, "quantity": qty, "unit": unit, "activity_date": date,
                "category_key": category, "country_code": "EG",
                "ownership_control": control, "energy_purchased": "yes",
                "manual_factor": {"value": factor_value, "source": "test source"}}
        if facility_id is not None:
            body["facility_id"] = facility_id
        r = self.client.post("/api/records", headers=headers, json=body)
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()


class Auth(Base):
    def test_login_ok_and_me(self):
        r = self.client.post("/api/auth/login", json={"username": "admin", "password": ADMIN_PW})
        self.assertEqual(r.status_code, 200)
        me = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {r.json()['token']}"}).json()
        self.assertEqual(me["role"], "admin")

    def test_login_wrong_password(self):
        r = self.client.post("/api/auth/login", json={"username": "admin", "password": "nope"})
        self.assertEqual(r.status_code, 401)

    def test_endpoints_require_token(self):
        self.assertEqual(self.client.get("/api/records").status_code, 401)
        self.assertEqual(self.client.get("/api/dashboard/summary").status_code, 401)

    def test_change_password_flow(self):
        self._mk_facility("F")
        self._mk_user("worker", 1)
        tok = self._login("worker", "UserPass1!")
        h = {"Authorization": f"Bearer {tok}"}
        r = self.client.post("/api/auth/change-password", headers=h,
                             json={"old_password": "UserPass1!", "new_password": "BrandNew2!"})
        self.assertEqual(r.status_code, 200)
        self._login("worker", "BrandNew2!")

    def test_weak_password_rejected(self):
        r = self.client.post("/api/auth/login", json={"username": "admin", "password": ADMIN_PW})
        h = {"Authorization": f"Bearer {r.json()['token']}"}
        r2 = self.client.post("/api/users", headers=h, json={
            "username": "shorty", "password": "abc", "role": "viewer", "facility_id": 1})
        self.assertEqual(r2.status_code, 422)  # pydantic min_length


class MultiTenancy(Base):
    def setUp(self):
        super().setUp()
        self.fa = self._mk_facility("Factory A")
        self.fb = self._mk_facility("Factory B")
        self._mk_user("mgr_a", self.fa["facility_id"])
        self._mk_user("mgr_b", self.fb["facility_id"])
        self.ha = {"Authorization": f"Bearer {self._login('mgr_a', 'UserPass1!')}"}
        self.hb = {"Authorization": f"Bearer {self._login('mgr_b', 'UserPass1!')}"}

    def test_factory_user_cannot_see_other_facility_records(self):
        self._mk_record(self.admin, facility_id=self.fa["facility_id"])
        rows_b = self.client.get("/api/records", headers=self.hb).json()
        self.assertEqual(rows_b["total"], 0)
        # direct id access is blocked too
        self.assertEqual(self.client.get("/api/records/1", headers=self.hb).status_code, 403)

    def test_factory_user_cannot_act_on_foreign_facility(self):
        r = self.client.post("/api/submissions", headers=self.hb,
                             json={"facility_id": self.fa["facility_id"], "period_year": 2025})
        self.assertEqual(r.status_code, 403)
        r2 = self.client.get("/api/records", headers=self.hb,
                             params={"facility_id": self.fa["facility_id"]})
        self.assertEqual(r2.status_code, 403)

    def test_factory_user_records_auto_scoped(self):
        rec = self._mk_record(self.ha, name="Auto scope")
        self.assertEqual(rec["record"]["facility_id"], self.fa["facility_id"])
        self.assertEqual(rec["record"]["company_id"], self.fa["company_id"])

    def test_viewer_cannot_write(self):
        self._mk_user("looker", self.fa["facility_id"], role="viewer")
        hv = {"Authorization": f"Bearer {self._login('looker', 'UserPass1!')}"}
        r = self.client.post("/api/records", headers=hv, json={"activity_name": "x", "quantity": "1", "unit": "kg"})
        self.assertEqual(r.status_code, 403)

    def test_head_office_scoped_to_company(self):
        r = self.client.post("/api/users", headers=self.admin, json={
            "username": "hquser", "password": "UserPass1!", "role": "head_office"})
        self.assertEqual(r.status_code, 201)
        hh = {"Authorization": f"Bearer {self._login('hquser', 'UserPass1!')}"}
        self._mk_record(self.admin, facility_id=self.fa["facility_id"])
        # sees both facilities of the company, cannot create facilities for another company
        self.assertEqual(self.client.get("/api/records", headers=hh).json()["total"], 1)
        self.assertEqual(self.client.get("/api/dashboard/summary", headers=hh).json()["records"], 1)


class RecordsAndCalculation(Base):
    def setUp(self):
        super().setUp()
        self.fac = self._mk_facility("Calc Facility")

    def test_record_creation_with_manual_factor_matches_engine(self):
        rec = self._mk_record(self.admin, facility_id=self.fac["facility_id"], qty="1200", factor_value="2.68")
        row = rec["record"]
        self.assertEqual(row["calc_status"], "calculated")
        self.assertEqual(row["scope"], "Scope 1")
        self.assertEqual(float(row["kg_co2e"]), 1200 * 2.68)

    def test_duplicate_fingerprint_detected(self):
        facility = self._mk_facility("D Facility")
        self._mk_record(self.admin, facility_id=facility["facility_id"], name="Same", qty="100")
        r = self.client.post("/api/records", headers=self.admin, json={
            "activity_name": "Same", "quantity": "100", "unit": "litre", "activity_date": "2025-03-15",
            "category_key": "stationary_fuel", "country_code": "EG", "facility_id": facility["facility_id"],
            "manual_factor": {"value": "2.68", "source": "test source"}})
        self.assertEqual(r.status_code, 409)
        # allow_duplicate bypasses
        r2 = self.client.post("/api/records", headers=self.admin, json={
            "activity_name": "Same", "quantity": "100", "unit": "litre", "activity_date": "2025-03-15",
            "category_key": "stationary_fuel", "country_code": "EG", "facility_id": facility["facility_id"],
            "allow_duplicate": True,
            "manual_factor": {"value": "2.68", "source": "test source"}})
        self.assertEqual(r2.status_code, 201)

    def test_missing_source_for_manual_factor(self):
        r = self.client.post("/api/records", headers=self.admin, json={
            "activity_name": "X", "quantity": "1", "unit": "kg",
            "facility_id": self.fac["facility_id"],
            "manual_factor": {"value": "1", "source": ""}})
        self.assertEqual(r.status_code, 400)

    def test_scope_override_requires_reason(self):
        rec = self._mk_record(self.admin, facility_id=self.fac["facility_id"])
        rid = rec["record_id"]
        r = self.client.post(f"/api/records/{rid}/scope-override", headers=self.admin,
                             json={"scope": "Scope 3", "reason": ""})
        self.assertEqual(r.status_code, 400)
        r2 = self.client.post(f"/api/records/{rid}/scope-override", headers=self.admin,
                              json={"scope": "Scope 3", "reason": "third party haulage"})
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.json()["scope"], "Scope 3")
        self.assertEqual(r2.json()["scope_manual_override"], 1)

    def test_records_listing_filters_and_pagination(self):
        for m in range(1, 13):
            self._mk_record(self.admin, facility_id=self.fac["facility_id"], date=f"2025-{m:02d}-10", name=f"R{m}")
        r = self.client.get("/api/records", headers=self.admin, params={"year": 2025, "page_size": 5}).json()
        self.assertEqual(r["total"], 12)
        self.assertEqual(len(r["rows"]), 5)
        r2 = self.client.get("/api/records", headers=self.admin, params={"search": "R12"}).json()
        self.assertEqual(r2["total"], 1)


class SubmissionsWorkflow(Base):
    def setUp(self):
        super().setUp()
        self.fa = self._mk_facility("Factory A")
        self.fb = self._mk_facility("Factory B")
        self._mk_record(self.admin, facility_id=self.fa["facility_id"], qty="1200", factor_value="2.68")

    def test_full_submit_approve_consolidate(self):
        sub = self.client.post("/api/submissions", headers=self.admin,
                               json={"facility_id": self.fa["facility_id"], "period_year": 2025,
                                     "period_month": 3}).json()
        self.assertEqual(sub["total_kg_co2e"], "3216")
        # duplicate submission blocked
        dup = self.client.post("/api/submissions", headers=self.admin,
                               json={"facility_id": self.fa["facility_id"], "period_year": 2025, "period_month": 3})
        self.assertEqual(dup.status_code, 409)
        # approve
        r = self.client.post(f"/api/submissions/{sub['submission_id']}/review", headers=self.admin,
                             json={"decision": "approve", "note": "ok"})
        self.assertEqual(r.json()["status"], "approved")
        # consolidation sees only approved
        c = self.client.get("/api/submissions/consolidated", headers=self.admin).json()
        self.assertEqual(c["approved_submissions"], 1)
        self.assertEqual(c["total_kg_co2e"], "3216")
        self.assertEqual(c["facilities"][0]["facility_name"], "Factory A")

    def test_reject_then_resubmit(self):
        sub = self.client.post("/api/submissions", headers=self.admin,
                               json={"facility_id": self.fa["facility_id"], "period_year": 2025,
                                     "period_month": 3}).json()
        rej = self.client.post(f"/api/submissions/{sub['submission_id']}/review", headers=self.admin,
                               json={"decision": "reject"})
        self.assertEqual(rej.status_code, 409)  # rejection requires a note
        ok = self.client.post(f"/api/submissions/{sub['submission_id']}/review", headers=self.admin,
                              json={"decision": "reject", "note": "evidence missing"})
        self.assertEqual(ok.json()["status"], "rejected")
        again = self.client.post("/api/submissions", headers=self.admin,
                                 json={"facility_id": self.fa["facility_id"], "period_year": 2025, "period_month": 3})
        self.assertEqual(again.status_code, 201)
        # consolidated counts nothing (no approved)
        c = self.client.get("/api/submissions/consolidated", headers=self.admin).json()
        self.assertEqual(c["approved_submissions"], 0)

    def test_approved_submission_is_immutable_snapshot(self):
        sub = self.client.post("/api/submissions", headers=self.admin,
                               json={"facility_id": self.fa["facility_id"], "period_year": 2025,
                                     "period_month": 3}).json()
        sid = sub["submission_id"]
        self.client.post(f"/api/submissions/{sid}/review", headers=self.admin,
                         json={"decision": "approve", "note": "ok"})
        # more activity added afterwards does not change the approved snapshot
        self._mk_record(self.admin, facility_id=self.fa["facility_id"], name="Extra", qty="500")
        c = self.client.get("/api/submissions/consolidated", headers=self.admin).json()
        self.assertEqual(c["total_kg_co2e"], "3216")
        d = self.client.get(f"/api/submissions/{sid}", headers=self.admin).json()
        self.assertEqual(len(d["records"]), 1)

    def test_withdraw_and_resubmit_supersede(self):
        self.client.post("/api/submissions", headers=self.admin,
                         json={"facility_id": self.fa["facility_id"], "period_year": 2025, "period_month": 3})
        r = self.client.post("/api/submissions", headers=self.admin,
                             json={"facility_id": self.fa["facility_id"], "period_year": 2025,
                                   "period_month": 3, "allow_supersede": True})
        self.assertEqual(r.status_code, 201)


class ML(Base):
    def setUp(self):
        super().setUp()
        from services import ml_model as M
        # deterministic: point the registry at the temp dir (no model shipped, none trained here)
        self._orig_paths = (M.BUNDLE_PATH, M.META_PATH)
        M.BUNDLE_PATH = Path(self.tmp.name) / "emission_model.pkl"
        M.META_PATH = Path(self.tmp.name) / "emission_model_meta.json"

    def tearDown(self):
        from services import ml_model as M
        M.BUNDLE_PATH, M.META_PATH = self._orig_paths
        super().tearDown()

    def test_status_without_model_is_explicit(self):
        st = self.client.get("/api/ml/status", headers=self.admin).json()
        self.assertFalse(st["row_estimate_model"]["loaded"])
        self.assertIn("reason", st["row_estimate_model"])
        self.assertIn("forecast_models", st)

    def test_predict_without_model_404(self):
        r = self.client.post("/api/ml/predict", headers=self.admin,
                             json={"quantity": 100, "unit": "litre"})
        self.assertEqual(r.status_code, 404)

    def test_train_refuses_when_insufficient_data(self):
        f = self._mk_facility("ML F")
        for i in range(5):
            self._mk_record(self.admin, facility_id=f["facility_id"], name=f"m{i}")
        r = self.client.post("/api/ml/train", headers=self.admin, json={"min_rows": 40})
        self.assertEqual(r.status_code, 409)


class ReportsAndImports(Base):
    def test_csv_and_pdf(self):
        f = self._mk_facility("R F")
        self._mk_record(self.admin, facility_id=f["facility_id"])
        csv = self.client.get("/api/reports/csv", headers=self.admin, params={"year": 2025})
        self.assertEqual(csv.status_code, 200)
        self.assertIn("النشاط".encode("utf-8"), csv.content)
        pdf = self.client.get("/api/reports/pdf", headers=self.admin, params={"year": 2025, "lang": "en"})
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.content.startswith(b"%PDF"))

    def test_import_preview_and_commit(self):
        csv_content = ("activity,scope,quantity,unit,factor,source,date,country\n"
                       "Imported gen,Scope 1,150,kg,1.5,test source,2025-02-01,EG\n"
                       ",,bad,kg,1,x,2025-02-01,EG\n").encode("utf-8")
        f = self._mk_facility("I F")
        self._mk_user("importer", f["facility_id"])
        hi = {"Authorization": f"Bearer {self._login('importer', 'UserPass1!')}"}
        pv = self.client.post("/api/imports/preview", headers=hi,
                              files={"file": ("data.csv", csv_content, "text/csv")}).json()
        self.assertEqual(len(pv["accepted"]), 1)
        self.assertEqual(len(pv["rejected"]), 1)
        self.assertEqual(pv["accepted"][0]["facility"], "I F")  # tenancy override
        com = self.client.post("/api/imports/commit", headers=hi,
                               files={"file": ("data.csv", csv_content, "text/csv")}).json()
        self.assertEqual(com["added"], 1)
        rows = self.client.get("/api/records", headers=hi).json()
        self.assertEqual(rows["total"], 1)
        self.assertEqual(rows["rows"][0]["facility_id"], f["facility_id"])

    def test_factor_suggest_endpoint(self):
        # fresh installs seed the Egyptian dataset (EEHC 2023/2024, unverified by default)
        sg = self.client.get("/api/factors/suggest", headers=self.admin,
                             params={"country": "EG", "category": "electricity", "year": 2024,
                                     "unit": "kWh"}).json()
        self.assertIn("message", sg)
        self.assertTrue(sg["candidates"], "expected Egyptian electricity candidates for 2024")
        ids = [c["factor_id"] for c in sg["candidates"]]
        self.assertIn("EG-EEHC-THERMAL-INTENSITY-FY2023-24", ids)
        # seed factors are UNVERIFIED by design: nothing auto-chosen until a reviewer verifies
        chosen = sg["chosen"]
        if chosen is not None:
            self.assertTrue(chosen["factor"]["status"] == "verified")


class Settings(Base):
    def test_settings_roundtrip(self):
        r = self.client.put("/api/settings", headers=self.admin, json={"key": "display_unit", "value": "kg"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get("/api/settings", headers=self.admin).json()["display_unit"], "kg")
        bad = self.client.put("/api/settings", headers=self.admin, json={"key": "jwt_secret", "value": "x"})
        self.assertEqual(bad.status_code, 400)


if __name__ == "__main__":
    unittest.main()
