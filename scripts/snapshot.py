#!/usr/bin/env python3
"""Validate and diff valuation input snapshots.

A snapshot is a frozen, dated set of sourcing-ready inputs for one company and
one reporting period (format: references/snapshot-format.md). Freezing the
inputs is what makes a re-run comparable: the next valuation reads a new
snapshot and diffs it against the old one, so a changed value can be traced to
a changed fact instead of a retyped assumption.

Commands:
  check <snapshot.json>            structural gate, same role as audit_ledger.py
  diff <old.json> <new.json>       what changed between two snapshots of a company

Both are structural checks. Neither proves a source is real or a figure correct.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

SNAPSHOT_VERSION = 1
REQUIRED_IDENTIFIER = ("ticker", "name", "market", "currency", "unit")
REQUIRED_RECORD = ("unit", "period", "basis", "status", "as_of")
ALLOWED_STATUS = {"fact", "calculated", "assumption", "unknown"}
NON_MONETARY_UNITS = {"x", "times", "ratio", "%", "n/a", "count", "years", "persons"}
_PLACEHOLDER_TOKENS = ("示例占位", "placeholder", "todo", "待补充", "example.com")
DEFAULT_MAX_PRICE_AGE_DAYS = 7
# Market quotes age differently from company facts: a risk-free rate is a
# valuation-date input, not a period fact. 3 days covers a weekend; longer
# gaps are a warning so the report must say which date the rate is from.
DEFAULT_MAX_MARKET_AGE_DAYS = 3
_MARKET_RATE_HINTS = ("risk_free", "cgb", "bond_yield", "fx_rate", "exchange_rate", "yield_")


def _parse_date(label: str, value: Any, errors: list[str]) -> date | None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{label} must be an ISO date string (YYYY-MM-DD)")
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        errors.append(f"{label} is not a valid ISO date: {value!r}")
        return None


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _check_record(
    name: str,
    record: Any,
    reporting_currency: str,
    retrieved_at: date | None,
    errors: list[str],
    warnings: list[str],
) -> None:
    prefix = f"data.{name}"
    if not isinstance(record, dict):
        errors.append(f"{prefix} must be an object")
        return
    status = record.get("status")
    if status not in ALLOWED_STATUS:
        errors.append(f"{prefix}.status must be one of {sorted(ALLOWED_STATUS)}")
    unit = record.get("unit")
    is_monetary = not (isinstance(unit, str) and unit.strip().lower() in NON_MONETARY_UNITS)
    for key in REQUIRED_RECORD:
        if key not in record or record[key] in (None, ""):
            errors.append(f"{prefix}.{key} is missing")
    if is_monetary and record.get("currency") in (None, ""):
        errors.append(f"{prefix}.currency is missing")
    value = record.get("value")
    if status == "unknown":
        if value not in (None, ""):
            errors.append(f"{prefix} is marked unknown but still carries a value; remove the value or change the status")
        warnings.append(f"{prefix} is unknown and must not feed a formal valuation calculation")
    elif not _is_number(value):
        errors.append(f"{prefix}.value must be numeric")
    if status in {"fact", "calculated"} and not record.get("source"):
        errors.append(f"{prefix}.source is missing; a fact or calculated figure must keep its source/formula")
    if status in {"fact", "calculated"} and not record.get("source_type"):
        errors.append(f"{prefix}.source_type is missing")
    if status == "calculated" and not (record.get("formula") or record.get("input_refs")):
        errors.append(f"{prefix} is calculated but provides neither formula nor input_refs; it cannot be recomputed")
    if status == "assumption" and not record.get("rationale"):
        errors.append(f"{prefix}.rationale is missing; an assumption must explain itself")

    currency = record.get("currency")
    if is_monetary:
        if isinstance(currency, str) and currency and currency != reporting_currency:
            warnings.append(
                f"{prefix}.currency {currency!r} differs from the reporting currency {reporting_currency!r}; "
                "record the FX rate and its as-of date before using it in a calculation"
            )
        if isinstance(unit, str) and isinstance(currency, str) and currency and not unit.startswith(currency):
            warnings.append(f"{prefix}.unit {unit!r} does not start with the record currency {currency!r}")

    as_of = record.get("as_of")
    published_at = record.get("published_at")
    if isinstance(published_at, str) and published_at and retrieved_at:
        pub_date = _parse_date(f"{prefix}.published_at", published_at, [])
        if pub_date and pub_date > retrieved_at:
            errors.append(f"{prefix} was published after retrieved_at; it cannot have been retrieved then")
    if isinstance(published_at, str) and published_at and isinstance(as_of, str) and as_of:
        pub_date = _parse_date(f"{prefix}.published_at", published_at, [])
        as_of_date = _parse_date(f"{prefix}.as_of", as_of, [])
        if pub_date and as_of_date and pub_date < as_of_date:
            warnings.append(
                f"{prefix}.published_at is earlier than as_of; as_of should be the date the figure describes "
                "(period end), and a document cannot precede the period it reports"
            )
    if isinstance(as_of, str) and as_of and retrieved_at:
        as_of_date = _parse_date(f"{prefix}.as_of", as_of, [])
        if as_of_date and as_of_date > retrieved_at:
            warnings.append(f"{prefix}.as_of is later than retrieved_at; confirm the date semantics")
    for field in ("source", "rationale", "note"):
        text = record.get(field)
        if isinstance(text, str) and any(token in text.lower() for token in _PLACEHOLDER_TOKENS):
            warnings.append(f"{prefix}.{field} still contains placeholder text; provenance is not complete")
            break


def _check_market_rate_age(
    name: str,
    record: Any,
    retrieved_at: date | None,
    max_age_days: int,
    warnings: list[str],
) -> None:
    """Rate-style market quotes must be as-of the valuation date.

    Applies to risk-free / CGB / FX fields by name. The risk-free rate feeds
    Ke one-for-one: a stale quote (e.g. reusing last year's 2.1% when today is
    1.63%) silently adds ~50bp to Ke and cuts the DCF value ~5%, and nothing
    else in the model would flag it. Beta and ERP are windowed estimates with
    their own provenance rules in ke_wacc.py and are deliberately not gated
    here. Warn, never error: a Monday valuation quoting Friday's close is
    normal.
    """
    if not isinstance(record, dict):
        return
    lowered = name.lower()
    if not any(hint in lowered for hint in _MARKET_RATE_HINTS):
        return
    as_of = _parse_date(f"data.{name}.as_of", record.get("as_of"), [])
    if not (as_of and retrieved_at):
        return
    age = (retrieved_at - as_of).days
    if age > max_age_days:
        warnings.append(
            f"data.{name} is {age} days old at retrieval (threshold {max_age_days}); "
            "a market rate must be quoted as-of the valuation date (10Y CGB yield to "
            "maturity for the risk-free rate), not a stale close"
        )


def check(
    payload: Any,
    *,
    max_price_age_days: int = DEFAULT_MAX_PRICE_AGE_DAYS,
    max_market_age_days: int = DEFAULT_MAX_MARKET_AGE_DAYS,
) -> tuple[list[str], list[str], dict[str, Any]]:
    """Return (errors, warnings, facts) for a snapshot payload."""
    errors: list[str] = []
    warnings: list[str] = []
    facts: dict[str, Any] = {}
    if not isinstance(payload, dict):
        return ["top-level JSON must be an object"], warnings, facts

    version = payload.get("snapshot_version")
    if version != SNAPSHOT_VERSION:
        errors.append(f"snapshot_version must be {SNAPSHOT_VERSION}")
    if payload.get("illustrative"):
        warnings.append("illustrative snapshot: it demonstrates the format and must not feed a formal valuation")

    identifier = payload.get("identifier")
    reporting_currency = ""
    if not isinstance(identifier, dict):
        errors.append("missing identifier object")
    else:
        for key in REQUIRED_IDENTIFIER:
            if not identifier.get(key):
                errors.append(f"identifier.{key} is missing")
        reporting_currency = str(identifier.get("currency") or "")
        facts["ticker"] = identifier.get("ticker")

    period = payload.get("period")
    period_end: date | None = None
    if not isinstance(period, dict):
        errors.append("missing period object")
    else:
        for key in ("label", "end"):
            if not period.get(key):
                errors.append(f"period.{key} is missing")
        period_end = _parse_date("period.end", period.get("end"), errors)
        facts["period"] = period.get("label")

    retrieved_at = _parse_date("retrieved_at", payload.get("retrieved_at"), errors)
    if retrieved_at and period_end and retrieved_at < period_end:
        errors.append("retrieved_at is earlier than period.end; the report cannot precede its period end")
    if retrieved_at and period_end:
        facts["data_age_days"] = (retrieved_at - period_end).days

    price = payload.get("price")
    if not isinstance(price, dict):
        errors.append("missing price object")
    else:
        for key in ("value", "currency", "as_of", "source"):
            if price.get(key) in (None, ""):
                errors.append(f"price.{key} is missing")
        if "value" in price and not _is_number(price.get("value")):
            errors.append("price.value must be numeric")
        elif _is_number(price.get("value")) and price["value"] <= 0:
            errors.append("price.value must be > 0")
        if reporting_currency and price.get("currency") and price.get("currency") != reporting_currency:
            warnings.append(
                f"price.currency {price.get('currency')!r} differs from the reporting currency "
                f"{reporting_currency!r}; record the FX rate used for per-share comparisons"
            )
        price_as_of = _parse_date("price.as_of", price.get("as_of"), errors)
        if price_as_of and retrieved_at:
            age = (retrieved_at - price_as_of).days
            facts["price_age_days"] = age
            if age < 0:
                errors.append("price.as_of is later than retrieved_at")
            elif age > max_price_age_days:
                warnings.append(
                    f"price is {age} days old at retrieval (threshold {max_price_age_days}); "
                    "refresh it before using the snapshot for a valuation verdict"
                )
        if price_as_of and period_end and price_as_of < period_end:
            warnings.append("price.as_of predates period.end; the price and the fundamentals use different information windows")

    records = payload.get("data")
    if not isinstance(records, dict) or not records:
        errors.append("data must be a non-empty object keyed by field name")
        return errors, warnings, facts
    for name, record in records.items():
        _check_record(str(name), record, reporting_currency, retrieved_at, errors, warnings)
        _check_market_rate_age(str(name), record, retrieved_at, max_market_age_days, warnings)
    facts["fields"] = len(records)
    facts["unknown_fields"] = sorted(
        str(n) for n, r in records.items() if isinstance(r, dict) and r.get("status") == "unknown"
    )
    return errors, warnings, facts


def _changed_fields(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    old_data = old.get("data") if isinstance(old.get("data"), dict) else {}
    new_data = new.get("data") if isinstance(new.get("data"), dict) else {}
    added = sorted(k for k in new_data if k not in old_data)
    removed = sorted(k for k in old_data if k not in new_data)
    changed: list[dict[str, Any]] = []
    resourced: list[str] = []
    unchanged = 0
    for name in sorted(set(old_data) & set(new_data)):
        before, after = old_data[name], new_data[name]
        before = before if isinstance(before, dict) else {}
        after = after if isinstance(after, dict) else {}
        before_value, after_value = before.get("value"), after.get("value")
        if before_value == after_value:
            unchanged += 1
            if before.get("source") != after.get("source") or before.get("as_of") != after.get("as_of"):
                resourced.append(name)
            continue
        delta = None
        if _is_number(before_value) and _is_number(after_value) and before_value != 0:
            delta = (after_value - before_value) / abs(before_value)
        changed.append(
            {
                "field": name,
                "from": before_value,
                "to": after_value,
                "change_pct": delta,
                "status_from": before.get("status"),
                "status_to": after.get("status"),
                "as_of_from": before.get("as_of"),
                "as_of_to": after.get("as_of"),
                "source_from": before.get("source"),
                "source_to": after.get("source"),
            }
        )
    return {"added": added, "removed": removed, "changed": changed, "resourced": resourced, "unchanged": unchanged}


def diff(old: Any, new: Any) -> tuple[list[str], list[str], dict[str, Any]]:
    """Compare two snapshots of the same company."""
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(old, dict) or not isinstance(new, dict):
        return ["both snapshots must be JSON objects"], warnings, {}

    old_id = old.get("identifier") if isinstance(old.get("identifier"), dict) else {}
    new_id = new.get("identifier") if isinstance(new.get("identifier"), dict) else {}
    if old_id.get("ticker") != new_id.get("ticker"):
        errors.append(
            f"tickers differ ({old_id.get('ticker')!r} vs {new_id.get('ticker')!r}); diff only snapshots of the same company"
        )
    if old_id.get("currency") != new_id.get("currency"):
        warnings.append("reporting currency changed between snapshots; do not compare values without an FX basis")
    if old_id.get("unit") != new_id.get("unit"):
        warnings.append("reporting unit changed between snapshots (e.g. million -> billion); restate before comparing")

    old_period = old.get("period") if isinstance(old.get("period"), dict) else {}
    new_period = new.get("period") if isinstance(new.get("period"), dict) else {}
    period_changed = old_period.get("end") != new_period.get("end")
    if not period_changed:
        warnings.append(
            "both snapshots cover the same reporting period; only price and assumption changes can be genuine, "
            "any changed fundamental means a figure was re-sourced or corrected"
        )

    old_price = old.get("price") if isinstance(old.get("price"), dict) else {}
    new_price = new.get("price") if isinstance(new.get("price"), dict) else {}
    price_from, price_to = old_price.get("value"), new_price.get("value")
    price_change = None
    if _is_number(price_from) and _is_number(price_to) and price_from != 0:
        price_change = (price_to - price_from) / price_from

    fields = _changed_fields(old, new)
    for item in fields["changed"]:
        if item["source_from"] == item["source_to"] and item["as_of_from"] == item["as_of_to"]:
            warnings.append(
                f"data.{item['field']} changed but the source and as_of did not; "
                "the change is unexplained by a new disclosure - check for a typo or a re-read figure"
            )
        if item["status_to"] == "unknown":
            warnings.append(f"data.{item['field']} is now unknown; it cannot feed a formal calculation")
    for name in fields["resourced"]:
        warnings.append(
            f"data.{name} keeps the same value but its source or as_of changed; "
            "confirm the figure is not being back-filled from the new document"
        )

    return errors, warnings, {
        "ticker": new_id.get("ticker") or old_id.get("ticker"),
        "from": {"period": old_period.get("label"), "retrieved_at": old.get("retrieved_at")},
        "to": {"period": new_period.get("label"), "retrieved_at": new.get("retrieved_at")},
        "period_changed": period_changed,
        "price": {"from": price_from, "to": price_to, "change_pct": price_change},
        "data": fields,
    }


def _load(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] not in ("check", "diff"):
        print("usage: python scripts/snapshot.py check <snapshot.json> [--max-price-age-days N]\n"
              "       python scripts/snapshot.py diff <old.json> <new.json>", file=sys.stderr)
        return 2
    command = argv[1]
    try:
        if command == "check":
            if len(argv) < 3:
                print("usage: python scripts/snapshot.py check <snapshot.json> [--max-price-age-days N]", file=sys.stderr)
                return 2
            max_age = DEFAULT_MAX_PRICE_AGE_DAYS
            if "--max-price-age-days" in argv:
                idx = argv.index("--max-price-age-days")
                max_age = int(argv[idx + 1])
            errors, warnings, facts = check(_load(argv[2]), max_price_age_days=max_age)
            print(json.dumps({
                "status": "fail" if errors else ("pass_with_warnings" if warnings else "pass"),
                "errors": errors,
                "warnings": warnings,
                "facts": facts,
                "note": "Structural check only: passing does not prove a source is real or a figure accurate.",
            }, ensure_ascii=False, indent=2))
            return 1 if errors else 0
        if len(argv) < 4:
            print("usage: python scripts/snapshot.py diff <old.json> <new.json>", file=sys.stderr)
            return 2
        errors, warnings, result = diff(_load(argv[2]), _load(argv[3]))
        result["status"] = "fail" if errors else ("pass_with_warnings" if warnings else "pass")
        result["errors"] = errors
        result["warnings"] = warnings
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if errors else 0
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
