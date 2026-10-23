"""Tests for the research-ledger provenance gate (scripts/audit_ledger.py).

Synthetic payloads only; no real securities data.
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import audit_ledger  # noqa: E402


def fact(name: str, **overrides):
    record = {
        "name": name,
        "value": 1280,
        "unit": "million CNY",
        "currency": "CNY",
        "period": "FY2025",
        "status": "fact",
        "source_type": "official_filing",
        "source": "annual report p.112",
        "as_of": "2026-10-23",
    }
    record.update(overrides)
    return record


class LedgerStructureTests(unittest.TestCase):
    def test_clean_ledger_passes(self):
        errors, warnings = audit_ledger.audit(
            {
                "security": {
                    "ticker": "EXAMPLE",
                    "market": "A-share",
                    "currency": "CNY",
                    "valuation_date": "2026-10-23",
                },
                "data": [fact("operating_cash_flow")],
            }
        )
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_top_level_must_be_object(self):
        errors, _ = audit_ledger.audit([1, 2, 3])
        self.assertTrue(any("object" in e for e in errors))

    def test_security_block_required(self):
        errors, _ = audit_ledger.audit({"data": [fact("x")]})
        self.assertTrue(any("security" in e for e in errors))

    def test_empty_data_array_rejected(self):
        errors, _ = audit_ledger.audit(
            {
                "security": {
                    "ticker": "E",
                    "market": "A-share",
                    "currency": "CNY",
                    "valuation_date": "2026-10-23",
                },
                "data": [],
            }
        )
        self.assertTrue(any("non-empty" in e for e in errors))


class StatusRuleTests(unittest.TestCase):
    def test_fact_requires_source_and_source_type(self):
        errors, _ = audit_ledger.audit(
            {"security": _sec(), "data": [fact("x", source="", source_type="")]}
        )
        self.assertTrue(any("source is missing" in e for e in errors))
        self.assertTrue(any("source_type" in e for e in errors))

    def test_calculated_requires_formula_or_input_refs(self):
        record = fact("x", status="calculated", formula=None)
        record.pop("formula", None)
        errors, _ = audit_ledger.audit({"security": _sec(), "data": [record]})
        self.assertTrue(any("formula" in e or "input_refs" in e for e in errors))

    def test_calculated_with_formula_passes(self):
        record = fact("x", status="calculated", formula="x = y / z", input_refs=["data[0]"])
        errors, _ = audit_ledger.audit({"security": _sec(), "data": [record]})
        self.assertEqual(errors, [])

    def test_assumption_requires_rationale(self):
        errors, _ = audit_ledger.audit(
            {"security": _sec(), "data": [fact("x", status="assumption", rationale="")]}
        )
        self.assertTrue(any("rationale" in e for e in errors))

    def test_unknown_may_omit_value_but_warns(self):
        record = fact("x", status="unknown")
        record.pop("value")
        errors, warnings = audit_ledger.audit({"security": _sec(), "data": [record]})
        self.assertEqual(errors, [])
        self.assertTrue(any("unknown" in w for w in warnings))

    def test_invalid_status_rejected(self):
        errors, _ = audit_ledger.audit(
            {"security": _sec(), "data": [fact("x", status="guess")]}
        )
        self.assertTrue(any("status must be" in e for e in errors))


class PlaceholderAndDateTests(unittest.TestCase):
    def test_placeholder_source_warns(self):
        record = fact("x", source="TODO: find the filing")
        _, warnings = audit_ledger.audit({"security": _sec(), "data": [record]})
        self.assertTrue(any("placeholder" in w for w in warnings))

    def test_placeholder_in_chinese_warns(self):
        record = fact("x", rationale="示例占位：需要论证")
        _, warnings = audit_ledger.audit({"security": _sec(), "data": [record]})
        self.assertTrue(any("placeholder" in w for w in warnings))

    def test_published_after_as_of_warns(self):
        record = fact("x", published_at="2026-12-01", as_of="2026-10-23")
        _, warnings = audit_ledger.audit({"security": _sec(), "data": [record]})
        self.assertTrue(any("published_at" in w for w in warnings))

    def test_non_string_dates_do_not_crash(self):
        record = fact("x", published_at=20260328, as_of=20261023)
        errors, _ = audit_ledger.audit({"security": _sec(), "data": [record]})
        self.assertEqual(errors, [])

    def test_duplicate_names_warn(self):
        errors, warnings = audit_ledger.audit(
            {"security": _sec(), "data": [fact("x"), fact("x", value=999)]}
        )
        self.assertEqual(errors, [])
        self.assertTrue(any("duplicates" in w for w in warnings))


class ExampleLedgerTests(unittest.TestCase):
    def test_bundled_example_audits_without_errors(self):
        path = ROOT / "examples" / "research-ledger.example.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        errors, warnings = audit_ledger.audit(payload)
        self.assertEqual(errors, [])
        # the example intentionally ships placeholder text and an unknown record
        self.assertTrue(warnings)


def _sec():
    return {
        "ticker": "EXAMPLE",
        "market": "A-share",
        "currency": "CNY",
        "valuation_date": "2026-10-23",
    }


if __name__ == "__main__":
    unittest.main()
