import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import snapshot


def record(**overrides):
    base = {
        "value": 100.0,
        "unit": "CNY million",
        "currency": "CNY",
        "period": "2026H1",
        "basis": "consolidated",
        "status": "fact",
        "source_type": "annual_report",
        "source": "2026 interim report",
        "as_of": "2026-06-30",
    }
    base.update(overrides)
    return base


def valid_snapshot():
    return {
        "snapshot_version": 1,
        "identifier": {
            "ticker": "000000.SZ", "name": "Example Co", "market": "A",
            "currency": "CNY", "unit": "million",
        },
        "period": {"label": "2026H1", "end": "2026-06-30"},
        "retrieved_at": "2026-10-22",
        "price": {
            "value": 18.4, "currency": "CNY", "as_of": "2026-10-21", "source": "exchange quote",
        },
        "data": {"revenue": record()},
    }


class SnapshotCheckTests(unittest.TestCase):
    def test_valid_snapshot_passes(self):
        errors, warnings, facts = snapshot.check(valid_snapshot())
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])
        self.assertEqual(facts["ticker"], "000000.SZ")
        self.assertEqual(facts["fields"], 1)
        self.assertEqual(facts["price_age_days"], 1)

    def test_requires_snapshot_version(self):
        payload = valid_snapshot()
        payload["snapshot_version"] = 2
        errors, _, _ = snapshot.check(payload)
        self.assertTrue(any("snapshot_version" in e for e in errors))

    def test_requires_identifier_fields(self):
        payload = valid_snapshot()
        del payload["identifier"]["market"]
        errors, _, _ = snapshot.check(payload)
        self.assertTrue(any("identifier.market" in e for e in errors))

    def test_requires_period_and_iso_period_end(self):
        payload = valid_snapshot()
        payload["period"]["end"] = "2026/06/30"
        errors, _, _ = snapshot.check(payload)
        self.assertTrue(any("period.end" in e for e in errors))

    def test_retrieved_at_cannot_precede_period_end(self):
        payload = valid_snapshot()
        payload["retrieved_at"] = "2026-06-01"
        errors, _, _ = snapshot.check(payload)
        self.assertTrue(any("retrieved_at" in e for e in errors))

    def test_price_requires_source_and_positive_value(self):
        payload = valid_snapshot()
        payload["price"]["source"] = ""
        payload["price"]["value"] = 0
        errors, _, _ = snapshot.check(payload)
        self.assertTrue(any("price.source" in e for e in errors))
        self.assertTrue(any("price.value" in e for e in errors))

    def test_price_as_of_after_retrieval_is_error(self):
        payload = valid_snapshot()
        payload["price"]["as_of"] = "2026-10-30"
        errors, _, _ = snapshot.check(payload)
        self.assertTrue(any("price.as_of" in e for e in errors))

    def test_stale_price_warns(self):
        payload = valid_snapshot()
        payload["price"]["as_of"] = "2026-09-01"
        errors, warnings, facts = snapshot.check(payload)
        self.assertEqual(errors, [])
        self.assertTrue(any("days old" in w for w in warnings))
        self.assertGreater(facts["price_age_days"], 7)

    def test_fresh_risk_free_rate_passes(self):
        payload = valid_snapshot()
        payload["data"]["risk_free_10y_cgb"] = record(
            value=0.01627,
            unit="ratio",
            currency=None,
            status="fact",
            source_type="market_data",
            source="interbank 10Y CGB 26附息国债16 yield to maturity 1.627%",
            as_of="2026-10-22",
        )
        errors, warnings, _ = snapshot.check(payload)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_stale_risk_free_rate_warns(self):
        payload = valid_snapshot()
        payload["data"]["risk_free_10y_cgb"] = record(
            value=0.021,
            unit="ratio",
            currency=None,
            status="fact",
            source_type="market_data",
            source="CN 10Y CGB yield (stale reuse)",
            as_of="2026-06-30",
        )
        errors, warnings, _ = snapshot.check(payload)
        self.assertEqual(errors, [])
        self.assertTrue(any("risk_free" in w and "days old" in w for w in warnings))

    def test_rate_freshness_threshold_is_configurable(self):
        payload = valid_snapshot()
        payload["data"]["fx_rate"] = record(
            value=6.67,
            unit="ratio",
            currency=None,
            status="fact",
            source_type="market_data",
            source="CFETS mid rate",
            as_of="2026-10-18",
        )
        # 4 days old: over the default 3-day threshold, fine at 7 days
        _, warnings_default, _ = snapshot.check(payload)
        self.assertTrue(any("fx_rate" in w for w in warnings_default))
        _, warnings_loose, _ = snapshot.check(payload, max_market_age_days=7)
        self.assertFalse(any("fx_rate" in w for w in warnings_loose))

    def test_non_rate_fields_are_not_gated_by_market_age(self):
        payload = valid_snapshot()
        payload["data"]["beta"] = record(
            value=1.0,
            unit="ratio",
            currency=None,
            status="assumption",
            source_type="assumption",
            rationale="windowed estimate; freshness handled by ke_wacc.py flags",
            as_of="2026-06-30",
        )
        errors, warnings, _ = snapshot.check(payload)
        self.assertEqual(errors, [])
        self.assertFalse(any("beta" in w and "days old" in w for w in warnings))

    def test_non_monetary_units_do_not_require_a_currency(self):
        payload = valid_snapshot()
        payload["data"]["pev"] = {
            "value": 0.5, "unit": "x", "period": "2026H1", "basis": "market cap / EV",
            "status": "fact", "source_type": "derived", "source": "computed", "as_of": "2026-06-30",
        }
        errors, warnings, _ = snapshot.check(payload)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_monetary_units_still_require_a_currency(self):
        payload = valid_snapshot()
        broken = record()
        del broken["currency"]
        payload["data"]["revenue"] = broken
        errors, _, _ = snapshot.check(payload)
        self.assertTrue(any("currency is missing" in e for e in errors))

    def test_price_predating_period_end_warns(self):
        payload = valid_snapshot()
        payload["price"]["as_of"] = "2026-06-01"
        payload["retrieved_at"] = "2026-07-01"
        _, warnings, _ = snapshot.check(payload)
        self.assertTrue(any("predates period.end" in w for w in warnings))

    def test_currency_mismatch_warns(self):
        payload = valid_snapshot()
        payload["data"]["revenue"] = record(currency="HKD", unit="HKD million")
        errors, warnings, _ = snapshot.check(payload)
        self.assertEqual(errors, [])
        self.assertTrue(any("reporting currency" in w for w in warnings))

    def test_unit_prefix_mismatch_warns(self):
        payload = valid_snapshot()
        payload["data"]["revenue"] = record(unit="million CNY")
        _, warnings, _ = snapshot.check(payload)
        self.assertTrue(any("does not start with the record currency" in w for w in warnings))

    def test_fact_without_source_is_error(self):
        payload = valid_snapshot()
        payload["data"]["revenue"] = record(source="")
        errors, _, _ = snapshot.check(payload)
        self.assertTrue(any("source is missing" in e for e in errors))

    def test_calculated_needs_formula_or_input_refs(self):
        payload = valid_snapshot()
        payload["data"]["revenue"] = record(status="calculated")
        errors, _, _ = snapshot.check(payload)
        self.assertTrue(any("neither formula nor input_refs" in e for e in errors))

    def test_calculated_with_formula_passes(self):
        payload = valid_snapshot()
        payload["data"]["revenue"] = record(status="calculated", formula="a - b", input_refs=["a", "b"])
        errors, _, _ = snapshot.check(payload)
        self.assertEqual(errors, [])

    def test_assumption_needs_rationale(self):
        payload = valid_snapshot()
        payload["data"]["revenue"] = record(status="assumption")
        errors, _, _ = snapshot.check(payload)
        self.assertTrue(any("rationale" in e for e in errors))

    def test_unknown_cannot_carry_a_value(self):
        payload = valid_snapshot()
        payload["data"]["revenue"] = record(status="unknown")
        errors, _, _ = snapshot.check(payload)
        self.assertTrue(any("marked unknown but still carries a value" in e for e in errors))

    def test_unknown_without_value_warns_and_is_listed(self):
        payload = valid_snapshot()
        payload["data"]["revenue"] = {"unit": "CNY million", "currency": "CNY", "period": "2026H1",
                                      "basis": "not disclosed", "status": "unknown", "as_of": "2026-06-30"}
        errors, warnings, facts = snapshot.check(payload)
        self.assertEqual(errors, [])
        self.assertTrue(any("unknown" in w for w in warnings))
        self.assertEqual(facts["unknown_fields"], ["revenue"])

    def test_published_after_retrieval_is_error(self):
        payload = valid_snapshot()
        payload["data"]["revenue"] = record(published_at="2026-11-01")
        errors, _, _ = snapshot.check(payload)
        self.assertTrue(any("published after retrieved_at" in e for e in errors))

    def test_published_before_as_of_warns(self):
        payload = valid_snapshot()
        payload["data"]["revenue"] = record(published_at="2026-05-01")
        _, warnings, _ = snapshot.check(payload)
        self.assertTrue(any("earlier than as_of" in w for w in warnings))

    def test_published_after_as_of_is_normal(self):
        payload = valid_snapshot()
        payload["data"]["revenue"] = record(published_at="2026-08-28")
        errors, warnings, _ = snapshot.check(payload)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_placeholder_text_warns(self):
        payload = valid_snapshot()
        payload["data"]["revenue"] = record(source="TODO: find filing")
        _, warnings, _ = snapshot.check(payload)
        self.assertTrue(any("placeholder" in w for w in warnings))

    def test_illustrative_snapshot_warns(self):
        payload = valid_snapshot()
        payload["illustrative"] = True
        _, warnings, _ = snapshot.check(payload)
        self.assertTrue(any("illustrative" in w for w in warnings))

    def test_empty_data_is_error(self):
        payload = valid_snapshot()
        payload["data"] = {}
        errors, _, _ = snapshot.check(payload)
        self.assertTrue(any("data must be a non-empty object" in e for e in errors))


class SnapshotDiffTests(unittest.TestCase):
    def test_detects_value_change_with_unchanged_source(self):
        old = valid_snapshot()
        new = valid_snapshot()
        new["data"]["revenue"] = record(value=110.0)
        errors, warnings, result = snapshot.diff(old, new)
        self.assertEqual(errors, [])
        self.assertEqual(len(result["data"]["changed"]), 1)
        self.assertAlmostEqual(result["data"]["changed"][0]["change_pct"], 0.10)
        self.assertTrue(any("unexplained" in w for w in warnings))

    def test_detects_period_rollover(self):
        old = valid_snapshot()
        new = valid_snapshot()
        new["period"] = {"label": "2026Q3", "end": "2026-09-30"}
        new["retrieved_at"] = "2026-10-30"
        new["data"]["revenue"] = record(period="2026Q3", as_of="2026-09-30", published_at="2026-10-28")
        _, warnings, result = snapshot.diff(old, new)
        self.assertTrue(result["period_changed"])
        self.assertFalse(any("same reporting period" in w for w in warnings))

    def test_same_period_warns(self):
        old = valid_snapshot()
        new = valid_snapshot()
        new["price"]["value"] = 20.0
        _, warnings, result = snapshot.diff(old, new)
        self.assertFalse(result["period_changed"])
        self.assertTrue(any("same reporting period" in w for w in warnings))
        self.assertAlmostEqual(result["price"]["change_pct"], (20.0 - 18.4) / 18.4)

    def test_tracks_added_removed_and_resourced(self):
        old = valid_snapshot()
        old["data"]["operating_income"] = record(value=300.0)
        new = valid_snapshot()
        new["data"]["operating_income"] = record(value=300.0, source="2026 Q3 report", as_of="2026-09-30")
        new["data"]["capex"] = record(value=50.0)
        _, warnings, result = snapshot.diff(old, new)
        self.assertEqual(result["data"]["added"], ["capex"])
        self.assertEqual(result["data"]["removed"], [])
        self.assertEqual(result["data"]["resourced"], ["operating_income"])
        self.assertTrue(any("same value but its source" in w for w in warnings))

    def test_rejects_different_tickers(self):
        old = valid_snapshot()
        new = valid_snapshot()
        new["identifier"]["ticker"] = "600036.SH"
        errors, _, _ = snapshot.diff(old, new)
        self.assertTrue(any("tickers differ" in e for e in errors))

    def test_warns_on_status_becoming_unknown(self):
        old = valid_snapshot()
        new = valid_snapshot()
        new["data"]["revenue"] = {"unit": "CNY million", "currency": "CNY", "period": "2026H1",
                                  "basis": "not disclosed", "status": "unknown", "as_of": "2026-06-30"}
        _, warnings, result = snapshot.diff(old, new)
        self.assertEqual(result["data"]["changed"][0]["status_to"], "unknown")
        self.assertTrue(any("now unknown" in w for w in warnings))


class SnapshotCliTests(unittest.TestCase):
    def _write(self, payload):
        handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        with handle as fh:
            json.dump(payload, fh, ensure_ascii=False)
        return handle.name

    def test_cli_check_pass_and_fail(self):
        ok_path = self._write(valid_snapshot())
        bad = valid_snapshot()
        bad["price"]["value"] = -1
        bad_path = self._write(bad)
        self.assertEqual(snapshot.main(["snapshot.py", "check", ok_path]), 0)
        self.assertEqual(snapshot.main(["snapshot.py", "check", bad_path]), 1)
        Path(ok_path).unlink()
        Path(bad_path).unlink()

    def test_cli_usage_error(self):
        self.assertEqual(snapshot.main(["snapshot.py"]), 2)
        self.assertEqual(snapshot.main(["snapshot.py", "check"]), 2)

    def test_cli_diff(self):
        old_path = self._write(valid_snapshot())
        new = valid_snapshot()
        new["data"]["revenue"] = record(value=120.0)
        new_path = self._write(new)
        self.assertEqual(snapshot.main(["snapshot.py", "diff", old_path, new_path]), 0)
        Path(old_path).unlink()
        Path(new_path).unlink()


if __name__ == "__main__":
    unittest.main()
