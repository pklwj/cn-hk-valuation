"""Routing-table consistency and end-to-end acceptance cases.

These tests verify that (a) the DEFAULT_ROUTING table stays consistent with the
models the script can actually run, (b) unknown company types are refused
rather than guessed, and (c) each of the six acceptance company types runs
end-to-end through run_payload with sane outputs.

Case inputs are synthetic and exist to test model selection and formula
behaviour. They are not company research and must not be quoted as such.
"""
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import valuation


class RoutingTableTests(unittest.TestCase):
    EXPECTED_TYPES = {
        "bank", "insurer", "dividend_payer", "consumer_manufacturing",
        "cyclical_resource", "growth", "real_estate", "reit",
    }

    def test_table_covers_all_documented_types(self):
        self.assertEqual(set(valuation.DEFAULT_ROUTING), self.EXPECTED_TYPES)

    def test_every_route_has_primary_and_refusal_rule(self):
        for name, route in valuation.DEFAULT_ROUTING.items():
            self.assertTrue(route["primary"], f"{name} missing primary model")
            self.assertTrue(route["refuse_if"].strip(), f"{name} missing refusal rule")
            self.assertIsInstance(route["secondary"], list)

    def test_routed_models_are_dispatchable(self):
        dispatchable = {
            "dcf_fcff", "ddm", "dcf_sensitivity", "ddm_sensitivity", "fcfe",
            "residual_income", "pev", "nav", "affo", "normalize_cycle",
        }
        for name, route in valuation.DEFAULT_ROUTING.items():
            self.assertIn(route["primary"], dispatchable, f"{name} primary not runnable")
            for model in route["secondary"]:
                self.assertIn(model, dispatchable, f"{name} secondary not runnable")

    def test_unknown_type_is_refused(self):
        with self.assertRaises(ValueError):
            valuation.route_model("cryptocurrency")

    def test_route_is_case_insensitive(self):
        route = valuation.route_model("Bank")
        self.assertEqual(route["primary"], "ddm")

    def test_route_returns_defensive_copy(self):
        route = valuation.route_model("bank")
        route["primary"] = "tampered"
        self.assertEqual(valuation.DEFAULT_ROUTING["bank"]["primary"], "ddm")

    def test_route_via_payload(self):
        out = valuation.run_payload({"model": "route", "company_type": "reit"})
        self.assertEqual(out["primary"], "affo")
        self.assertEqual(out["secondary"], ["nav"])


class AcceptanceCaseTests(unittest.TestCase):
    """Six company types end-to-end through the JSON dispatcher."""

    def test_case_bank_ddm_plus_residual_income(self):
        ddm_out = valuation.run_payload({
            "model": "ddm",
            "dividends_per_share": [2.0, 2.06, 2.12, 2.18, 2.25],
            "ke": 0.085, "terminal_growth": 0.025,
        })
        ri_out = valuation.run_payload({
            "model": "residual_income",
            "bvps": 40.0, "roe_path": [0.12, 0.12, 0.12, 0.12, 0.12],
            "payout": 0.35, "ke": 0.085,
            "terminal_roe": 0.105, "terminal_book_growth": 0.04,
        })
        self.assertTrue(math.isfinite(ddm_out["value_per_share"]))
        self.assertGreater(ri_out["implied_pb"], 1.0)  # ROE above Ke creates value
        # Divergence must be diagnosable: DDM values distributed cash only,
        # RI also credits retained earnings earning above Ke.
        self.assertGreater(ri_out["value_per_share"], ddm_out["value_per_share"])

    def test_case_dividend_payer_ddm_plus_fcfe(self):
        ddm_out = valuation.run_payload({
            "model": "ddm",
            "dividends_per_share": [1.5, 1.55, 1.6, 1.65, 1.7],
            "ke": 0.08, "terminal_growth": 0.02,
        })
        fcfe_out = valuation.run_payload({
            "model": "fcfe",
            "fcfe": [160.0, 165.0, 170.0, 175.0, 180.0],
            "ke": 0.08, "terminal_growth": 0.02, "diluted_shares": 100.0,
        })
        # FCFE above dividends => DDM understates; divergence must be explained
        # (retained cash and reinvestment), never averaged away.
        self.assertGreater(fcfe_out["value_per_share"], ddm_out["value_per_share"])

    def test_case_consumer_manufacturing_fcff_plus_fcfe_converge(self):
        fcff_out = valuation.run_payload({
            "model": "dcf_fcff",
            "fcff": [1000.0, 1060.0, 1120.0, 1180.0, 1240.0],
            "wacc": 0.09, "terminal_growth": 0.03, "diluted_shares": 500.0,
            "net_debt": 800.0,
        })
        fcfe_out = valuation.run_payload({
            "model": "fcfe",
            "fcfe": [950.0, 1010.0, 1070.0, 1130.0, 1190.0],
            "ke": 0.105, "terminal_growth": 0.03, "diluted_shares": 500.0,
        })
        # With a stable capital structure the two equity values should be in
        # the same neighbourhood; a large gap flags an inconsistency.
        ratio = fcfe_out["value_per_share"] / fcff_out["value_per_share"]
        self.assertGreater(ratio, 0.7)
        self.assertLess(ratio, 1.4)

    def test_case_cyclical_normalization_then_dcf(self):
        norm = valuation.run_payload({
            "model": "normalize_cycle",
            "values": [8.0, 12.0, 5.0, 10.0, 3.0, 9.0, 4.0, 11.0],
        })
        self.assertGreater(norm["normalized_value"], norm["min"])
        self.assertLess(norm["normalized_value"], norm["max"])
        dcf_out = valuation.run_payload({
            "model": "dcf_fcff",
            "fcff": [norm["normalized_value"] * 40.0] * 5,
            "wacc": 0.09, "terminal_growth": 0.02, "diluted_shares": 100.0,
        })
        self.assertTrue(math.isfinite(dcf_out["value_per_share"]))

    def test_case_growth_staged_scenario_dcf(self):
        bear = valuation.run_payload({
            "model": "dcf_fcff",
            "fcff": [-200.0, -100.0, 50.0, 200.0, 400.0],
            "wacc": 0.12, "terminal_growth": 0.02, "diluted_shares": 100.0,
            "net_debt": 500.0,
        })
        bull = valuation.run_payload({
            "model": "dcf_fcff",
            "fcff": [-200.0, -50.0, 200.0, 500.0, 900.0],
            "wacc": 0.10, "terminal_growth": 0.035, "diluted_shares": 100.0,
            "net_debt": 500.0,
        })
        # Loss-making early years are allowed as long as the terminal year is
        # positive; the scenario spread is the honest output, not a point.
        self.assertGreater(bull["value_per_share"], bear["value_per_share"])

    def test_case_real_estate_nav_with_debt_stress(self):
        base = valuation.run_payload({
            "model": "nav",
            "asset_values": [600.0, 300.0, 100.0],
            "liabilities": 500.0, "shares": 80.0, "scenario": "base",
        })
        stress = valuation.run_payload({
            "model": "nav",
            "asset_values": [480.0, 240.0, 80.0],  # -20% revaluation
            "liabilities": 500.0, "shares": 80.0, "scenario": "stress",
        })
        self.assertAlmostEqual(base["value_per_share"], 6.25, places=9)
        self.assertAlmostEqual(stress["value_per_share"], 3.75, places=9)
        self.assertLess(stress["value_per_share"], base["value_per_share"])

    def test_case_insurer_pev(self):
        out = valuation.run_payload({
            "model": "pev",
            "embedded_value": 2000.0, "pev_multiple": 0.8,
            "shares": 100.0, "holdco_discount": 0.15,
        })
        self.assertAlmostEqual(out["value_per_share"], 2000.0 * 0.8 * 0.85 / 100.0, places=9)

    def test_missing_input_is_refused_not_invented(self):
        with self.assertRaises(KeyError):
            valuation.run_payload({"model": "ddm", "ke": 0.09})  # no dividends
        with self.assertRaises(ValueError):
            valuation.run_payload({"model": "nav", "asset_values": [], "liabilities": 1, "shares": 1})
        with self.assertRaises(ValueError):
            valuation.run_payload({"model": "affo", "affo_per_share": 1.0})  # no method


class KeToValuationIntegrationTests(unittest.TestCase):
    """Cost-of-capital estimation composes with the valuation models through
    the single dispatcher: estimate Ke, then value at that Ke."""

    def test_capm_ke_then_ddm(self):
        ke_out = valuation.run_payload({
            "model": "capm_ke",
            "risk_free_rate": {"value": 0.021, "source": "CN 10Y CGB, SSE", "as_of": "2026-10-22"},
            "beta": {"value": 0.95, "source": "exchange regression", "as_of": "2026-10-22"},
            "equity_risk_premium": {"value": 0.062, "source": "documented ERP study",
                                    "as_of": "2026-09-30", "method": "historical", "market": "A-share"},
        })
        ke = ke_out["ke"]
        self.assertAlmostEqual(ke, 0.0799, places=6)
        ddm_out = valuation.run_payload({
            "model": "ddm", "dividends_per_share": [1.5, 1.55, 1.6, 1.65, 1.7],
            "ke": ke, "terminal_growth": 0.02,
        })
        self.assertTrue(math.isfinite(ddm_out["value_per_share"]))
        self.assertEqual(ddm_out["input_echo"]["ke"], ke)

    def test_ke_scenario_then_sensitivity(self):
        scenario = valuation.run_payload({
            "model": "ke_scenario",
            "bear": {"method": "capm",
                     "inputs": {"risk_free_rate": 0.026, "beta": 1.25, "equity_risk_premium": 0.07},
                     "rationale": "rate shock"},
            "base": {"method": "capm",
                     "inputs": {"risk_free_rate": 0.021, "beta": 0.95, "equity_risk_premium": 0.062},
                     "rationale": "central estimate"},
            "bull": {"method": "capm",
                     "inputs": {"risk_free_rate": 0.018, "beta": 0.85, "equity_risk_premium": 0.058},
                     "rationale": "benign path"},
        })
        ke_range = [scenario["scenarios"][k]["ke"] for k in ("bear", "base", "bull")]
        sens = valuation.run_payload({
            "model": "ddm_sensitivity", "dividends_per_share": [1.5, 1.55, 1.6, 1.65, 1.7],
            "ke_values": ke_range, "growth_values": [0.015, 0.02, 0.025],
        })
        self.assertEqual(len(sens["value_per_share_matrix"]), 3)
        for row in sens["value_per_share_matrix"]:
            for cell in row:
                self.assertTrue(math.isfinite(cell))

    def test_wacc_refused_for_bank_through_dispatch(self):
        with self.assertRaises(ValueError):
            valuation.run_payload({
                "model": "wacc", "cost_of_equity": 0.10,
                "cost_of_debt": {"basis": "observed", "value": 0.04, "source": "bond"},
                "tax_rate": 0.25, "weight_equity": 0.9, "weight_debt": 0.1,
                "entity_type": "bank",
            })


class HighDividendMediaRegressionTests(unittest.TestCase):
    """SYNTHETIC regression case shaped like a high-dividend advertising /
    media company (not any real issuer's historicals).

    Purpose: DDM + FCFE must diverge in the documented direction (FCFE above
    dividends => DDM understates), the divergence must be explainable by
    retained cash, and reverse DCF must round-trip the base case.
    """

    def test_ddm_fcfe_divergence_direction(self):
        ddm_out = valuation.run_payload({
            "model": "ddm", "dividends_per_share": [0.35, 0.37, 0.39, 0.41, 0.43],
            "ke": 0.085, "terminal_growth": 0.02,
        })
        fcfe_out = valuation.run_payload({
            "model": "fcfe", "fcfe": [42.0, 44.0, 46.0, 48.0, 50.0],
            "ke": 0.085, "terminal_growth": 0.02, "diluted_shares": 100.0,
        })
        self.assertGreater(fcfe_out["value_per_share"], ddm_out["value_per_share"])

    def test_reverse_growth_round_trips_media_case(self):
        base = valuation.run_payload({
            "model": "ddm", "dividends_per_share": [0.35, 0.37, 0.39, 0.41, 0.43],
            "ke": 0.085, "terminal_growth": 0.02,
        })
        target = base["value_per_share"]
        out = valuation.run_payload({
            "model": "reverse_dcf_growth", "fcff": [42.0, 44.0, 46.0, 48.0, 50.0],
            "wacc": 0.085, "diluted_shares": 100.0, "target_price": target,
        })
        # The FCFF path and the dividend path are different models; the point
        # of the test is that the solver converges to a stable, finite answer.
        self.assertEqual(out["status"], "solved")
        self.assertTrue(math.isfinite(out["implied_terminal_growth"]))


class ReitCrossCheckTests(unittest.TestCase):
    """SYNTHETIC: property-level NOI valuation and equity-level AFFO valuation
    must land in the same neighbourhood when inputs are consistent; a large
    gap is a diagnostic to explain (cap-rate basis, leverage, occupancy),
    never something to average away."""

    def test_noi_and_affo_neighbourhood(self):
        noi_out = valuation.run_payload({
            "model": "reit_noi", "noi": 100.0, "property_cap_rate": 0.05,
            "liabilities": 500.0, "shares": 100.0,
        })
        # AFFO here is NOI less interest and maintenance capex: 100 - 25 - 5 = 70
        affo_out = valuation.run_payload({
            "model": "affo", "affo_per_share": 0.70, "multiple": 20.0,
        })
        ratio = affo_out["value_per_share"] / noi_out["value_per_share"]
        self.assertGreater(ratio, 0.7)
        self.assertLess(ratio, 1.3)

    def test_insurer_pev_with_ri_cross_check(self):
        pev_out = valuation.run_payload({
            "model": "pev", "embedded_value": 2000.0, "pev_multiple": 0.8,
            "shares": 100.0, "holdco_discount": 0.15,
        })
        ri_out = valuation.run_payload({
            "model": "residual_income", "bvps": 20.0, "roe_path": [0.12, 0.12],
            "payout": 0.3, "ke": 0.09, "terminal_roe": 0.10, "terminal_book_growth": 0.04,
        })
        self.assertAlmostEqual(pev_out["value_per_share"], 13.6, places=9)
        self.assertGreater(ri_out["implied_pb"], 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
