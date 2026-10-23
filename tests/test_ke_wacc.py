"""Tests for the auditable Ke/WACC estimation module.

All inputs are synthetic. They test formula arithmetic, provenance
enforcement and refusal behaviour - not any real company's cost of capital.
"""
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import ke_wacc


class CapmKeTests(unittest.TestCase):
    def test_basic_math(self):
        out = ke_wacc.capm_ke({
            "risk_free_rate": 0.02, "beta": 1.0, "equity_risk_premium": 0.06,
        })
        self.assertAlmostEqual(out["ke"], 0.08, places=12)
        self.assertAlmostEqual(out["components"]["beta_x_equity_risk_premium"], 0.06, places=12)

    def test_full_formula_with_adjustments(self):
        out = ke_wacc.capm_ke({
            "risk_free_rate": 0.02, "beta": 1.2, "equity_risk_premium": 0.06,
            "country_risk_premium": 0.005, "country_risk_premium_rationale": "sovereign spread x lambda",
            "size_premium": 0.01, "size_premium_rationale": "small-cap premium per documented study",
            "company_specific_premium": 0.005,
            "company_specific_premium_rationale": "customer concentration",
        })
        expected = 0.02 + 1.2 * 0.06 + 0.005 + 0.01 + 0.005
        self.assertAlmostEqual(out["ke"], expected, places=12)

    def test_dict_input_without_source_raises(self):
        with self.assertRaises(ValueError):
            ke_wacc.capm_ke({"risk_free_rate": {"value": 0.02},
                             "beta": 1.0, "equity_risk_premium": 0.06})

    def test_dict_input_without_value_raises(self):
        with self.assertRaises(ValueError):
            ke_wacc.capm_ke({"risk_free_rate": {"source": "SSE"},
                             "beta": 1.0, "equity_risk_premium": 0.06})

    def test_bare_number_warns_missing_provenance(self):
        out = ke_wacc.capm_ke({"risk_free_rate": 0.02, "beta": 1.0,
                               "equity_risk_premium": 0.06})
        self.assertTrue(any("provenance" in w for w in out["warnings"]))

    def test_dict_without_as_of_warns(self):
        out = ke_wacc.capm_ke({"risk_free_rate": {"value": 0.02, "source": "SSE"},
                               "beta": 1.0, "equity_risk_premium": 0.06})
        self.assertTrue(any("as-of" in w for w in out["warnings"]))

    def test_country_risk_without_rationale_raises(self):
        with self.assertRaises(ValueError):
            ke_wacc.capm_ke({"risk_free_rate": 0.02, "beta": 1.0,
                             "equity_risk_premium": 0.06, "country_risk_premium": 0.01})

    def test_country_risk_double_count_warning(self):
        out = ke_wacc.capm_ke({
            "risk_free_rate": 0.02, "beta": 1.0, "equity_risk_premium": 0.06,
            "country_risk_premium": 0.01, "country_risk_premium_rationale": "sovereign spread",
            "erp_includes_country_risk": True,
        })
        self.assertTrue(any("double count" in w for w in out["warnings"]))

    def test_beta_reliability_warnings(self):
        out = ke_wacc.capm_ke({
            "risk_free_rate": 0.02,
            "beta": {"value": 0.05, "source": "exchange", "as_of": "2026-10-01",
                     "r_squared": 0.1, "standard_error": 0.3},
            "equity_risk_premium": 0.06,
        })
        joined = " | ".join(out["warnings"])
        self.assertIn("r_squared", joined)
        self.assertIn("standard_error", joined)
        self.assertIn("near-zero beta", joined)

    def test_missing_required_input_raises(self):
        with self.assertRaises(ValueError):
            ke_wacc.capm_ke({"risk_free_rate": 0.02, "beta": 1.0})

    def test_negative_ke_warns(self):
        out = ke_wacc.capm_ke({"risk_free_rate": -0.05, "beta": 0.5,
                               "equity_risk_premium": 0.02})
        self.assertLess(out["ke"], 0)
        self.assertTrue(any("not positive" in w for w in out["warnings"]))


class BuildUpTests(unittest.TestCase):
    def test_math(self):
        out = ke_wacc.build_up_ke({
            "risk_free_rate": 0.02, "equity_risk_premium": 0.06,
            "size_premium": 0.01, "size_premium_rationale": "documented size study",
            "industry_premium": 0.005, "industry_premium_rationale": "sector risk",
        })
        self.assertAlmostEqual(out["ke"], 0.095, places=12)

    def test_industry_premium_without_rationale_raises(self):
        with self.assertRaises(ValueError):
            ke_wacc.build_up_ke({"risk_free_rate": 0.02, "equity_risk_premium": 0.06,
                                 "industry_premium": 0.01})


class BetaTests(unittest.TestCase):
    def test_unlever_relever_round_trip(self):
        bl, de, t = 1.3, 0.5, 0.25
        ba = ke_wacc.unlever_beta(bl, de, t)["beta_asset"]
        back = ke_wacc.relever_beta(ba, de, t)["beta_levered"]
        self.assertAlmostEqual(back, bl, places=12)

    def test_unlever_math(self):
        out = ke_wacc.unlever_beta(1.2, 0.5, 0.25)
        self.assertAlmostEqual(out["beta_asset"], 1.2 / (1 + 0.75 * 0.5), places=12)

    def test_unlever_rejects_bad_tax(self):
        with self.assertRaises(ValueError):
            ke_wacc.unlever_beta(1.2, 0.5, 1.5)
        with self.assertRaises(ValueError):
            ke_wacc.unlever_beta(1.2, -0.1, 0.25)

    def test_bottom_up_math(self):
        out = ke_wacc.bottom_up_beta({
            "comparables": [
                {"name": "A", "beta_levered": 1.0, "debt_to_equity": 0.0, "tax_rate": 0.25, "weight": 2.0},
                {"name": "B", "beta_levered": 1.5, "debt_to_equity": 1.0, "tax_rate": 0.25, "weight": 1.0},
            ],
            "target": {"tax_rate": 0.25, "debt_to_equity": 0.5},
        })
        ba_a = 1.0
        ba_b = 1.5 / (1 + 0.75 * 1.0)
        expected_asset = (2.0 * ba_a + 1.0 * ba_b) / 3.0
        self.assertAlmostEqual(out["beta_asset"], expected_asset, places=12)
        self.assertAlmostEqual(out["beta_levered_at_target"],
                               expected_asset * (1 + 0.75 * 0.5), places=12)
        self.assertAlmostEqual(out["comparables"][0]["normalized_weight"], 2.0 / 3.0, places=12)

    def test_bottom_up_equal_weights_default(self):
        out = ke_wacc.bottom_up_beta({
            "comparables": [
                {"name": "A", "beta_levered": 1.0, "debt_to_equity": 0.0, "tax_rate": 0.25},
                {"name": "B", "beta_levered": 1.0, "debt_to_equity": 0.0, "tax_rate": 0.25},
            ],
            "target": {"tax_rate": 0.25, "debt_to_equity": 0.0},
        })
        self.assertAlmostEqual(out["beta_asset"], 1.0, places=12)

    def test_bottom_up_rejects_zero_and_negative_weights(self):
        with self.assertRaises(ValueError):
            ke_wacc.bottom_up_beta({
                "comparables": [
                    {"name": "A", "beta_levered": 1.0, "debt_to_equity": 0.0, "tax_rate": 0.25, "weight": 0.0},
                ],
                "target": {"tax_rate": 0.25, "debt_to_equity": 0.0},
            })
        with self.assertRaises(ValueError):
            ke_wacc.bottom_up_beta({
                "comparables": [
                    {"name": "A", "beta_levered": 1.0, "debt_to_equity": 0.0, "tax_rate": 0.25, "weight": -1.0},
                ],
                "target": {"tax_rate": 0.25, "debt_to_equity": 0.0},
            })


class WaccTests(unittest.TestCase):
    def test_math(self):
        out = ke_wacc.wacc({
            "cost_of_equity": 0.10, "cost_of_debt": 0.05, "tax_rate": 0.25,
            "weight_equity": 0.7, "weight_debt": 0.3,
        })
        self.assertAlmostEqual(out["wacc"], 0.7 * 0.10 + 0.3 * 0.05 * 0.75, places=12)

    def test_weights_must_sum_to_one(self):
        with self.assertRaises(ValueError):
            ke_wacc.wacc({"cost_of_equity": 0.10, "cost_of_debt": 0.05,
                          "tax_rate": 0.25, "weight_equity": 0.7, "weight_debt": 0.4})

    def test_debt_basis_assumption_requires_rationale(self):
        with self.assertRaises(ValueError):
            ke_wacc.wacc({"cost_of_equity": 0.10,
                          "cost_of_debt": {"value": 0.05, "basis": "assumption",
                                           "source": "guess"},
                          "tax_rate": 0.25, "weight_equity": 0.7, "weight_debt": 0.3})

    def test_debt_basis_observed_requires_source(self):
        with self.assertRaises(ValueError):
            ke_wacc.wacc({"cost_of_equity": 0.10,
                          "cost_of_debt": {"value": 0.05, "basis": "observed"},
                          "tax_rate": 0.25, "weight_equity": 0.7, "weight_debt": 0.3})

    def test_debt_spread_build_up_computes_value(self):
        out = ke_wacc.wacc({
            "cost_of_equity": 0.10,
            "cost_of_debt": {"basis": "spread_build_up",
                             "risk_free_rate": {"value": 0.02, "source": "SSE"},
                             "credit_spread": {"value": 0.015, "source": "bond curve"}},
            "tax_rate": 0.25, "weight_equity": 0.7, "weight_debt": 0.3,
        })
        self.assertAlmostEqual(out["inputs"]["cost_of_debt"]["value"], 0.035, places=12)

    def test_bank_refuses_wacc(self):
        with self.assertRaises(ValueError):
            ke_wacc.wacc({"cost_of_equity": 0.10, "cost_of_debt": 0.05,
                          "tax_rate": 0.25, "weight_equity": 0.7, "weight_debt": 0.3,
                          "entity_type": "bank"})

    def test_bank_override_with_rationale_computes_and_warns(self):
        out = ke_wacc.wacc({"cost_of_equity": 0.10, "cost_of_debt": 0.05,
                            "tax_rate": 0.25, "weight_equity": 0.7, "weight_debt": 0.3,
                            "entity_type": "insurer",
                            "override_financial_wacc": True,
                            "override_rationale": "holding-company FCFF on consolidated non-insurance segments"})
        self.assertTrue(math.isfinite(out["wacc"]))
        self.assertTrue(any("override" in w for w in out["warnings"]))

    def test_book_weights_require_rationale(self):
        with self.assertRaises(ValueError):
            ke_wacc.wacc({"cost_of_equity": 0.10, "cost_of_debt": 0.05,
                          "tax_rate": 0.25, "weight_equity": 0.7, "weight_debt": 0.3,
                          "weight_basis": "book"})

    def test_bad_tax_rate_raises(self):
        with self.assertRaises(ValueError):
            ke_wacc.wacc({"cost_of_equity": 0.10, "cost_of_debt": 0.05,
                          "tax_rate": 1.5, "weight_equity": 0.7, "weight_debt": 0.3})


class KeScenarioTests(unittest.TestCase):
    def _inputs(self, bear_rationale="higher rate for stress", bull_rationale="lower rate for benign"):
        return {
            "bear": {"method": "capm",
                     "inputs": {"risk_free_rate": 0.02, "beta": 1.3, "equity_risk_premium": 0.07},
                     "rationale": bear_rationale},
            "base": {"method": "capm",
                     "inputs": {"risk_free_rate": 0.02, "beta": 1.0, "equity_risk_premium": 0.06},
                     "rationale": "central estimate"},
            "bull": {"method": "capm",
                     "inputs": {"risk_free_rate": 0.02, "beta": 0.9, "equity_risk_premium": 0.055},
                     "rationale": bull_rationale},
        }

    def test_math_and_spread(self):
        out = ke_wacc.ke_scenario(self._inputs())
        bear = 0.02 + 1.3 * 0.07
        bull = 0.02 + 0.9 * 0.055
        self.assertAlmostEqual(out["scenarios"]["bear"]["ke"], bear, places=12)
        self.assertAlmostEqual(out["scenarios"]["bull"]["ke"], bull, places=12)
        self.assertAlmostEqual(out["ke_spread_bull_minus_bear"], bull - bear, places=12)

    def test_missing_rationale_raises(self):
        inputs = self._inputs()
        del inputs["base"]["rationale"]
        with self.assertRaises(ValueError):
            ke_wacc.ke_scenario(inputs)

    def test_missing_scenario_raises(self):
        inputs = self._inputs()
        del inputs["bull"]
        with self.assertRaises(ValueError):
            ke_wacc.ke_scenario(inputs)

    def test_inverted_scenario_warns(self):
        inputs = self._inputs()
        inputs["bear"]["inputs"]["beta"] = 0.5   # bear Ke now below base
        out = ke_wacc.ke_scenario(inputs)
        self.assertTrue(any("bear Ke is below base Ke" in w for w in out["warnings"]))

    def test_build_up_scenario(self):
        inputs = self._inputs()
        inputs["base"] = {"method": "build_up",
                          "inputs": {"risk_free_rate": 0.02, "equity_risk_premium": 0.06,
                                     "size_premium": 0.01, "size_premium_rationale": "size study"},
                          "rationale": "build-up for unstable beta"}
        out = ke_wacc.ke_scenario(inputs)
        self.assertAlmostEqual(out["ke_base"], 0.09, places=12)


class AdditionalPremiumsTests(unittest.TestCase):
    """Generic {label, rate, rationale, source} premia on capm_ke / build_up_ke."""

    def test_entry_sums_into_ke(self):
        out = ke_wacc.capm_ke({
            "risk_free_rate": 0.02, "beta": 1.0, "equity_risk_premium": 0.06,
            "additional_premiums": [
                {"label": "governance discount", "rate": 0.005,
                 "rationale": "related-party dealings disclosed in FY2025 report",
                 "source": "annual report p.88"},
            ],
        })
        self.assertAlmostEqual(out["ke"], 0.085, places=12)
        self.assertEqual(out["components"]["additional_premiums_total"], 0.005)
        self.assertEqual(len(out["components"]["additional_premiums"]), 1)

    def test_build_up_accepts_additional_premiums(self):
        out = ke_wacc.build_up_ke({
            "risk_free_rate": 0.02, "equity_risk_premium": 0.06,
            "additional_premiums": [
                {"label": "liquidity", "rate": 0.01,
                 "rationale": "thin float, wide bid-ask", "source": "exchange data"},
            ],
        })
        self.assertAlmostEqual(out["ke"], 0.09, places=12)

    def test_missing_rationale_raises(self):
        with self.assertRaises(ValueError):
            ke_wacc.capm_ke({
                "risk_free_rate": 0.02, "beta": 1.0, "equity_risk_premium": 0.06,
                "additional_premiums": [
                    {"label": "governance", "rate": 0.005, "source": "x"}],
            })

    def test_missing_label_or_source_raises(self):
        for bad in ({"rate": 0.005, "rationale": "r", "source": "s"},
                    {"label": "l", "rate": 0.005, "rationale": "r"}):
            with self.assertRaises(ValueError):
                ke_wacc.capm_ke({
                    "risk_free_rate": 0.02, "beta": 1.0, "equity_risk_premium": 0.06,
                    "additional_premiums": [bad],
                })

    def test_non_numeric_rate_raises(self):
        with self.assertRaises(ValueError):
            ke_wacc.capm_ke({
                "risk_free_rate": 0.02, "beta": 1.0, "equity_risk_premium": 0.06,
                "additional_premiums": [
                    {"label": "l", "rate": "high", "rationale": "r", "source": "s"}],
            })

    def test_not_a_list_raises(self):
        with self.assertRaises(ValueError):
            ke_wacc.capm_ke({
                "risk_free_rate": 0.02, "beta": 1.0, "equity_risk_premium": 0.06,
                "additional_premiums": {"label": "l", "rate": 0.01},
            })

    def test_zero_rate_still_requires_provenance(self):
        with self.assertRaises(ValueError):
            ke_wacc.capm_ke({
                "risk_free_rate": 0.02, "beta": 1.0, "equity_risk_premium": 0.06,
                "additional_premiums": [
                    {"label": "l", "rate": 0.0, "rationale": "r", "source": ""}],
            })

    def test_stacking_warning_present(self):
        out = ke_wacc.capm_ke({
            "risk_free_rate": 0.02, "beta": 1.0, "equity_risk_premium": 0.06,
            "additional_premiums": [
                {"label": "governance", "rate": 0.005,
                 "rationale": "r", "source": "s"}],
        })
        self.assertTrue(any("double counting" in w for w in out["warnings"]))

    def test_empty_list_is_noop(self):
        out = ke_wacc.capm_ke({
            "risk_free_rate": 0.02, "beta": 1.0, "equity_risk_premium": 0.06,
            "additional_premiums": [],
        })
        self.assertAlmostEqual(out["ke"], 0.08, places=12)
        self.assertEqual(out["components"]["additional_premiums"], [])

    def test_source_accepts_provenance_dict(self):
        out = ke_wacc.capm_ke({
            "risk_free_rate": 0.02, "beta": 1.0, "equity_risk_premium": 0.06,
            "additional_premiums": [
                {"label": "l", "rate": 0.005, "rationale": "r",
                 "source": {"source": "annual report p.88", "as_of": "2026-10-22"}}],
        })
        self.assertEqual(out["components"]["additional_premiums"][0]["source"],
                         "annual report p.88")


class DispatchTests(unittest.TestCase):
    def test_run_payload_dispatch(self):
        out = ke_wacc.run_payload({"model": "capm_ke", "risk_free_rate": 0.02,
                                   "beta": 1.0, "equity_risk_premium": 0.06})
        self.assertEqual(out["model"], "capm_ke")
        self.assertAlmostEqual(out["ke"], 0.08, places=12)

    def test_run_payload_unknown_model_raises(self):
        with self.assertRaises(ValueError):
            ke_wacc.run_payload({"model": "guess_the_rate"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
