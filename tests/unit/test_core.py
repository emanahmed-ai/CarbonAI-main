import unittest
from decimal import Decimal as Dc

from schemas.domain import (ActivityInput, D, EmissionFactor, FactorClass,
                            GasComponent, ValueBasis, VerificationStatus as VS)
from services import calculations as calc
from services import unit_conversion as uc
from services.emission_factors import MissingFactorError, select_factor, select_proxy
from services.gwp import AR4_100, AR5_100, get_gwp_set
from services.reference_loader import load_nz_mfe_2023


def synth(**kw):
    """SYNTHETIC test factor. Not real data."""
    base = dict(factor_id="TEST-1", version=1, country="XX", category="electricity",
                activity="grid", numerator_unit="kg CO2e", denominator_unit="kWh",
                total_co2e=D("0.5"), components=(), year_from=2024, year_to=2024,
                classification=FactorClass.TEST_SYNTHETIC, status=VS.VERIFIED,
                source_org="TEST", source_title="synthetic", source_url=None,
                source_locator="n/a", gwp_set_id=None)
    base.update(kw)
    return EmissionFactor(**base)


def act(q, unit="kWh", country="XX", year=2024, cat="electricity", a="grid"):
    return ActivityInput(D(q), unit, country, year, cat, a)


class Units(unittest.TestCase):
    def test_kg_tonnes(self): self.assertEqual(calc.kg_to_tonnes(1500), Dc("1.5"))
    def test_mwh_to_kwh(self): self.assertEqual(uc.convert(2, "MWh", "kWh"), 2000)
    def test_gj_to_kwh(self): self.assertAlmostEqual(float(uc.convert(1, "GJ", "kWh")), 277.7778, 3)
    def test_mass_volume_blocked(self):
        with self.assertRaises(uc.IncompatibleUnitsError): uc.convert(1, "kg", "litre")
    def test_pkm_vs_tkm_blocked(self):
        with self.assertRaises(uc.IncompatibleUnitsError): uc.convert(1, "pkm", "tkm")
    def test_pkm_vs_km_blocked(self):
        with self.assertRaises(uc.IncompatibleUnitsError): uc.convert(1, "pkm", "km")
    def test_unknown_unit(self):
        with self.assertRaises(uc.UnitError): uc.convert(1, "furlong", "km")
    def test_density_explicit(self):
        self.assertEqual(uc.convert_with_property(10, "litre", "kg", property_value="0.536",
                         property_unit="kg/litre"), Dc("5.36"))
    def test_wrong_property(self):
        with self.assertRaises(uc.IncompatibleUnitsError):
            uc.convert_with_property(1, "kg", "kwh", property_value=1, property_unit="kg/litre")
    def test_currency_needs_source(self):
        with self.assertRaises(uc.UnitError): uc.convert_currency(10, 2, rate_source="", rate_date="")
    def test_float_rejected(self):
        with self.assertRaises(TypeError): D(0.1)


class Gwp(unittest.TestCase):
    def test_ar5_combustion(self):
        # 100 CO2 + 1 CH4*28 + 1 N2O*265 = 393
        self.assertEqual(calc.combustion_co2e(100, 1, 1, AR5_100), Dc(393))
    def test_ar4_differs(self):
        self.assertEqual(calc.combustion_co2e(100, 1, 1, AR4_100), Dc(423))
    def test_missing_gas_not_assumed(self):
        with self.assertRaises(KeyError): AR5_100.gwp("HFC-134a")
    def test_unknown_set(self):
        with self.assertRaises(KeyError): get_gwp_set("AR9")
    def test_refrigerant_needs_source(self):
        with self.assertRaises(calc.CalculationError):
            calc.refrigerant_leakage(1, 100, refrigerant="X", gwp_source="")
        self.assertEqual(calc.refrigerant_leakage(2, 100, refrigerant="TEST", gwp_source="synthetic"), 200)


class Engine(unittest.TestCase):
    def test_basic(self):
        r = calc.calculate(act(1000), synth(), allow_test_factor=True)
        self.assertEqual(r.kg_co2e, Dc(500)); self.assertEqual(r.t_co2e, Dc("0.5"))
        self.assertIn("SYNTHETIC", " ".join(r.warnings))
    def test_unit_conversion_step(self):
        r = calc.calculate(act("1", "MWh"), synth(), allow_test_factor=True)
        self.assertEqual(r.kg_co2e, Dc(500)); self.assertTrue(r.steps)
    def test_incompatible_unit(self):
        with self.assertRaises(calc.CalculationError):
            calc.calculate(act(1, "litre"), synth(), allow_test_factor=True)
    def test_synthetic_blocked_by_default(self):
        with self.assertRaises(calc.CalculationError): calc.calculate(act(1), synth())
    def test_negative_blocked(self):
        with self.assertRaises(calc.CalculationError):
            calc.calculate(act(-1), synth(), allow_test_factor=True)
    def test_year_outside_validity(self):
        with self.assertRaises(calc.CalculationError):
            calc.calculate(act(1, year=2030), synth(), allow_test_factor=True)
    def test_activity_mismatch(self):
        with self.assertRaises(calc.CalculationError):
            calc.calculate(act(1, a="other"), synth(), allow_test_factor=True)
    def test_rejected_and_superseded(self):
        with self.assertRaises(calc.CalculationError):
            calc.calculate(act(1), synth(status=VS.REJECTED), allow_test_factor=True)
        with self.assertRaises(calc.CalculationError):
            calc.calculate(act(1), synth(status=VS.SUPERSEDED), allow_test_factor=True)
    def test_proxy_requires_confirmation(self):
        f = synth(country="YY", classification=FactorClass.PROXY)
        with self.assertRaises(calc.ProxyNotConfirmedError): calc.calculate(act(1), f)
        r = calc.calculate(act(1), f, proxy_confirmed=True)
        self.assertTrue(r.is_estimate); self.assertIn("PROXY", r.warnings[0])
    def test_mass_component_needs_gwp(self):
        comps = (GasComponent("CO2", D(2), ValueBasis.MASS), GasComponent("CH4", D("0.01"), ValueBasis.MASS))
        f = synth(components=comps, total_co2e=None, classification=FactorClass.USER_SUPPLIED,
                  country="XX")
        with self.assertRaises(calc.CalculationError): calc.calculate(act(10), f)
        r = calc.calculate(act(10), f, gwp_set=AR5_100)
        self.assertEqual(r.kg_co2e, Dc(20) + Dc("0.1") * 28)
        self.assertEqual(r.gwp_set_id, "AR5-GWP100")
    def test_gwp_mixing_blocked(self):
        comps = (GasComponent("CH4", D("0.01"), ValueBasis.MASS),)
        f = synth(components=comps, total_co2e=None, gwp_set_id="AR4-GWP100",
                  classification=FactorClass.USER_SUPPLIED)
        with self.assertRaises(calc.CalculationError): calc.calculate(act(1), f, gwp_set=AR5_100)
    def test_historical_reproducible_after_supersede(self):
        f1 = synth(classification=FactorClass.USER_SUPPLIED)
        r1 = calc.calculate(act(100), f1)
        f1_sup = synth(classification=FactorClass.USER_SUPPLIED, status=VS.SUPERSEDED)
        f2 = synth(classification=FactorClass.USER_SUPPLIED, version=2, total_co2e=D("0.6"))
        self.assertEqual(calc.calculate(act(100), f2).kg_co2e, Dc(60))
        r_repro = calc.calculate(act(100), f1_sup, allow_superseded=True)
        self.assertEqual(r_repro.kg_co2e, r1.kg_co2e)
        self.assertEqual(r1.factor_snapshot["version"], 1)


class Selection(unittest.TestCase):
    def setUp(self):
        self.nz = load_nz_mfe_2023()
    def test_missing_country_no_invention(self):
        with self.assertRaises(MissingFactorError) as cm:
            select_factor(self.nz, country="EG", category="electricity", activity="grid_average",
                          year=2022, allow_unverified=True)
        self.assertTrue(cm.exception.proxy_candidates)  # NZ offered ONLY as candidate
    def test_unverified_excluded_by_default(self):
        with self.assertRaises(MissingFactorError):
            select_factor(self.nz, country="NZ", category="electricity", activity="grid_average", year=2022)
    def test_reviewer_promotes(self):
        nz = load_nz_mfe_2023(reviewer="reviewer@example.org")
        s = select_factor(nz, country="NZ", category="electricity", activity="grid_average", year=2022)
        self.assertFalse(s.is_proxy)
    def test_proxy_needs_rationale(self):
        with self.assertRaises(PermissionError):
            select_proxy(self.nz[0], confirmed_by="", rationale="")
    def test_highest_version_wins_and_alt_listed(self):
        a = synth(classification=FactorClass.USER_SUPPLIED)
        b = synth(classification=FactorClass.USER_SUPPLIED, version=2, total_co2e=D("0.6"))
        s = select_factor([a, b], country="XX", category="electricity", activity="grid", year=2024)
        self.assertEqual(s.factor.version, 2); self.assertEqual(len(s.alternatives), 1)


class NZDocumentedFactors(unittest.TestCase):
    """Values below are read from the supplied NZ MfE 2023 guide (Tables 3 and 9)."""
    def setUp(self):
        self.nz = load_nz_mfe_2023()
    def _sel(self, **kw):
        return select_factor(self.nz, allow_unverified=True, country="NZ", **kw).factor
    def test_electricity_2022(self):
        f = self._sel(category="electricity", activity="grid_average", year=2022)
        self.assertEqual(f.total_co2e, Dc("0.0742"))
        r = calc.calculate(ActivityInput(D(10000), "kWh", "NZ", 2022, "electricity", "grid_average"), f)
        self.assertEqual(r.kg_co2e, Dc("742.0000")); self.assertEqual(r.t_co2e, Dc("0.742"))
        self.assertTrue(r.is_estimate)  # unverified -> flagged
    def test_diesel_commercial(self):
        f = self._sel(category="stationary_fuel", activity="diesel_commercial", year=2021)
        r = calc.calculate(ActivityInput(D(100), "litre", "NZ", 2021, "stationary_fuel", "diesel_commercial"), f)
        self.assertEqual(r.kg_co2e, Dc(269))
        self.assertEqual(set(r.per_gas_kg_co2e), {"CO2", "CH4", "N2O"})
    def test_natural_gas_unit_conversion_not_silent(self):
        # GJ and kWh rows both exist; selecting by denominators must be explicit.
        gas = [f for f in self.nz if f.activity == "natural_gas_commercial"]
        self.assertEqual({f.denominator_unit for f in gas}, {"kWh", "GJ"})
    def test_all_rows_loaded(self):
        self.assertEqual(len(self.nz), 37)
        self.assertTrue(all(f.status == VS.UNVERIFIED for f in self.nz))
        self.assertTrue(all(f.source_url is None for f in self.nz))  # never invented


if __name__ == "__main__":
    unittest.main()
