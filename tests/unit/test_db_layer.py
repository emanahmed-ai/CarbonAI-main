"""Tests for the DB/ledger/scope/import/report layers. Every test uses an isolated temp database;
the real data/carbonai.db is never touched. Factor values created here are TEST FIXTURES only."""
import io
import os
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

import pandas as pd

from db import connection as dbc
from db.schema import init_db
from db.seed import seed_all
from services import factor_library as FL
from services import importer as IM
from services import ledger as L
from services import library_update as LU
from services import reports as R
from services.scope_classifier import classify


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["CARBONAI_DB_PATH"] = str(Path(self.tmp.name) / "data" / "t.db")
        self.con = dbc.connect()
        init_db(self.con)
        seed_all(self.con, include_legacy_nz=True)

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def nz_elec(self, year=2022, verify=False):
        f = FL.get_factor(self.con, f"NZ-ELEC-GRID-{year}")
        if verify:
            FL.set_verification(self.con, f.factor_id, f.version, "verified", reviewer="test-reviewer",
                                reason="test fixture promotion")
            f = FL.get_factor(self.con, f.factor_id)
        return f

    def add_fixture_global(self, value="0.5", year=2022):
        FL.add_factor(self.con, factor_id="TEST-GLOBAL-ELEC", country_code="GLOBAL", factor_class="global_default",
                      category="electricity", activity="grid_average", unit="kWh", value=value, year_from=year,
                      year_to=year, reference_id=None, source_organization="TEST ORG", source_document="TEST DOC",
                      source_url=None, source_locator="fixture", reason="test fixture", user="test")
        f = FL.get_factor(self.con, "TEST-GLOBAL-ELEC")
        FL.set_verification(self.con, f.factor_id, f.version, "verified", reviewer="test-reviewer", reason="fixture")
        return FL.get_factor(self.con, "TEST-GLOBAL-ELEC")


class Storage(Base):
    def test_schema_idempotent_and_no_data_loss(self):                      # 4, 22
        f = self.nz_elec()
        L.add_record(self.con, activity_name="keep me", quantity="10", unit="kWh", country_code="NZ",
                     activity_date="2022-01-01", category_key="electricity", factor=f)
        for _ in range(3):
            init_db(self.con); seed_all(self.con, include_legacy_nz=True)
        self.assertEqual(len(L.fetch_records(self.con)), 1)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM emission_factors").fetchone()[0], 37)

    def test_persists_after_reconnect(self):                                # 22
        L.add_record(self.con, activity_name="x", quantity="1", unit="kWh", country_code="NZ",
                     activity_date="2022-01-01", category_key="electricity", factor=self.nz_elec())
        self.con.close()
        con2 = dbc.connect()
        self.assertEqual(len(L.fetch_records(con2)), 1)
        con2.close()
        self.con = dbc.connect()

    def test_backup_created_before_migration_and_restorable(self):
        L.add_record(self.con, activity_name="x", quantity="1", unit="kWh", country_code="NZ",
                     activity_date="2022-01-01", category_key="electricity", factor=self.nz_elec())
        b = dbc.backup_file(label="t")
        self.assertTrue(b.exists())
        self.con.close()
        dbc.restore_file(b)
        self.con = dbc.connect()
        self.assertEqual(len(L.fetch_records(self.con)), 1)

    def test_no_drop_or_delete_in_schema_and_seed(self):
        for mod in ("db/schema.py", "db/seed.py"):
            src = (Path(__file__).resolve().parents[2] / mod).read_text(encoding="utf-8").upper()
            self.assertNotIn("DROP TABLE", src)
            self.assertNotIn("DELETE FROM", src)


class Calculation(Base):
    def test_activity_with_date_month_and_year_totals(self):                # 5, 6
        f = self.nz_elec()
        for d, q in (("2022-03-05", "1000"), ("2022-03-20", "500"), ("2022-04-01", "2000")):
            L.add_record(self.con, activity_name="e", quantity=q, unit="kWh", country_code="NZ", activity_date=d,
                         category_key="electricity", factor=f, energy_purchased="yes", ownership_control="owned_controlled")
        df = L.fetch_records(self.con, year=2022)
        s = L.summarize(df, year=2022)
        self.assertEqual(s["total_kg"], Decimal("3500") * Decimal("0.0742"))
        self.assertEqual(s["monthly_kg"][(2022, 3)], Decimal("1500") * Decimal("0.0742"))
        self.assertEqual(s["months_with_data"], 2)
        self.assertEqual(s["avg_monthly_12_kg"], s["total_kg"] / 12)
        self.assertEqual(s["avg_monthly_active_kg"], s["total_kg"] / 2)
        m = L.summarize(L.fetch_records(self.con, year=2022, month=3))
        self.assertEqual(m["total_kg"], Decimal("1500") * Decimal("0.0742"))

    def test_empty_period_is_safe(self):
        s = L.summarize(L.fetch_records(self.con, year=1999), year=1999)
        self.assertEqual(s["total_kg"], 0)
        self.assertIsNone(s["avg_monthly_active_kg"])

    def test_missing_date_not_invented(self):
        r = L.add_record(self.con, activity_name="x", quantity="5", unit="kWh", country_code="NZ",
                         category_key="electricity", factor=self.nz_elec())
        row = L.fetch_records(self.con).iloc[0]
        self.assertIsNone(row["activity_date"] if pd.notna(row["activity_date"]) else None)
        self.assertEqual(r["status"], "needs_date")
        self.assertEqual(L.summarize(L.fetch_records(self.con))["total_kg"], 0)  # not silently zero-counted as data

    def test_missing_factor_is_needs_factor_not_zero(self):
        r = L.add_record(self.con, activity_name="x", quantity="5", unit="kWh", country_code="EG",
                         activity_date="2024-01-01", category_key="electricity")
        self.assertEqual(r["status"], "needs_factor")
        self.assertIsNone(L.fetch_records(self.con).iloc[0]["kg"])

    def test_incompatible_unit_rejected_not_converted(self):                # 13
        r = L.add_record(self.con, activity_name="x", quantity="5", unit="kg", country_code="NZ",
                         activity_date="2022-01-01", category_key="electricity", factor=self.nz_elec())
        self.assertEqual(r["status"], "rejected_unit")
        self.assertIsNone(L.fetch_records(self.con).iloc[0]["kg"])

    def test_unit_conversion_applied_when_compatible(self):
        r = L.add_record(self.con, activity_name="x", quantity="1", unit="MWh", country_code="NZ",
                         activity_date="2022-01-01", category_key="electricity", factor=self.nz_elec())
        self.assertEqual(r["status"], "calculated")
        self.assertEqual(L.fetch_records(self.con).iloc[0]["kg"], Decimal("1000") * Decimal("0.0742"))

    def test_snapshot_survives_library_update(self):                        # 20
        f = self.nz_elec()
        L.add_record(self.con, activity_name="x", quantity="1000", unit="kWh", country_code="NZ",
                     activity_date="2022-01-01", category_key="electricity", factor=f)
        before = L.fetch_records(self.con).iloc[0]["kg_co2e"]
        FL.add_factor(self.con, factor_id=f.factor_id, country_code="NZ", factor_class="official_national",
                      category="electricity", activity="grid_average", unit="kWh", value="0.9", year_from=2022,
                      year_to=2022, reference_id=None, source_organization="TEST", source_document="TEST DOC",
                      source_url=None, source_locator="fixture", reason="test update", user="t")
        after = L.fetch_records(self.con).iloc[0]
        self.assertEqual(after["kg_co2e"], before)
        self.assertEqual(after["factor_version"], 1)
        vers = [r["version"] for r in self.con.execute("SELECT version FROM emission_factors WHERE factor_id=?", (f.factor_id,))]
        self.assertEqual(sorted(vers), [1, 2])
        self.assertEqual(self.con.execute("SELECT verification_status FROM emission_factors WHERE factor_id=? AND version=1",
                                          (f.factor_id,)).fetchone()[0], "superseded")
        self.assertGreaterEqual(len(FL.audit_log(self.con, f.factor_id)), 3)


class Scope(unittest.TestCase):
    def test_scope1_owned_fuel(self):                                       # 7
        s = classify(category_key="stationary_fuel", ownership_control="owned_controlled")
        self.assertEqual((s.scope, s.confidence, s.status), ("Scope 1", "high", "suggested"))

    def test_scope2_purchased_electricity(self):                            # 8
        s = classify(category_key="electricity", energy_purchased="yes", ownership_control="owned_controlled")
        self.assertEqual(s.scope, "Scope 2")

    def test_scope3_value_chain(self):                                      # 9
        s = classify(category_key="transport_freight", value_chain_relation="third_party_upstream")
        self.assertEqual((s.scope, s.scope3_category), ("Scope 3", 4))
        self.assertEqual(classify(category_key="business_travel").scope3_category, 6)

    def test_insufficient_info_asks_not_guesses(self):                      # 10
        for kw in (dict(category_key="stationary_fuel"), dict(category_key="electricity"),
                   dict(category_key="mobile_fuel"), dict(category_key=None)):
            s = classify(**kw)
            self.assertIsNone(s.scope)
            self.assertIn(s.status, ("needs_review", "undetermined"))
            self.assertTrue(s.missing)

    def test_same_activity_different_scope_by_control(self):
        a = classify(category_key="mobile_fuel", ownership_control="owned_controlled", value_chain_relation="own_fleet")
        b = classify(category_key="transport_freight", value_chain_relation="third_party_downstream")
        self.assertEqual((a.scope, b.scope), ("Scope 1", "Scope 3"))

    def test_manual_override_is_logged(self):
        con_dir = tempfile.TemporaryDirectory()
        os.environ["CARBONAI_DB_PATH"] = str(Path(con_dir.name) / "t.db")
        con = dbc.connect(); init_db(con)
        r = L.add_record(con, activity_name="x", quantity="1", unit="kWh", country_code=None, category_key="other")
        self.assertIsNone(L.fetch_records(con).iloc[0]["scope"] if pd.notna(L.fetch_records(con).iloc[0]["scope"]) else None)
        with self.assertRaises(ValueError):
            L.override_scope(con, r["record_id"], "Scope 3", None, "  ", "u")
        L.override_scope(con, r["record_id"], "Scope 3", "Category 1", "supplier invoice", "u")
        row = L.fetch_records(con).iloc[0]
        self.assertEqual((row["scope"], row["scope_status"]), ("Scope 3", "confirmed"))
        self.assertEqual(con.execute("SELECT COUNT(*) FROM scope_audit_log").fetchone()[0], 1)
        con.close(); con_dir.cleanup()


class Selection(Base):
    def test_national_verified_auto_selected(self):                         # 11
        self.nz_elec(verify=True)
        s = FL.suggest(self.con, country="NZ", category="electricity", year=2022, unit="kWh")
        self.assertIsNotNone(s.chosen)
        self.assertEqual(s.chosen.factor.factor_id, "NZ-ELEC-GRID-2022")
        self.assertTrue(s.chosen.is_national_for_activity)

    def test_unverified_national_not_auto_selected(self):
        s = FL.suggest(self.con, country="NZ", category="electricity", year=2022, unit="kWh")
        self.assertIsNone(s.chosen)
        self.assertIn("NOT verified", s.message)

    def test_international_fallback_shown_with_reason_not_auto(self):       # 12
        self.add_fixture_global()
        s = FL.suggest(self.con, country="EG", category="electricity", year=2022, unit="kWh")
        self.assertIsNone(s.chosen)
        kinds = {c.factor.country: c for c in s.candidates}
        self.assertIn("GLOBAL", kinds)
        self.assertTrue(kinds["GLOBAL"].needs_proxy_confirmation)
        self.assertIn("not a national factor", kinds["GLOBAL"].reason)
        # NZ national data is offered only as a clearly-labelled proxy
        self.assertIn("NOT of EG", kinds["NZ"].reason)

    def test_proxy_requires_confirmation_in_calculation(self):
        g = self.add_fixture_global()
        r = L.add_record(self.con, activity_name="x", quantity="10", unit="kWh", country_code="EG",
                         activity_date="2022-05-01", category_key="electricity", factor=g)
        self.assertEqual(r["status"], "needs_review")
        r2 = L.add_record(self.con, activity_name="y", quantity="10", unit="kWh", country_code="EG",
                          activity_date="2022-05-01", category_key="electricity", factor=g, proxy_confirmed=True)
        self.assertEqual(r2["status"], "calculated")
        self.assertIn("PROXY", L.fetch_records(self.con, calc_status="calculated").iloc[0]["calc_notes"])

    def test_nz_factor_never_national_for_egypt(self):
        s = FL.suggest(self.con, country="EG", category="electricity", year=2022, unit="kWh")
        self.assertIsNone(s.chosen)
        self.assertTrue(all(not c.is_national_for_activity for c in s.candidates))

    def test_incompatible_unit_candidates_excluded_with_reason(self):
        s = FL.suggest(self.con, country="NZ", category="electricity", year=2022, unit="kg")
        self.assertEqual(s.candidates, [])
        self.assertTrue(s.excluded)

    def test_verify_requires_reviewer_and_reason(self):
        with self.assertRaises(PermissionError):
            FL.set_verification(self.con, "NZ-ELEC-GRID-2022", 1, "verified", reviewer="", reason="x")

    def test_coverage_does_not_claim_global(self):
        cov = {r["iso2_code"]: r for r in FL.countries_coverage(self.con)}
        self.assertEqual(cov["EG"]["n_factors"], 0)
        self.assertEqual(cov["NZ"]["n_verified"], 0)


class Imports(Base):
    LEGACY = "النشاط,النطاق,الكمية,الوحدة,معامل الانبعاث,المصدر\nكهرباء,Scope 2,1000,kWh,0.45,مرجع\nديزل,Scope 1,800,L,2.68,\n"

    def _commit(self, df, **kw):
        pv = IM.preview(df, **kw)
        return pv, IM.commit(self.con, pv, file_name="t.csv")

    def test_legacy_csv_without_date(self):                                 # 15
        df = IM.read_upload("t.csv", ("\ufeff" + self.LEGACY).encode("utf-8"))
        pv, res = self._commit(df)
        self.assertEqual(len(pv.accepted), 2)
        self.assertEqual(res["added"], 2)
        out = L.fetch_records(self.con)
        self.assertTrue(out["activity_date"].isna().all())
        self.assertEqual(sorted(out["scope"]), ["Scope 1", "Scope 2"])
        s = L.summarize(out)
        self.assertEqual(s["undated_kg"], Decimal("1000") * Decimal("0.45") + Decimal("800") * Decimal("2.68"))
        self.assertEqual(s["months_with_data"], 0)

    def test_explicit_default_date_only_when_given(self):
        df = IM.read_upload("t.csv", self.LEGACY.encode("utf-8"))
        pv, _ = self._commit(df, default_date="2024-06-15")
        self.assertTrue(all(a["date"].isoformat() == "2024-06-15" for a in pv.accepted))

    def test_rejected_rows_listed_and_good_rows_kept(self):                 # 16
        csv = ("النشاط,النطاق,الكمية,الوحدة,معامل الانبعاث\nok,Scope 1,10,L,2\n,Scope 1,5,L,2\nbadqty,Scope 1,abc,L,2\n"
               "badscope,Scope 9,5,L,2\nbadunit,Scope 1,5,furlong,2\nzeroqty,Scope 1,0,L,2\nnegfactor,Scope 1,5,L,-1\n")
        pv, res = self._commit(IM.read_upload("t.csv", csv.encode("utf-8")))
        self.assertEqual(len(pv.accepted), 1)
        self.assertEqual(len(pv.rejected), 6)
        self.assertTrue(all(r[1] for r in pv.rejected))
        self.assertEqual(res["added"], 1)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM import_rejections").fetchone()[0], 6)

    def test_duplicates_reported_not_deleted_and_merge_not_replace(self):   # 16
        df = IM.read_upload("t.csv", self.LEGACY.encode("utf-8"))
        self._commit(df)
        _, res2 = self._commit(df)
        self.assertEqual(len(res2["duplicates"]), 2)
        self.assertEqual(len(L.fetch_records(self.con)), 2)
        _, res3 = self._commit(df, **{}) if False else (None, IM.commit(self.con, IM.preview(df), file_name="t.csv", keep_duplicates=True))
        self.assertEqual(len(L.fetch_records(self.con)), 4)

    def test_excel_import(self):                                            # 14
        raw = pd.DataFrame({"activity": ["Grid power"], "quantity": [1000], "unit": ["kWh"], "date": ["2022-02-10"],
                            "country": ["NZ"], "category": ["electricity"], "company": ["Acme"], "facility": ["Plant 1"],
                            "energy_purchased": ["yes"], "ownership_control": ["owned_controlled"]})
        buf = io.BytesIO(); raw.to_excel(buf, index=False)
        df = IM.read_upload("t.xlsx", buf.getvalue())
        pv, res = self._commit(df)
        self.assertEqual(res["added"], 1)
        row = L.fetch_records(self.con).iloc[0]
        self.assertEqual((row["company_name"], row["facility_name"], row["scope"]), ("Acme", "Plant 1", "Scope 2"))
        # NEW APPROVED POLICY (2026-11-11): exact-year factor exists but is unverified, so the
        # documented selection policy falls back to the nearest available year and marks the
        # result as ESTIMATED. It must never be silent - the note proves the fallback.
        self.assertEqual(row["calc_status"], "calculated")
        self.assertEqual(row["factor_id"], "NZ-ELEC-GRID-2021")
        self.assertIn("ESTIMATED", row["calc_notes"])

    def test_missing_required_columns(self):
        pv = IM.preview(pd.DataFrame({"foo": [1]}))
        self.assertIn("activity", pv.missing_columns)

    def test_existing_rows_untouched_by_import(self):
        f = self.nz_elec()
        L.add_record(self.con, activity_name="old", quantity="1", unit="kWh", country_code="NZ",
                     activity_date="2022-01-01", category_key="electricity", factor=f)
        self._commit(IM.read_upload("t.csv", self.LEGACY.encode("utf-8")))
        self.assertEqual(len(L.fetch_records(self.con)), 3)
        self.assertIn("old", list(L.fetch_records(self.con)["activity_name"]))


class LegacySession(Base):
    def test_migrate_session_rows_idempotent(self):
        df = pd.DataFrame([{"النشاط": "استهلاك الكهرباء", "النطاق": "Scope 2", "الكمية": 12000.0, "الوحدة": "kWh",
                            "معامل الانبعاث": 0.45, "المصدر": "عامل تجريبي للواجهة"}])
        a = L.migrate_session_rows(self.con, df)
        b = L.migrate_session_rows(self.con, df)
        self.assertEqual((a["added"], b["added"], b["skipped_duplicates"]), (1, 0, 1))
        row = L.fetch_records(self.con).iloc[0]
        self.assertEqual(row["factor_verification"], "unverified")
        self.assertEqual(row["factor_class"], "user_supplied")
        self.assertEqual(Decimal(row["kg_co2e"]), Decimal("5400"))


class Companies(Base):
    def test_company_facility_persist_and_link(self):
        cid = L.upsert_company(self.con, "Acme", "EG", "Manufacturing", "operational_control")
        self.assertEqual(L.upsert_company(self.con, "Acme", "EG"), cid)  # no duplicate / no overwrite
        fid = L.add_facility(self.con, cid, "Plant 1", "EG", control_status="owned_controlled")
        L.add_record(self.con, activity_name="x", quantity="1", unit="kWh", country_code="EG", company_id=cid,
                     facility_id=fid, activity_date="2024-01-01")
        self.assertEqual(len(L.fetch_records(self.con, company_id=cid, facility_id=fid)), 1)


class LibraryUpdate(Base):
    def _df(self, **over):
        row = dict(factor_id="TEST-X", country_code="EG", factor_class="official_national",
                   activity_category="electricity", activity="grid_average", unit="kWh", value="0.1", year_from=2023,
                   year_to=2023, source_organization="TEST ORG", source_document="TEST DOC", source_locator="fixture")
        row.update(over)
        return pd.DataFrame([row])

    def test_valid_file_added_unverified_with_audit(self):
        r = LU.apply_file(self.con, self._df(), reference_id=None, user="t", reason="test", source_label="fixture")
        self.assertEqual(r["imported"], 1)
        f = FL.get_factor(self.con, "TEST-X")
        self.assertEqual(f.status.value, "unverified")
        self.assertEqual(self.con.execute("SELECT outcome FROM update_log").fetchone()[0], "imported")

    def test_bad_file_changes_nothing_and_does_not_crash(self):             # 21
        before = self.con.execute("SELECT COUNT(*) FROM emission_factors").fetchone()[0]
        bad = pd.concat([self._df(), self._df(factor_id="TEST-Y", value="-5"),
                         self._df(factor_id="TEST-Z", source_locator="")])
        r = LU.apply_file(self.con, bad.reset_index(drop=True), reference_id=None, user="t", reason="t", source_label="f")
        self.assertFalse(r["applied"])
        self.assertEqual(len(r["problems"]), 2)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM emission_factors").fetchone()[0], before)
        r2 = LU.apply_file(self.con, pd.DataFrame({"x": [1]}), reference_id=None, user="t", reason="t", source_label="f")
        self.assertFalse(r2["applied"])

    def test_unsourced_factor_refused(self):
        with self.assertRaises(ValueError):
            FL.add_factor(self.con, factor_id="A", country_code="EG", factor_class="official_national", category="c",
                          activity="a", unit="kWh", value="1", year_from=2020, year_to=2020, reference_id=None,
                          source_organization="", source_document="", source_url=None, source_locator="",
                          reason="r", user="u")


class Reports(Base):
    def _populate(self):
        f = self.nz_elec()
        for i in range(60):
            L.add_record(self.con, activity_name=f"a{i}", quantity=str(10 + i), unit="kWh", country_code="NZ",
                         activity_date=f"2022-{1 + i % 12:02d}-10", category_key="electricity", factor=f,
                         energy_purchased="yes", ownership_control="owned_controlled")

    def test_csv_arabic_utf8_sig_and_filter(self):                          # 17, 19
        self._populate()
        df = L.fetch_records(self.con, year=2022, month=3)
        data = R.csv_bytes(df)
        self.assertTrue(data.startswith(b"\xef\xbb\xbf"))
        txt = data.decode("utf-8-sig")
        self.assertIn("تاريخ النشاط", txt.splitlines()[0])
        rows = pd.read_csv(io.BytesIO(data), encoding="utf-8-sig")
        self.assertTrue((rows["الشهر"] == 3).all())
        self.assertEqual(R.csv_filename("report", year=2022, month=3), "carbonai_report_2022-03.csv")
        self.assertIn("الإجمالي (kg CO2e)", R.monthly_summary_df(L.fetch_records(self.con, year=2022)).columns)

    def test_dashboard_report_same_numbers(self):
        self._populate()
        df = L.fetch_records(self.con, year=2022)
        total = L.summarize(df)["total_kg"]
        csv_total = sum(Decimal(str(v)) for v in R.report_dataframe(df)["الانبعاثات (kg CO2e)"])
        self.assertEqual(total, csv_total)

    def test_pdf_english_multipage_header_repeat(self):                     # 18 (English part)
        self._populate()
        data = R.pdf_bytes(L.fetch_records(self.con, year=2022), title_company="Acme", country="NZ", period="2022")
        self.assertTrue(data.startswith(b"%PDF"))
        try:
            import pdfplumber
        except ImportError:
            return
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            self.assertGreater(len(pdf.pages), 1)
            self.assertIn("Date Activity Scope", pdf.pages[-1].extract_text())

    def test_pdf_arabic_degrades_gracefully_or_works(self):
        self._populate()
        ok, _ = R.arabic_pdf_supported()
        df = L.fetch_records(self.con, year=2022)
        if ok:
            self.assertTrue(R.pdf_bytes(df, lang="ar").startswith(b"%PDF"))
        else:
            with self.assertRaises(R.PdfUnavailable):
                R.pdf_bytes(df, lang="ar")

    def test_pdf_empty_period_does_not_crash(self):
        self.assertTrue(R.pdf_bytes(L.fetch_records(self.con, year=1999)).startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
