#!/usr/bin/env python3
"""Audit a valuation research ledger for provenance completeness.

A research ledger is the structured record of every material input used in a
valuation (see references/china-market.md). This script is an executable
gate: it checks that each record carries the minimum metadata, that facts
and calculated figures keep their sources, that assumptions state their
rationale, and that no placeholder text is left behind.

It is a structural check only. It does not prove that a source is real or
that a number is correct - a ledger that passes here can still be wrong.

Adapted from the audit_data.py gate in the cn-hk-valuation-pro variant of
this project (same upstream lineage).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REQUIRED_ALL = ("name", "value", "unit", "currency", "period", "status", "as_of")
ALLOWED_STATUS = {"fact", "calculated", "assumption", "unknown"}
_PLACEHOLDER_TOKENS = ("示例占位", "placeholder", "todo", "待补充", "example.com")


def audit(payload: Any) -> tuple[list[str], list[str]]:
    """Return (errors, warnings) for a research-ledger payload."""
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(payload, dict):
        return ["top-level JSON must be an object"], warnings

    security = payload.get("security")
    if not isinstance(security, dict):
        errors.append("missing security object")
    else:
        for key in ("ticker", "market", "currency", "valuation_date"):
            if not security.get(key):
                errors.append(f"security.{key} is missing")

    records = payload.get("data")
    if not isinstance(records, list) or not records:
        errors.append("data must be a non-empty array")
        return errors, warnings

    seen_names: set[str] = set()
    for i, record in enumerate(records):
        prefix = f"data[{i}]"
        if not isinstance(record, dict):
            errors.append(f"{prefix} must be an object")
            continue
        status = record.get("status")
        for key in REQUIRED_ALL:
            if key == "value" and status == "unknown":
                continue
            if key not in record or record[key] in (None, ""):
                errors.append(f"{prefix}.{key} is missing")
        if status not in ALLOWED_STATUS:
            errors.append(f"{prefix}.status must be one of {sorted(ALLOWED_STATUS)}")
        if status in {"fact", "calculated"}:
            if not record.get("source"):
                errors.append(
                    f"{prefix}.source is missing; a fact or calculated figure must keep its source/formula"
                )
            if not record.get("source_type"):
                errors.append(f"{prefix}.source_type is missing")
        if status == "calculated" and not (record.get("formula") or record.get("input_refs")):
            errors.append(
                f"{prefix} is calculated but provides neither formula nor input_refs; it cannot be recomputed"
            )
        if status == "assumption" and not record.get("rationale"):
            errors.append(f"{prefix}.rationale is missing; an assumption must explain itself")
        if status == "unknown":
            warnings.append(f"{prefix} is marked unknown and must not feed a formal valuation calculation")
        for field in ("source", "rationale"):
            value = record.get(field)
            if isinstance(value, str) and any(
                token in value.lower() for token in _PLACEHOLDER_TOKENS
            ):
                warnings.append(f"{prefix}.{field} still contains placeholder text; provenance is not complete")
                break
        published_at = record.get("published_at")
        as_of = record.get("as_of")
        if (
            isinstance(published_at, str)
            and isinstance(as_of, str)
            and published_at > as_of
        ):
            warnings.append(f"{prefix} published_at is later than as_of; confirm the date semantics")
        name = record.get("name")
        if isinstance(name, str):
            if name in seen_names:
                warnings.append(f"{prefix} duplicates the record name {name!r}; confirm both entries are intended")
            seen_names.add(name)
    return errors, warnings


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python scripts/audit_ledger.py <research-ledger.json>", file=sys.stderr)
        return 2
    try:
        payload = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
        errors, warnings = audit(payload)
        result = {
            "status": "fail" if errors else ("pass_with_warnings" if warnings else "pass"),
            "errors": errors,
            "warnings": warnings,
            "note": (
                "Structural check only: passing does not prove a source is real or a figure accurate."
            ),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if errors else 0
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
