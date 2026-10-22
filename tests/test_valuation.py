import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import valuation


class DCFTests(unittest.TestCase):
    def test_dcf_basic_bridge(self):
        result = valuation.dcf_fcff(
            fcff=[100.0, 110.0], wacc=0.10, terminal_growth=0.02,
            diluted_shares=10.0, net_debt=100.0,
        )
        pv_explicit = 100 / 1.1 + 110 / (1.1 ** 2)
        tv = 110 * 1.02 / (0.10 - 0.02)
        ev = pv_explicit + tv / (1.1 ** 2)
        self.assertAlmostEqual(result["enterprise_value"], ev, places=9)
        self.assertAlmostEqual(result["equity_value"], ev - 100, places=9)
        self.assertAlmostEqual(result["value_per_share"], (ev - 100) / 10, places=9)

    def test_dcf_rejects_wacc_not_above_growth(self):
        with self.assertRaises(ValueError):
            valuation.dcf_fcff([100], 0.03, 0.03, 10)

    def test_dcf_rate_sensitivity_direction(self):
        low = valuation.dcf_fcff([100, 110, 120], 0.08, 0.02, 10)["value_per_share"]
        high = valuation.dcf_fcff([100, 110, 120], 0.10, 0.02, 10)["value_per_share"]
        self.assertGreater(low, high)

    def test_dcf_growth_sensitivity_direction(self):
        low = valuation.dcf_fcff([100, 110, 120], 0.10, 0.01, 10)["value_per_share"]
        high = valuation.dcf_fcff([100, 110, 120], 0.10, 0.03, 10)["value_per_share"]
        self.assertGreater(high, low)

    def test_dcf_invalid_share_count(self):
        with self.assertRaises(ValueError):
            valuation.dcf_fcff([100], 0.1, 0.02, 0)

    def test_dcf_requires_positive_terminal_cashflow(self):
        with self.assertRaises(ValueError):
            valuation.dcf_fcff([100, -10], 0.1, 0.02, 10)


class DDMTests(unittest.TestCase):
    def test_ddm_basic(self):
        result = valuation.ddm([1.0, 1.05, 1.10], 0.10, 0.02)
        pv = 1.0 / 1.1 + 1.05 / (1.1 ** 2) + 1.10 / (1.1 ** 3)
        tv = 1.10 * 1.02 / (0.10 - 0.02)
        expected = pv + tv / (1.1 ** 3)
        self.assertAlmostEqual(result["value_per_share"], expected, places=9)

    def test_ddm_rejects_ke_not_above_growth(self):
        with self.assertRaises(ValueError):
            valuation.ddm([1.0, 1.1], 0.03, 0.04)

    def test_ddm_rate_sensitivity_direction(self):
        low = valuation.ddm([1.0, 1.05, 1.10], 0.08, 0.02)["value_per_share"]
        high = valuation.ddm([1.0, 1.05, 1.10], 0.10, 0.02)["value_per_share"]
        self.assertGreater(low, high)

    def test_ddm_growth_sensitivity_direction(self):
        low = valuation.ddm([1.0, 1.05, 1.10], 0.10, 0.01)["value_per_share"]
        high = valuation.ddm([1.0, 1.05, 1.10], 0.10, 0.03)["value_per_share"]
        self.assertGreater(high, low)

    def test_ddm_requires_positive_terminal_dividend(self):
        with self.assertRaises(ValueError):
            valuation.ddm([1.0, 0.0], 0.10, 0.02)

    def test_sensitivity_has_none_when_invalid(self):
        result = valuation.ddm_sensitivity([1, 1.1], [0.03], [0.02, 0.04])
        self.assertIsNotNone(result["value_per_share_matrix"][0][0])
        self.assertIsNone(result["value_per_share_matrix"][0][1])

    def test_json_dispatch(self):
        out = valuation.run_payload({
            "model": "ddm", "dividends_per_share": [1.0, 1.1],
            "ke": 0.1, "terminal_growth": 0.02,
        })
        self.assertEqual(out["model"], "ddm")
        self.assertTrue(math.isfinite(out["value_per_share"]))


class FCFETests(unittest.TestCase):
    def test_fcfe_basic(self):
        result = valuation.fcfe([100.0, 110.0], 0.10, 0.02, 10.0)
        pv = 100 / 1.1 + 110 / (1.1 ** 2)
        tv = 110 * 1.02 / (0.10 - 0.02)
        expected = pv + tv / (1.1 ** 2)
        self.assertAlmostEqual(result["equity_value"], expected, places=9)
        self.assertAlmostEqual(result["value_per_share"], expected / 10, places=9)

    def test_fcfe_no_equity_bridge(self):
        # FCFE is an equity flow: equity_value must equal pv_explicit + pv_terminal exactly
        result = valuation.fcfe([100.0, 110.0], 0.10, 0.02, 10.0)
        self.assertAlmostEqual(
            result["equity_value"],
            result["pv_explicit_fcfe"] + result["pv_terminal_value"],
            places=9,
        )

    def test_fcfe_rejects_ke_not_above_growth(self):
        with self.assertRaises(ValueError):
            valuation.fcfe([100], 0.03, 0.03, 10)

    def test_fcfe_requires_positive_terminal_flow(self):
        with self.assertRaises(ValueError):
            valuation.fcfe([100, -10], 0.1, 0.02, 10)

    def test_fcfe_invalid_shares(self):
        with self.assertRaises(ValueError):
            valuation.fcfe([100], 0.1, 0.02, 0)

    def test_fcfe_rate_sensitivity_direction(self):
        low = valuation.fcfe([100, 110, 120], 0.08, 0.02, 10)["value_per_share"]
        high = valuation.fcfe([100, 110, 120], 0.10, 0.02, 10)["value_per_share"]
        self.assertGreater(low, high)


class ResidualIncomeTests(unittest.TestCase):
    def test_ri_basic(self):
        result = valuation.residual_income(
            bvps=10.0, roe_path=[0.15, 0.15], payout=0.4, ke=0.10,
            terminal_roe=0.12, terminal_book_growth=0.05,
        )
        ri1 = (0.15 - 0.10) * 10.0
        bvps1 = 10.0 * (1.0 + 0.6 * 0.15)
        ri2 = (0.15 - 0.10) * bvps1
        bvps2 = bvps1 * (1.0 + 0.6 * 0.15)
        pv = ri1 / 1.1 + ri2 / 1.21
        terminal_ri = (0.12 - 0.10) * bvps2
        tv = terminal_ri / (0.10 - 0.05)
        expected = 10.0 + pv + tv / 1.21
        self.assertAlmostEqual(result["value_per_share"], expected, places=9)
        self.assertAlmostEqual(result["implied_pb"], expected / 10.0, places=9)
        self.assertAlmostEqual(result["bvps_terminal_start"], bvps2, places=9)

    def test_ri_roe_equal_ke_gives_book_value(self):
        result = valuation.residual_income(
            bvps=10.0, roe_path=[0.10, 0.10], payout=0.4, ke=0.10,
            terminal_roe=0.10, terminal_book_growth=0.05,
        )
        self.assertAlmostEqual(result["value_per_share"], 10.0, places=9)

    def test_ri_below_ke_can_be_below_book(self):
        result = valuation.residual_income(
            bvps=10.0, roe_path=[0.08, 0.08], payout=0.4, ke=0.10,
            terminal_roe=0.08, terminal_book_growth=0.04,
        )
        self.assertLess(result["value_per_share"], 10.0)

    def test_ri_rejects_ke_not_above_book_growth(self):
        with self.assertRaises(ValueError):
            valuation.residual_income(10.0, [0.15], 0.4, 0.05, 0.12, 0.05)

    def test_ri_rejects_bad_payout(self):
        with self.assertRaises(ValueError):
            valuation.residual_income(10.0, [0.15], 1.2, 0.10, 0.12, 0.05)

    def test_ri_rejects_nonpositive_bvps(self):
        with self.assertRaises(ValueError):
            valuation.residual_income(0.0, [0.15], 0.4, 0.10, 0.12, 0.05)


class PEVTests(unittest.TestCase):
    def test_pev_basic(self):
        result = valuation.pev(1000.0, 1.2, 100.0)
        self.assertAlmostEqual(result["value_per_share"], 12.0, places=9)

    def test_pev_holdco_discount(self):
        result = valuation.pev(1000.0, 1.2, 100.0, holdco_discount=0.2)
        self.assertAlmostEqual(result["value_per_share"], 9.6, places=9)

    def test_pev_rejects_bad_inputs(self):
        with self.assertRaises(ValueError):
            valuation.pev(0.0, 1.2, 100.0)
        with self.assertRaises(ValueError):
            valuation.pev(1000.0, 0.0, 100.0)
        with self.assertRaises(ValueError):
            valuation.pev(1000.0, 1.2, 0.0)
        with self.assertRaises(ValueError):
            valuation.pev(1000.0, 1.2, 100.0, holdco_discount=1.0)


class NAVTests(unittest.TestCase):
    def test_nav_basic(self):
        result = valuation.nav([300.0, 200.0], 100.0, 50.0)
        self.assertAlmostEqual(result["gross_asset_value"], 500.0, places=9)
        self.assertAlmostEqual(result["nav_total"], 400.0, places=9)
        self.assertAlmostEqual(result["value_per_share"], 8.0, places=9)

    def test_nav_stress_can_be_negative(self):
        result = valuation.nav([100.0, 80.0], 250.0, 50.0, scenario="stress")
        self.assertAlmostEqual(result["value_per_share"], -1.4, places=9)
        self.assertEqual(result["scenario"], "stress")

    def test_nav_rejects_empty_assets(self):
        with self.assertRaises(ValueError):
            valuation.nav([], 100.0, 50.0)

    def test_nav_rejects_nonpositive_shares(self):
        with self.assertRaises(ValueError):
            valuation.nav([100.0], 10.0, 0.0)


class AFFOTests(unittest.TestCase):
    def test_affo_cap_rate(self):
        result = valuation.affo(1.0, cap_rate=0.05)
        self.assertEqual(result["method"], "cap_rate")
        self.assertAlmostEqual(result["value_per_share"], 20.0, places=9)

    def test_affo_multiple(self):
        result = valuation.affo(1.0, multiple=15.0)
        self.assertEqual(result["method"], "multiple")
        self.assertAlmostEqual(result["value_per_share"], 15.0, places=9)

    def test_affo_requires_exactly_one_method(self):
        with self.assertRaises(ValueError):
            valuation.affo(1.0)
        with self.assertRaises(ValueError):
            valuation.affo(1.0, cap_rate=0.05, multiple=15.0)

    def test_affo_rejects_bad_inputs(self):
        with self.assertRaises(ValueError):
            valuation.affo(0.0, cap_rate=0.05)
        with self.assertRaises(ValueError):
            valuation.affo(1.0, cap_rate=0.0)


class NormalizeCycleTests(unittest.TestCase):
    def test_normalize_median_odd(self):
        result = valuation.normalize_cycle([1.0, 2.0, 3.0, 4.0, 100.0])
        self.assertAlmostEqual(result["normalized_value"], 3.0, places=9)

    def test_normalize_median_even(self):
        result = valuation.normalize_cycle([1.0, 2.0, 3.0, 4.0])
        self.assertAlmostEqual(result["normalized_value"], 2.5, places=9)

    def test_normalize_mean(self):
        result = valuation.normalize_cycle([1.0, 2.0, 100.0], method="mean")
        self.assertAlmostEqual(result["normalized_value"], 103.0 / 3.0, places=9)

    def test_normalize_rejects_bad_method(self):
        with self.assertRaises(ValueError):
            valuation.normalize_cycle([1.0, 2.0], method="mode")


if __name__ == "__main__":
    unittest.main(verbosity=2)
