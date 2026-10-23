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


class DCFExitMultipleTests(unittest.TestCase):
    def test_exit_multiple_basic_bridge(self):
        result = valuation.dcf_fcff(
            fcff=[100.0, 110.0], wacc=0.10, diluted_shares=10.0, net_debt=100.0,
            terminal_method="exit_multiple", ebitda=[200.0, 220.0], exit_ev_ebitda=6.0,
        )
        pv_explicit = 100 / 1.1 + 110 / (1.1 ** 2)
        tv = 6.0 * 220.0
        ev = pv_explicit + tv / (1.1 ** 2)
        self.assertEqual(result["terminal_method"], "exit_multiple")
        self.assertAlmostEqual(result["terminal_value_at_year_n"], tv, places=9)
        self.assertAlmostEqual(result["enterprise_value"], ev, places=9)
        self.assertAlmostEqual(result["equity_value"], ev - 100, places=9)
        self.assertAlmostEqual(result["value_per_share"], (ev - 100) / 10, places=9)
        self.assertIsNone(result["terminal_growth"])

    def test_exit_multiple_implied_growth_matches_gordon(self):
        gordon = valuation.dcf_fcff(
            fcff=[100.0, 110.0], wacc=0.10, terminal_growth=0.025, diluted_shares=10.0,
        )
        multiple = gordon["terminal_value_at_year_n"] / 220.0
        result = valuation.dcf_fcff(
            fcff=[100.0, 110.0], wacc=0.10, diluted_shares=10.0,
            terminal_method="exit_multiple", ebitda=[200.0, 220.0], exit_ev_ebitda=multiple,
        )
        self.assertAlmostEqual(result["implied_perpetuity_growth"], 0.025, places=9)
        self.assertAlmostEqual(result["value_per_share"], gordon["value_per_share"], places=6)
        self.assertFalse(any(w.startswith("exit multiple implies") for w in result["warnings"]))

    def test_exit_multiple_allows_negative_terminal_fcff(self):
        result = valuation.dcf_fcff(
            fcff=[100.0, -10.0], wacc=0.10, diluted_shares=10.0,
            terminal_method="exit_multiple", ebitda=[50.0, 60.0], exit_ev_ebitda=8.0,
        )
        self.assertAlmostEqual(result["terminal_value_at_year_n"], 480.0, places=9)
        self.assertGreater(result["implied_perpetuity_growth"], 0.05)
        self.assertTrue(any("perpetuity growth" in w for w in result["warnings"]))

    def test_exit_multiple_warns_when_growth_at_or_above_wacc(self):
        result = valuation.dcf_fcff(
            fcff=[-1.0], wacc=0.05, diluted_shares=1.0,
            terminal_method="exit_multiple", ebitda=[1.0], exit_ev_ebitda=100.0,
        )
        self.assertGreaterEqual(result["implied_perpetuity_growth"], 0.05)
        self.assertTrue(any("at or above WACC" in w for w in result["warnings"]))

    def test_exit_multiple_rejects_bad_inputs(self):
        base = dict(fcff=[100.0], wacc=0.10, diluted_shares=10.0)
        with self.assertRaises(ValueError):
            valuation.dcf_fcff(**base, terminal_method="exit_multiple", exit_ev_ebitda=6.0)
        with self.assertRaises(ValueError):
            valuation.dcf_fcff(**base, terminal_method="exit_multiple", ebitda=[5.0, 6.0], exit_ev_ebitda=6.0)
        with self.assertRaises(ValueError):
            valuation.dcf_fcff(**base, terminal_method="exit_multiple", ebitda=[5.0])
        with self.assertRaises(ValueError):
            valuation.dcf_fcff(**base, terminal_method="exit_multiple", ebitda=[5.0], exit_ev_ebitda=-6.0)
        with self.assertRaises(ValueError):
            valuation.dcf_fcff(fcff=[100.0], wacc=0.10, diluted_shares=10.0,
                               terminal_method="exit_multiple", ebitda=[-5.0], exit_ev_ebitda=6.0)
        with self.assertRaises(ValueError):
            valuation.dcf_fcff(**base, terminal_method="pev", ebitda=[5.0], exit_ev_ebitda=6.0)

    def test_gordon_still_requires_terminal_growth(self):
        with self.assertRaises(ValueError):
            valuation.dcf_fcff(fcff=[100.0], wacc=0.10, diluted_shares=10.0)

    def test_exit_multiple_via_payload(self):
        result = valuation.run_payload({
            "model": "dcf_fcff", "fcff": [100.0, 110.0], "wacc": 0.10,
            "diluted_shares": 10.0, "terminal_method": "exit_multiple",
            "ebitda": [200.0, 220.0], "exit_ev_ebitda": 6.0, "currency": "CNY",
        })
        self.assertAlmostEqual(result["terminal_value_at_year_n"], 1320.0, places=9)
        self.assertEqual(result["input_metadata"]["currency"], "CNY")


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

    def test_normalize_trimmed_mean(self):
        # 10 observations: 1 trimmed from each end (int(10 * 0.1) == 1),
        # so 1 and 100 drop out and the mean of the remaining 8 is 44/8.
        result = valuation.normalize_cycle(
            [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 100.0],
            method="trimmed_mean",
        )
        self.assertAlmostEqual(result["normalized_value"], 44.0 / 8.0, places=9)

    def test_normalize_trimmed_mean_short_series_no_trim(self):
        # Fewer than 10 observations: cut == 0, so nothing is trimmed.
        result = valuation.normalize_cycle([1.0, 2.0, 3.0], method="trimmed_mean")
        self.assertAlmostEqual(result["normalized_value"], 2.0, places=9)

    def test_normalize_rejects_bad_method(self):
        with self.assertRaises(ValueError):
            valuation.normalize_cycle([1.0, 2.0], method="mode")


class ReitNoiTests(unittest.TestCase):
    """Property-level cap-rate valuation must stay distinct from the
    equity-level AFFO method, and must bridge to equity like nav()."""

    def test_property_value_and_bridge(self):
        result = valuation.reit_noi(100.0, 0.05, 500.0, 100.0)
        self.assertAlmostEqual(result["property_value"], 2000.0, places=9)
        self.assertAlmostEqual(result["nav_total"], 1500.0, places=9)
        self.assertAlmostEqual(result["value_per_share"], 15.0, places=9)
        self.assertEqual(result["model"], "reit_noi")
        self.assertEqual(result["bridge_model"], "nav")

    def test_other_assets_included(self):
        result = valuation.reit_noi(100.0, 0.05, 500.0, 100.0, other_assets=50.0)
        self.assertAlmostEqual(result["gross_asset_value"], 2050.0, places=9)
        self.assertAlmostEqual(result["value_per_share"], 15.5, places=9)

    def test_stress_scenario_can_be_negative(self):
        result = valuation.reit_noi(80.0, 0.0625, 1500.0, 100.0, scenario="stress")
        self.assertAlmostEqual(result["property_value"], 1280.0, places=9)
        self.assertLess(result["value_per_share"], 0)

    def test_rejects_bad_inputs(self):
        with self.assertRaises(ValueError):
            valuation.reit_noi(0.0, 0.05, 500.0, 100.0)
        with self.assertRaises(ValueError):
            valuation.reit_noi(100.0, 0.0, 500.0, 100.0)
        with self.assertRaises(ValueError):
            valuation.reit_noi(100.0, 0.05, 500.0, 0.0)

    def test_cap_rate_basis_warning_note(self):
        result = valuation.reit_noi(100.0, 0.05, 500.0, 100.0)
        self.assertIn("NOT the", result["note"])


class ComparableMultiplesTests(unittest.TestCase):
    def test_pe_pb_math(self):
        out = valuation.comparable_multiples({
            "per_share_metrics": {"eps": 1.5, "bvps": 10.0},
            "multiples": {"pe": 10, "pb": 1.2},
        })
        self.assertAlmostEqual(out["methods"]["pe"]["implied_value_per_share"], 15.0, places=9)
        self.assertAlmostEqual(out["methods"]["pb"]["implied_value_per_share"], 12.0, places=9)
        self.assertEqual(len(out["warnings"]), 2)  # bare multiples warn

    def test_ev_ebitda_bridge(self):
        out = valuation.comparable_multiples({
            "per_share_metrics": {},
            "entity_metrics": {"ebitda": 1000, "net_debt": 2000, "shares": 100},
            "multiples": {"ev_ebitda": {"value": 8, "comparable_set": "peers", "as_of": "2026-10-22"}},
        })
        m = out["methods"]["ev_ebitda"]
        self.assertAlmostEqual(m["implied_enterprise_value"], 8000.0, places=9)
        self.assertAlmostEqual(m["implied_equity_value"], 6000.0, places=9)
        self.assertAlmostEqual(m["implied_value_per_share"], 60.0, places=9)

    def test_p_affo(self):
        out = valuation.comparable_multiples({
            "per_share_metrics": {"affo_per_share": 2.0},
            "multiples": {"p_affo": 15},
        })
        self.assertAlmostEqual(out["methods"]["p_affo"]["implied_value_per_share"], 30.0, places=9)

    def test_dict_multiple_requires_comparable_set_and_date(self):
        with self.assertRaises(ValueError):
            valuation.comparable_multiples({
                "per_share_metrics": {"eps": 1.5},
                "multiples": {"pe": {"value": 10, "as_of": "2026-10-22"}},
            })
        with self.assertRaises(ValueError):
            valuation.comparable_multiples({
                "per_share_metrics": {"eps": 1.5},
                "multiples": {"pe": {"value": 10, "comparable_set": "peers"}},
            })

    def test_ev_ebitda_requires_full_bridge(self):
        with self.assertRaises(ValueError):
            valuation.comparable_multiples({
                "per_share_metrics": {},
                "entity_metrics": {"ebitda": 1000},
                "multiples": {"ev_ebitda": 8},
            })

    def test_no_recognised_method_raises(self):
        with self.assertRaises(ValueError):
            valuation.comparable_multiples({
                "per_share_metrics": {"eps": 1.5},
                "multiples": {"p_sales": 3},
            })

    def test_empty_multiples_raises(self):
        with self.assertRaises(ValueError):
            valuation.comparable_multiples({"multiples": {}})


class ReverseSolverTests(unittest.TestCase):
    """Reverse solvers must round-trip: solving for a parameter that produces
    a target price must reproduce that price, and failure modes must be
    reported as statuses, not silent numbers."""

    BASE = dict(
        fcff=[1000.0, 1080.0, 1150.0, 1210.0, 1260.0],
        wacc=0.085, terminal_growth=0.025, diluted_shares=1000.0,
        net_debt=2500.0, non_operating_assets=200.0, minority_interest=50.0,
    )

    def _value(self, **overrides):
        params = dict(self.BASE)
        params.update(overrides)
        return valuation.dcf_fcff(
            params["fcff"], params["wacc"], params["terminal_growth"],
            params["diluted_shares"], params["net_debt"],
            params["non_operating_assets"], params["minority_interest"],
        )["value_per_share"]

    def test_reverse_growth_round_trip(self):
        target = self._value()
        out = valuation.reverse_dcf_growth(
            self.BASE["fcff"], self.BASE["wacc"], self.BASE["diluted_shares"],
            target, self.BASE["net_debt"], self.BASE["non_operating_assets"],
            self.BASE["minority_interest"],
        )
        self.assertEqual(out["status"], "solved")
        self.assertAlmostEqual(out["implied_terminal_growth"], 0.025, places=6)
        self.assertAlmostEqual(out["value_at_solution"], target, places=4)
        self.assertTrue(out["converged"])

    def test_reverse_growth_below_range(self):
        low = valuation.dcf_fcff(
            self.BASE["fcff"], self.BASE["wacc"], -0.5, self.BASE["diluted_shares"],
            self.BASE["net_debt"], self.BASE["non_operating_assets"],
            self.BASE["minority_interest"],
        )["value_per_share"]
        out = valuation.reverse_dcf_growth(
            self.BASE["fcff"], self.BASE["wacc"], self.BASE["diluted_shares"],
            low - 1.0, self.BASE["net_debt"], self.BASE["non_operating_assets"],
            self.BASE["minority_interest"],
        )
        self.assertEqual(out["status"], "target_below_min_modelled_value")
        self.assertIsNone(out["implied_terminal_growth"])

    def test_reverse_wacc_round_trip(self):
        target = self._value()
        out = valuation.reverse_dcf_wacc(
            self.BASE["fcff"], self.BASE["terminal_growth"], self.BASE["diluted_shares"],
            target, self.BASE["net_debt"], self.BASE["non_operating_assets"],
            self.BASE["minority_interest"],
        )
        self.assertEqual(out["status"], "solved")
        self.assertAlmostEqual(out["break_even_wacc"], 0.085, places=6)
        self.assertAlmostEqual(out["value_at_solution"], target, places=4)

    def test_reverse_wacc_deep_undervaluation_status(self):
        # No debt bridge: at a 300% discount rate the equity is still worth
        # ~3.4 per share, so a 0.01 target sits below the entire range.
        out = valuation.reverse_dcf_wacc([100.0, 110.0], 0.02, 10.0, 0.01)
        self.assertEqual(out["status"], "target_below_value_at_max_rate")
        self.assertIsNone(out["break_even_wacc"])

    def test_reverse_fcff_scale_round_trip(self):
        target = self._value()
        out = valuation.reverse_dcf_fcff_scale(
            self.BASE["fcff"], self.BASE["wacc"], self.BASE["terminal_growth"],
            self.BASE["diluted_shares"], target, self.BASE["net_debt"],
            self.BASE["non_operating_assets"], self.BASE["minority_interest"],
        )
        self.assertEqual(out["status"], "solved")
        self.assertAlmostEqual(out["implied_flow_scale"], 1.0, places=6)

    def test_reverse_fcff_scale_non_positive_ev(self):
        out = valuation.reverse_dcf_fcff_scale(
            [-1000.0, 1.0], 0.10, 0.02, 10.0, 50.0,
        )
        self.assertEqual(out["status"], "no_positive_scale_solution")

    def test_reverse_ddm_ke_round_trip(self):
        dividends = [2.0, 2.06, 2.12, 2.18, 2.25]
        target = valuation.ddm(dividends, 0.09, 0.025)["value_per_share"]
        out = valuation.reverse_ddm_ke(dividends, target, 0.025)
        self.assertEqual(out["status"], "solved")
        self.assertAlmostEqual(out["break_even_ke"], 0.09, places=6)
        self.assertAlmostEqual(out["value_at_solution"], target, places=4)

    def test_reverse_ddm_ke_below_range(self):
        out = valuation.reverse_ddm_ke([2.0, 2.1], 0.01, 0.025)
        self.assertEqual(out["status"], "target_below_value_at_max_ke")

    def test_reverse_bracket_validation(self):
        with self.assertRaises(ValueError):
            valuation.reverse_dcf_growth(
                self.BASE["fcff"], 0.085, 1000.0, 25.0, g_lower=0.09, g_upper=0.10
            )
        with self.assertRaises(ValueError):
            valuation.reverse_dcf_wacc(
                self.BASE["fcff"], 0.025, 1000.0, 25.0, wacc_lower=0.02, wacc_upper=0.03
            )

    def test_reverse_via_payload(self):
        target = self._value()
        out = valuation.run_payload({
            "model": "reverse_dcf_growth", "fcff": self.BASE["fcff"],
            "wacc": self.BASE["wacc"], "diluted_shares": self.BASE["diluted_shares"],
            "net_debt": self.BASE["net_debt"],
            "non_operating_assets": self.BASE["non_operating_assets"],
            "minority_interest": self.BASE["minority_interest"],
            "target_price": target,
        })
        self.assertEqual(out["status"], "solved")
        self.assertIn("input_echo", out)


class MetadataAndUnitsTests(unittest.TestCase):
    def test_metadata_echoed(self):
        out = valuation.run_payload({
            "model": "ddm", "dividends_per_share": [1.0, 1.1],
            "ke": 0.1, "terminal_growth": 0.02,
            "currency": "CNY", "unit": "RMB per share", "as_of": "2026-10-22",
        })
        self.assertEqual(out["input_metadata"],
                         {"currency": "CNY", "unit": "RMB per share", "as_of": "2026-10-22"})
        self.assertEqual(out["input_echo"]["model"], "ddm")

    def test_metadata_must_be_non_empty_string(self):
        with self.assertRaises(ValueError):
            valuation.run_payload({"model": "ddm", "dividends_per_share": [1.0],
                                   "ke": 0.1, "terminal_growth": 0.02, "currency": ""})
        with self.assertRaises(ValueError):
            valuation.run_payload({"model": "ddm", "dividends_per_share": [1.0],
                                   "ke": 0.1, "terminal_growth": 0.02, "unit": 5})

    def test_check_units_conflict_raises(self):
        with self.assertRaises(ValueError):
            valuation.check_units({"fcff": "million", "shares": "thousand"})

    def test_check_units_consistent_passes(self):
        out = valuation.check_units({"fcff": "million", "net_debt": "million"})
        self.assertTrue(out["consistent"])

    def test_check_units_undeclared_warns(self):
        out = valuation.check_units({"fcff": None, "shares": None})
        self.assertTrue(out["consistent"])
        self.assertEqual(len(out["warnings"]), 2)


class TerminalShareGuardTests(unittest.TestCase):
    def test_negative_ev_terminal_share_is_none(self):
        # A large early loss dominates: EV goes negative while the terminal
        # flow stays positive; the TV share of EV is meaningless.
        result = valuation.dcf_fcff([-1000.0, 1.0], 0.10, 0.02, 10.0)
        self.assertLess(result["enterprise_value"], 0)
        self.assertIsNone(result["terminal_value_share_of_ev"])

    def test_positive_ev_terminal_share_computed(self):
        result = valuation.dcf_fcff([100.0, 110.0], 0.10, 0.02, 10.0)
        self.assertIsNotNone(result["terminal_value_share_of_ev"])
        self.assertGreater(result["terminal_value_share_of_ev"], 0)


class TerminalShareWarningTests(unittest.TestCase):
    """TV share above the 0.75 threshold must raise a warning."""

    def test_dcf_fcff_high_terminal_share_warns(self):
        # 5-year explicit period with small early flows: TV dominates.
        result = valuation.dcf_fcff([1.0, 1.1, 1.21, 1.33, 1.46], 0.08, 0.03, 10.0)
        self.assertGreater(result["terminal_value_share_of_ev"], 0.75)
        self.assertTrue(any("terminal value is" in w for w in result["warnings"]))

    def test_dcf_fcff_low_terminal_share_no_warning(self):
        # Five-year explicit period with level flows: explicit period carries most of the value.
        result = valuation.dcf_fcff([100.0] * 5, 0.10, 0.02, 10.0)
        self.assertLess(result["terminal_value_share_of_ev"], 0.75)
        self.assertEqual(result["warnings"], [])

    def test_ddm_high_terminal_share_warns(self):
        result = valuation.ddm([0.5, 0.55], 0.09, 0.03)
        self.assertGreater(result["terminal_value_share_of_total"], 0.75)
        self.assertTrue(any("terminal value is" in w for w in result["warnings"]))

    def test_fcfe_high_terminal_share_warns(self):
        result = valuation.fcfe([0.5, 0.55], 0.09, 0.03, 10.0)
        self.assertGreater(result["terminal_value_share_of_total"], 0.75)
        self.assertTrue(any("terminal value is" in w for w in result["warnings"]))

    def test_negative_ev_no_warning_key_stays_empty(self):
        result = valuation.dcf_fcff([-1000.0, 1.0], 0.10, 0.02, 10.0)
        self.assertEqual(result["warnings"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
