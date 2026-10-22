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


if __name__ == "__main__":
    unittest.main(verbosity=2)
