"""v4 tests: NZ removal execution, Egypt selection/fallback, refrigerant module (single gas,
blends, recovery, explicit leakage), scope separation, reference library, isolation, PDFs."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from api.main import app
from db.connection import connect
from db.schema import init_db
from db.seed import seed_all

ADMIN_PW = "AdminPass1!"
ROOT = Path(__file__).resolve().parents[2]


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

    def _equipment(self, headers=None, facility_id=None, key="R410A", ident="CH-01") -> dict:
        r = self.client.post("/api/cooling/equipment", headers=headers or self.admin, json={
            "facility_id": facility_id or self.fac["facility_id"], "identifier": ident,
            "equipment_type": "chiller", "refrigerant_key": key, "charge_kg": "120"})
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()


class NZRemoval(unittest.TestCase):
    def test_removal_cli_executes_and_preserves_history(self):
        with tempfile.TemporaryDirectory() as td:
            db = str(Path(td) / "legacy.db")
            os.environ["CARBONAI_DB_PATH"] = db
            con = connect()
            init_db(con)
            seed_all(con, include_legacy_nz=True)
            con.commit()
            nz = con.execute("SELECT COUNT(*) c FROM emission_factors WHERE country_code='NZ'").fetchone()["c"]
            self.assertEqual(nz, 37)
            # a historical record that must survive removal
            from services import ledger as L
            f = L.user_factor("2.68", country="NZ", category="stationary_fuel", activity="diesel",
                              unit="litre", year=2023, source="historical fixture")
            L.add_record(con, activity_name="historical diesel", quantity="100", unit="litre",
                         country_code="NZ", activity_date="2023-05-01",
                         category_key="stationary_fuel", factor=f)
            before = con.execute("SELECT COUNT(*) c, SUM(CAST(kg_co2e AS REAL)) s FROM activity_records").fetchone()
            con.close()

            env = {**os.environ, "CARBONAI_DB_PATH": db}
            res = subprocess.run([sys.executable, "scripts/nz_removal_dry_run.py",
                                  "--execute", "--confirm", "REMOVE-LEGACY-NZ"],
                                 cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=120)
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

            con = connect()
            nz_after = con.execute("SELECT COUNT(*) c FROM emission_factors WHERE country_code='NZ'").fetchone()["c"]
            src_after = con.execute("SELECT COUNT(*) c FROM sources WHERE reference_id='NZ-MFE-2023-ME1764'").fetchone()["c"]
            after = con.execute("SELECT COUNT(*) c, SUM(CAST(kg_co2e AS REAL)) s FROM activity_records").fetchone()
            log = con.execute("SELECT outcome FROM update_log WHERE source='nz_removal'").fetchone()
            snap = con.execute("SELECT factor_snapshot_json, kg_co2e FROM activity_records "
                               "WHERE activity_name='historical diesel'").fetchone()
            con.close()
            self.assertEqual(nz_after, 0)
            self.assertEqual(src_after, 0)
            self.assertEqual(before["c"], after["c"], "historical records must not be touched")
            self.assertEqual(before["s"], after["s"])
            self.assertIsNotNone(log)
            self.assertIn('"country": "NZ"', snap["factor_snapshot_json"] or "")
            self.assertEqual(float(snap["kg_co2e"]), 268.0)


class EgyptSelection(Base):
    def test_default_country_is_egypt_and_no_nz_selectable(self):
        self.assertEqual(self.client.get("/api/settings", headers=self.admin).json()["default_country"], "EG")
        rows = self.client.get("/api/factors", headers=self.admin, params={"country": "NZ"}).json()
        self.assertEqual(rows, [])

    def test_egypt_official_factor_selection(self):
        r = self.client.post("/api/records", headers=self.admin, json={
            "activity_name": "EEHC thermal intensity", "quantity": "100000", "unit": "kWh",
            "activity_date": "2024-06-01", "category_key": "electricity", "country_code": "EG",
            "facility_id": self.fac["facility_id"],
            "ownership_control": "owned_controlled", "energy_purchased": "no",
            "factor": {"factor_id": "EG-EEHC-THERMAL-INTENSITY-FY2023-24"}})
        self.assertEqual(r.status_code, 201, r.text)
        rec = r.json()["record"]
        self.assertEqual(rec["calc_status"], "calculated")
        self.assertEqual(float(rec["kg_co2e"]), 100000 * 0.3803)
        self.assertIn("EEHC", rec["factor_source"])
        self.assertEqual(rec["factor_verification"], "unverified")

    def test_international_fallback_requires_explicit_proxy(self):
        body = {"activity_name": "R410 leakage fallback", "quantity": "1", "unit": "kg",
                "activity_date": "2024-06-01", "category_key": "refrigerant", "country_code": "EG",
                "facility_id": self.fac["facility_id"],
                "factor": {"factor_id": "REF-R410A-AR5"}}
        r1 = self.client.post("/api/records", headers=self.admin, json=body)
        self.assertEqual(r1.status_code, 400)
        body["factor"] = {"factor_id": "REF-R410A-AR5", "proxy_confirmed": True,
                          "proxy_rationale": "IPCC GWP default; no Egyptian GWP table"}
        r2 = self.client.post("/api/records", headers=self.admin, json=body)
        self.assertEqual(r2.status_code, 201, r2.text)
        self.assertTrue(r2.json()["record"]["calc_status"] == "calculated")

    def test_source_traceability_everywhere(self):
        rows = self.client.get("/api/factors/egypt", headers=self.admin).json()
        for r in rows:
            self.assertTrue(r["source_organization"], r["factor_id"])
            self.assertTrue(r["source_document"], r["factor_id"])
            self.assertTrue(r["source_locator"] or r["source_page"], r["factor_id"])


class RefrigerantFactorsRemain(Base):
    """The management page/API was removed; the refrigerant FACTORS must remain available."""

    def test_refrigerant_factors_available_in_emission_factors(self):
        rows = self.client.get("/api/factors", headers=self.admin,
                               params={"category": "refrigerant"}).json()
        self.assertGreaterEqual(len(rows), 40)
        r410 = [r for r in rows if r["factor_id"] == "REF-R410A-AR5"]
        self.assertEqual(len(r410), 1)
        self.assertEqual(r410[0]["co2e_factor_value"], "1924")
        self.assertEqual(r410[0]["country_scope"], "international_default")
        self.assertTrue(r410[0]["source_organization"])
        self.assertTrue(r410[0]["source_document"])

    def test_management_api_removed(self):
        self.assertEqual(self.client.get("/api/refrigerants", headers=self.admin).status_code, 404)
        self.assertEqual(self.client.get("/api/cooling/equipment", headers=self.admin).status_code, 404)

    def test_refrigerant_calculation_via_core(self):
        r = self.client.post("/api/records", headers=self.admin, json={
            "activity_name": "R-410A leakage", "quantity": "5", "unit": "kg",
            "activity_date": "2026-02-01", "category_key": "refrigerant", "country_code": "EG",
            "facility_id": self.fac["facility_id"], "ownership_control": "owned_controlled",
            "factor": {"factor_id": "REF-R410A-AR5", "proxy_confirmed": True,
                       "proxy_rationale": "IPCC GWP default (no Egyptian GWP table)"}})
        self.assertEqual(r.status_code, 201, r.text)
        rec = r.json()["record"]
        self.assertEqual(rec["scope"], "Scope 1")
        self.assertEqual(float(rec["kg_co2e"]), 5 * 1924)

    def test_scope_separation(self):
        self.client.post("/api/records", headers=self.admin, json={
            "activity_name": "R-32 leakage", "quantity": "2", "unit": "kg",
            "activity_date": "2026-02-01", "category_key": "refrigerant", "country_code": "EG",
            "facility_id": self.fac["facility_id"], "ownership_control": "owned_controlled",
            "factor": {"factor_id": "REF-R32-AR5", "proxy_confirmed": True, "proxy_rationale": "IPCC"}})
        r2 = self.client.post("/api/records", headers=self.admin, json={
            "activity_name": "electricity", "quantity": "1000", "unit": "kWh",
            "activity_date": "2026-02-01", "category_key": "electricity", "country_code": "EG",
            "facility_id": self.fac["facility_id"], "ownership_control": "owned_controlled",
            "energy_purchased": "yes", "manual_factor": {"value": "0.3803", "source": "EEHC test"}})
        self.assertEqual(r2.status_code, 201, r2.text)
        rows = self.client.get("/api/records", headers=self.admin,
                               params={"category_key": "refrigerant"}).json()["rows"]
        self.assertEqual({r["scope"] for r in rows}, {"Scope 1"})
        s = self.client.get("/api/dashboard/summary", headers=self.admin).json()
        self.assertEqual(float(s["by_scope_kg"]["Scope 1"]), 2 * 677)
        self.assertEqual(float(s["by_scope_kg"]["Scope 2"]), 1000 * 0.3803)

    def test_unsupported_basis_and_missing_quantities(self):
        # no cooling API: quantity validation happens through the core (negative rejected)
        r = self.client.post("/api/records", headers=self.admin, json={
            "activity_name": "negative", "quantity": "-1", "unit": "kg",
            "activity_date": "2026-02-01", "category_key": "refrigerant", "country_code": "EG",
            "facility_id": self.fac["facility_id"], "factor": {"factor_id": "REF-R410A-AR5",
                                                              "proxy_confirmed": True, "proxy_rationale": "x"}})
        self.assertEqual(r.status_code, 400)


class ReferenceLibrary(Base):
    def test_catalogue_complete_and_honest(self):
        rows = self.client.get("/api/references", headers=self.admin).json()
        self.assertGreaterEqual(len(rows), 30)
        self.assertGreaterEqual(sum(1 for r in rows if r["country_applicability"] == "EG"), 10)
        for r in rows:
            self.assertTrue(r["title"])
            self.assertTrue(r["organization"])
            self.assertIn(r["kind"], ("standard", "methodology", "factor_database", "gwp",
                                      "national_inventory"))
            if r["url"]:
                self.assertTrue(r["url"].startswith("https://"), r["ref_key"])
        keys = [r["ref_key"] for r in rows]
        self.assertEqual(len(keys), len(set(keys)))
        # ISO entries exist but are flagged as standards, not factor databases
        iso = [r for r in rows if r["ref_key"].startswith("ISO-")]
        self.assertGreaterEqual(len(iso), 4)
        self.assertTrue(all(r["kind"] == "standard" for r in iso))

    def test_groups_endpoint(self):
        g = self.client.get("/api/references/groups", headers=self.admin).json()
        self.assertIn("standard", g["groups"])
        self.assertGreater(g["counts"]["gwp"], 0)

    def test_reports_include_refrigerant(self):
        r = self.client.post("/api/records", headers=self.admin, json={
            "activity_name": "R-134a leakage", "quantity": "3", "unit": "kg",
            "activity_date": "2026-01-15", "category_key": "refrigerant", "country_code": "EG",
            "facility_id": self.fac["facility_id"], "ownership_control": "owned_controlled",
            "factor": {"factor_id": "REF-R134A-AR5", "proxy_confirmed": True, "proxy_rationale": "IPCC"}})
        self.assertEqual(r.status_code, 201, r.text)
        pdf = self.client.get("/api/reports/annual", headers=self.admin, params={"year": 2026})
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.content.startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
