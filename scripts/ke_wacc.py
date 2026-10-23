#!/usr/bin/env python3
"""Auditable cost-of-capital estimation: Ke (CAPM / build-up) and WACC.

Python standard library only.

Design rules (these are the module's contract, not suggestions):
- Every rate input is either a bare number or a dict carrying provenance:
  {"value": ..., "source": "...", "as_of": "...", "currency": "...", ...}.
  Dict form MUST have a non-empty "source" or the call raises. Bare numbers
  are accepted but produce a provenance warning - the discipline is "record
  source and as-of date", not "guess quietly".
- There are no default rates anywhere in this module. No fixed 8% / 10% Ke,
  no default ERP, no assumed cost of debt. Missing or unverifiable inputs
  raise; a refusal is a valid output.
- Country-risk, size, industry and company-specific premia each require a
  written economic rationale. When the ERP is declared to already include
  country risk and a separate country-risk premium is also supplied, the
  module emits a double-counting warning.
- WACC is refused for banks / insurers / financial institutions unless a
  documented override is supplied: financial entities discount equity flows
  at Ke, not enterprise flows at WACC.
- Output always separates: value, formula, components, normalized inputs
  with provenance, intermediate results, and warnings. A downstream report
  must be reproducible from the returned dict alone.
"""
from __future__ import annotations

import math
from typing import Any, Sequence

# Reliability thresholds for beta statistics. These are documented
# conventions (advisory warnings only), not hard gates - see
# references/ke-wacc-estimation.md.
BETA_STD_ERROR_WARN = 0.20
BETA_R_SQUARED_WARN = 0.30
BETA_ABS_LOW_WARN = 0.20
BETA_ABS_HIGH_WARN = 2.00

FINANCIAL_ENTITY_TYPES = {"bank", "insurer", "financial", "financial_institution"}


def _finite(name: str, value: Any) -> float:
    try:
        x = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(x):
        raise ValueError(f"{name} must be finite")
    return x


def _required(inputs: dict[str, Any], key: str) -> Any:
    if key not in inputs or inputs[key] is None:
        raise ValueError(f"{key} is required")
    return inputs[key]


def _normalize_input(name: str, spec: Any, warnings: list[str]) -> tuple[float, dict[str, Any]]:
    """Accept a bare number or a provenance dict; return (value, metadata)."""
    if isinstance(spec, dict):
        if "value" not in spec or spec["value"] is None:
            raise ValueError(f"{name}: dict input must contain 'value'")
        value = _finite(name, spec["value"])
        source = spec.get("source")
        if not isinstance(source, str) or not source.strip():
            raise ValueError(f"{name}: dict input must contain a non-empty 'source'")
        meta = {k: v for k, v in spec.items() if k != "value"}
        if not isinstance(meta.get("as_of"), str) or not meta["as_of"].strip():
            warnings.append(f"{name}: no as-of date recorded; refresh discipline requires one")
        return value, meta
    value = _finite(name, spec)
    warnings.append(
        f"{name}: bare number without provenance; record source and as-of date in the report"
    )
    return value, {"source": None, "as_of": None}


def _rationale(name: str, spec: dict[str, Any]) -> str:
    rationale = spec.get(f"{name}_rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        raise ValueError(
            f"{name} is non-zero but no {name}_rationale was given; "
            "every risk adjustment needs a written economic basis, data source and calculation"
        )
    return rationale.strip()


def _additional_premiums(inputs: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
    """Generic risk premia beyond the fixed keys (country/size/industry/company).

    Optional input `additional_premiums`: a list of
    {label, rate, rationale, source} dicts. Every entry must name the risk,
    state the rate, explain why the risk is not already captured by beta, the
    ERP or the cash-flow scenarios, and cite a source. Entries are summed
    linearly on top of the base Ke, exactly like the fixed-key premia.
    """
    raw = inputs.get("additional_premiums") or []
    if not isinstance(raw, list):
        raise ValueError("additional_premiums must be a list of {label, rate, rationale, source}")
    detail: list[dict[str, Any]] = []
    total = 0.0
    for i, entry in enumerate(raw):
        prefix = f"additional_premiums[{i}]"
        if not isinstance(entry, dict):
            raise ValueError(f"{prefix} must be an object")
        label = entry.get("label")
        if not isinstance(label, str) or not label.strip():
            raise ValueError(f"{prefix}.label must be a non-empty string")
        rationale = entry.get("rationale")
        if not isinstance(rationale, str) or not rationale.strip():
            raise ValueError(f"{prefix}.rationale must be a non-empty string")
        source = entry.get("source")
        if isinstance(source, dict):
            source = source.get("source")
        if not isinstance(source, str) or not source.strip():
            raise ValueError(f"{prefix}.source must be a non-empty string (or a dict containing one)")
        rate_v = _finite(f"{prefix}.rate", entry.get("rate"))
        detail.append(
            {"label": label.strip(), "rate": rate_v, "rationale": rationale.strip(), "source": source}
        )
        total += rate_v
    if detail:
        warnings.append(
            "additional_premiums are stacked linearly on top of the base Ke; verify each risk is not "
            "already captured by beta, the ERP or the cash-flow scenarios (double counting)"
        )
    return {"detail": detail, "total": total}


def _beta_flags(beta: float, beta_meta: dict[str, Any], warnings: list[str]) -> None:
    se = beta_meta.get("standard_error")
    r2 = beta_meta.get("r_squared")
    if isinstance(se, (int, float)) and math.isfinite(float(se)) and abs(float(se)) > BETA_STD_ERROR_WARN:
        warnings.append(
            f"beta standard_error {se} > {BETA_STD_ERROR_WARN}: point estimate unreliable; report a documented range"
        )
    if isinstance(r2, (int, float)) and math.isfinite(float(r2)) and float(r2) < BETA_R_SQUARED_WARN:
        warnings.append(
            f"beta r_squared {r2} < {BETA_R_SQUARED_WARN}: the market explains little of this stock's variance; consider a bottom-up beta"
        )
    if math.isfinite(beta):
        if abs(beta) < BETA_ABS_LOW_WARN:
            warnings.append(
                f"|beta| {beta} < {BETA_ABS_LOW_WARN}: near-zero beta is often a small-sample artefact, not low risk"
            )
        if abs(beta) > BETA_ABS_HIGH_WARN:
            warnings.append(
                f"|beta| {beta} > {BETA_ABS_HIGH_WARN}: extreme beta; verify the window and frequency"
            )


def capm_ke(inputs: dict[str, Any]) -> dict[str, Any]:
    """Ke = rf + beta x ERP + country-risk + size + company-specific premia.

    Required: risk_free_rate, beta, equity_risk_premium (each number or
    provenance dict). Optional: country_risk_premium (needs
    country_risk_rationale), size_premium (needs size_premium_rationale),
    company_specific_premium (needs company_specific_premium_rationale),
    additional_premiums (list of {label, rate, rationale, source}),
    erp_includes_country_risk (bool), currency (echoed).

    The country-risk premium is added linearly as a conservative, auditable
    simplification; a beta-scaled country-risk treatment is an acceptable
    documented alternative - state which one you used and why.
    """
    if not isinstance(inputs, dict):
        raise ValueError("inputs must be a dict")
    warnings: list[str] = []

    rf, rf_meta = _normalize_input("risk_free_rate", _required(inputs, "risk_free_rate"), warnings)
    beta, beta_meta = _normalize_input("beta", _required(inputs, "beta"), warnings)
    erp, erp_meta = _normalize_input(
        "equity_risk_premium", _required(inputs, "equity_risk_premium"), warnings
    )
    _beta_flags(beta, beta_meta, warnings)

    crp = _finite("country_risk_premium", inputs.get("country_risk_premium", 0.0))
    if crp != 0.0:
        _rationale("country_risk_premium", inputs)
        if bool(inputs.get("erp_includes_country_risk", False)):
            warnings.append(
                "equity_risk_premium is declared to already include country risk AND a separate "
                "country_risk_premium is supplied: possible double counting. Remove one or document why both apply"
            )

    size = _finite("size_premium", inputs.get("size_premium", 0.0))
    if size != 0.0:
        _rationale("size_premium", inputs)

    csp = _finite("company_specific_premium", inputs.get("company_specific_premium", 0.0))
    if csp != 0.0:
        _rationale("company_specific_premium", inputs)

    additional = _additional_premiums(inputs, warnings)

    ke = rf + beta * erp + crp + size + csp + additional["total"]
    if ke <= 0:
        warnings.append("computed Ke is not positive; check inputs before using it")

    return {
        "model": "capm_ke",
        "ke": ke,
        "formula": (
            "Ke = rf + beta x ERP + country-risk premium + size premium + company-specific premium "
            "+ additional_premiums (see components)"
        ),
        "components": {
            "risk_free_rate": rf,
            "beta": beta,
            "beta_x_equity_risk_premium": beta * erp,
            "country_risk_premium": crp,
            "size_premium": size,
            "company_specific_premium": csp,
            "additional_premiums": additional["detail"],
            "additional_premiums_total": additional["total"],
        },
        "inputs": {
            "risk_free_rate": rf_meta | {"value": rf},
            "beta": beta_meta | {"value": beta},
            "equity_risk_premium": erp_meta | {"value": erp},
            "erp_includes_country_risk": bool(inputs.get("erp_includes_country_risk", False)),
            "currency": inputs.get("currency"),
        },
        "warnings": warnings,
        "audit_note": (
            "CAPM is a reference framework, not proof of accuracy. A low or unstable beta does not "
            "make the stock safe; report a range and the break-even Ke. See references/ke-wacc-estimation.md"
        ),
    }


def build_up_ke(inputs: dict[str, Any]) -> dict[str, Any]:
    """Build-up Ke = rf + ERP + size + industry + company-specific premia.

    For cases where CAPM beta is unavailable or not meaningful. Every premium
    beyond the base ERP requires a written rationale. Additional_premiums
    accepts a generic list of {label, rate, rationale, source} for risks that
    do not fit the fixed keys.
    """
    if not isinstance(inputs, dict):
        raise ValueError("inputs must be a dict")
    warnings: list[str] = []

    rf, rf_meta = _normalize_input("risk_free_rate", _required(inputs, "risk_free_rate"), warnings)
    erp, erp_meta = _normalize_input(
        "equity_risk_premium", _required(inputs, "equity_risk_premium"), warnings
    )
    size = _finite("size_premium", inputs.get("size_premium", 0.0))
    if size != 0.0:
        _rationale("size_premium", inputs)
    industry = _finite("industry_premium", inputs.get("industry_premium", 0.0))
    if industry != 0.0:
        _rationale("industry_premium", inputs)
    csp = _finite("company_specific_premium", inputs.get("company_specific_premium", 0.0))
    if csp != 0.0:
        _rationale("company_specific_premium", inputs)

    additional = _additional_premiums(inputs, warnings)

    ke = rf + erp + size + industry + csp + additional["total"]
    if ke <= 0:
        warnings.append("computed Ke is not positive; check inputs before using it")

    return {
        "model": "build_up_ke",
        "ke": ke,
        "formula": (
            "Ke = rf + ERP + size premium + industry premium + company-specific premium "
            "+ additional_premiums (see components)"
        ),
        "components": {
            "risk_free_rate": rf,
            "equity_risk_premium": erp,
            "size_premium": size,
            "industry_premium": industry,
            "company_specific_premium": csp,
            "additional_premiums": additional["detail"],
            "additional_premiums_total": additional["total"],
        },
        "inputs": {
            "risk_free_rate": rf_meta | {"value": rf},
            "equity_risk_premium": erp_meta | {"value": erp},
            "currency": inputs.get("currency"),
        },
        "warnings": warnings,
        "audit_note": "Build-up method: each premium must name the risk it captures and its source",
    }


def unlever_beta(beta_levered: Any, debt_to_equity: Any, tax_rate: Any) -> dict[str, Any]:
    """Hamada unlevering: beta_A = beta_L / (1 + (1 - t) x D/E)."""
    bl = _finite("beta_levered", beta_levered)
    de = _finite("debt_to_equity", debt_to_equity)
    t = _finite("tax_rate", tax_rate)
    if de < 0:
        raise ValueError("debt_to_equity must be >= 0")
    if not 0.0 <= t <= 1.0:
        raise ValueError("tax_rate must be within [0, 1]")
    ba = bl / (1.0 + (1.0 - t) * de)
    return {
        "model": "unlever_beta",
        "beta_asset": ba,
        "formula": "beta_A = beta_L / (1 + (1 - t) x D/E)",
        "inputs": {"beta_levered": bl, "debt_to_equity": de, "tax_rate": t},
    }


def relever_beta(beta_asset: Any, debt_to_equity: Any, tax_rate: Any) -> dict[str, Any]:
    """Hamada relevering: beta_L = beta_A x (1 + (1 - t) x D/E)."""
    ba = _finite("beta_asset", beta_asset)
    de = _finite("debt_to_equity", debt_to_equity)
    t = _finite("tax_rate", tax_rate)
    if de < 0:
        raise ValueError("debt_to_equity must be >= 0")
    if not 0.0 <= t <= 1.0:
        raise ValueError("tax_rate must be within [0, 1]")
    bl = ba * (1.0 + (1.0 - t) * de)
    return {
        "model": "relever_beta",
        "beta_levered": bl,
        "formula": "beta_L = beta_A x (1 + (1 - t) x D/E)",
        "inputs": {"beta_asset": ba, "debt_to_equity": de, "tax_rate": t},
    }


def bottom_up_beta(inputs: dict[str, Any]) -> dict[str, Any]:
    """Bottom-up beta: unlever comparable betas, weight them, relever at the
    target's capital structure.

    inputs:
      comparables: list of {"name", "beta_levered", "debt_to_equity",
                            "tax_rate", "weight" (optional)}
      target: {"tax_rate": ..., "debt_to_equity": ...}
    Weights are optional (equal weights when omitted); negative weights and
    all-zero weights are refused. Keep every unlevered beta and weight in the
    audit trail.
    """
    if not isinstance(inputs, dict):
        raise ValueError("inputs must be a dict")
    comps = _required(inputs, "comparables")
    if not isinstance(comps, (list, tuple)) or len(comps) == 0:
        raise ValueError("comparables must be a non-empty list")
    target = _required(inputs, "target")
    if not isinstance(target, dict):
        raise ValueError("target must be a dict")
    t_tax = _finite("target.tax_rate", _required(target, "tax_rate"))
    if not 0.0 <= t_tax <= 1.0:
        raise ValueError("target.tax_rate must be within [0, 1]")
    t_de = _finite("target.debt_to_equity", _required(target, "debt_to_equity"))
    if t_de < 0:
        raise ValueError("target.debt_to_equity must be >= 0")

    details: list[dict[str, Any]] = []
    weights: list[float] = []
    for i, comp in enumerate(comps):
        if not isinstance(comp, dict):
            raise ValueError(f"comparables[{i}] must be a dict")
        name = comp.get("name")
        if not isinstance(name, str) or not name.strip():
            name = f"comparable_{i}"
        bl = _finite(f"comparables[{i}].beta_levered", _required(comp, "beta_levered"))
        de = _finite(f"comparables[{i}].debt_to_equity", _required(comp, "debt_to_equity"))
        t = _finite(f"comparables[{i}].tax_rate", _required(comp, "tax_rate"))
        if de < 0:
            raise ValueError(f"comparables[{i}].debt_to_equity must be >= 0")
        if not 0.0 <= t <= 1.0:
            raise ValueError(f"comparables[{i}].tax_rate must be within [0, 1]")
        w = comp.get("weight")
        w = _finite(f"comparables[{i}].weight", 1.0 if w is None else w)
        if w < 0:
            raise ValueError(f"comparables[{i}].weight must be >= 0")
        ba = bl / (1.0 + (1.0 - t) * de)
        details.append({"name": name, "beta_levered": bl, "debt_to_equity": de,
                        "tax_rate": t, "weight": w, "beta_asset": ba})
        weights.append(w)

    total = sum(weights)
    if total <= 0:
        raise ValueError("comparable weights must sum to > 0")
    for d in details:
        d["normalized_weight"] = d["weight"] / total
    asset_beta = sum(d["beta_asset"] * d["normalized_weight"] for d in details)
    levered = relever_beta(asset_beta, t_de, t_tax)["beta_levered"]

    return {
        "model": "bottom_up_beta",
        "beta_asset": asset_beta,
        "beta_levered_at_target": levered,
        "formula": "beta_A = sum(w_i x beta_L,i / (1 + (1 - t_i) x D/E_i)); beta_L,target = beta_A x (1 + (1 - t_target) x D/E_target)",
        "target": {"tax_rate": t_tax, "debt_to_equity": t_de},
        "comparables": details,
        "audit_note": "Every unlevered beta, weight and the relevering step is kept for reproducibility",
    }


def wacc(inputs: dict[str, Any]) -> dict[str, Any]:
    """WACC = E/V x Ke + D/V x Kd x (1 - t), with provenance enforcement.

    Required: cost_of_equity, cost_of_debt, tax_rate, weight_equity,
    weight_debt. Weights must sum to 1. weight_basis is "market" (default) or
    "book" (requires weight_basis_rationale). cost_of_debt must declare a
    basis:
      - "observed": an actual financing cost with source and as-of date
      - "spread_build_up": risk_free_rate + credit_spread (both with
        provenance); value is computed when not supplied directly
      - "assumption": requires cost_of_debt_rationale (a fixed percentage
        without evidence is not acceptable)
    entity_type in {bank, insurer, financial, financial_institution} refuses
    WACC unless override_financial_wacc is true with override_rationale:
    financial entities discount equity flows at Ke.
    """
    if not isinstance(inputs, dict):
        raise ValueError("inputs must be a dict")
    warnings: list[str] = []

    ke, ke_meta = _normalize_input("cost_of_equity", _required(inputs, "cost_of_equity"), warnings)

    kd_spec = _required(inputs, "cost_of_debt")
    basis = None
    if isinstance(kd_spec, dict):
        basis = kd_spec.get("basis")
        if basis not in ("observed", "spread_build_up", "assumption"):
            raise ValueError(
                "cost_of_debt basis must be 'observed', 'spread_build_up' or 'assumption'"
            )
        if basis == "assumption":
            _rationale("cost_of_debt", inputs)
            warnings.append(
                "cost_of_debt is an assumption without observed or market evidence; treat the WACC as assumption-driven"
            )
        if basis == "spread_build_up" and "value" not in kd_spec:
            rf, _ = _normalize_input(
                "cost_of_debt.risk_free_rate", _required(kd_spec, "risk_free_rate"), warnings
            )
            spread, _ = _normalize_input(
                "cost_of_debt.credit_spread", _required(kd_spec, "credit_spread"), warnings
            )
            kd_spec = dict(kd_spec)
            kd_spec["value"] = rf + spread
            if not (isinstance(kd_spec.get("source"), str) and kd_spec["source"].strip()):
                kd_spec["source"] = (
                    "computed: risk_free_rate + credit_spread; component provenance retained in inputs"
                )
        elif basis == "spread_build_up" and "value" in kd_spec:
            warnings.append(
                "cost_of_debt has both a supplied value and spread_build_up components; "
                "the supplied value is used - state why it differs from rf + spread"
            )
    kd, kd_meta = _normalize_input("cost_of_debt", kd_spec, warnings)
    if kd < 0:
        warnings.append("cost_of_debt is negative; verify the source and period")

    tax = _finite("tax_rate", _required(inputs, "tax_rate"))
    if not 0.0 <= tax <= 1.0:
        raise ValueError("tax_rate must be within [0, 1]")

    we = _finite("weight_equity", _required(inputs, "weight_equity"))
    wd = _finite("weight_debt", _required(inputs, "weight_debt"))
    if we < 0 or wd < 0:
        raise ValueError("weights must be >= 0")
    if abs(we + wd - 1.0) > 1e-9:
        raise ValueError("weight_equity + weight_debt must sum to 1")

    weight_basis = inputs.get("weight_basis", "market")
    if weight_basis not in ("market", "book"):
        raise ValueError("weight_basis must be 'market' or 'book'")
    if weight_basis == "book":
        rationale = inputs.get("weight_basis_rationale")
        if not isinstance(rationale, str) or not rationale.strip():
            raise ValueError(
                "book-value weights require weight_basis_rationale (why market weights are unavailable or misleading)"
            )
        warnings.append("book-value weights used; state why market weights are unavailable or misleading")

    entity_type = inputs.get("entity_type")
    override = bool(inputs.get("override_financial_wacc", False))
    if isinstance(entity_type, str) and entity_type.strip().lower() in FINANCIAL_ENTITY_TYPES:
        if not override:
            raise ValueError(
                f"entity_type '{entity_type}' is a financial institution: WACC is not the right "
                "discount rate. Discount equity flows (DDM / residual income / FCFE) at Ke instead. "
                "A documented override requires override_financial_wacc=true and override_rationale"
            )
        rationale = inputs.get("override_rationale")
        if not isinstance(rationale, str) or not rationale.strip():
            raise ValueError("override_financial_wacc requires override_rationale")
        warnings.append(
            "WACC applied to a financial institution under a documented override; this is a category "
            "exception - state why FCFF/WACC is meaningful for this entity"
        )

    equity_leg = we * ke
    debt_leg = wd * kd * (1.0 - tax)
    result_wacc = equity_leg + debt_leg
    if result_wacc <= 0:
        warnings.append("computed WACC is not positive; check inputs before using it")

    return {
        "model": "wacc",
        "wacc": result_wacc,
        "formula": "WACC = E/V x Ke + D/V x Kd x (1 - t)",
        "components": {
            "equity_leg": equity_leg,
            "debt_leg_after_tax": debt_leg,
            "weight_equity": we,
            "weight_debt": wd,
            "weight_basis": weight_basis,
            "tax_rate": tax,
        },
        "inputs": {
            "cost_of_equity": ke_meta | {"value": ke},
            "cost_of_debt": kd_meta | {"value": kd, "basis": basis},
            "entity_type": entity_type,
            "currency": inputs.get("currency"),
        },
        "warnings": warnings,
        "audit_note": (
            "WACC discounts FCFF only. Never discount FCFE, dividends or residual income at WACC, "
            "and never discount FCFF at Ke. Match the currency of the rate to the currency of the flows"
        ),
    }


def ke_scenario(inputs: dict[str, Any]) -> dict[str, Any]:
    """Bear / base / bull Ke estimation with mandatory rationales.

    inputs = {"bear": {"method": "capm"|"build_up", "inputs": {...},
                       "rationale": "..."},
              "base": {...}, "bull": {...}}
    Convention: bear carries the conservative (higher) Ke. The module warns
    if bear < base or bull > base so inverted definitions are caught.
    """
    if not isinstance(inputs, dict):
        raise ValueError("inputs must be a dict")
    scenarios: dict[str, Any] = {}
    collected_warnings: list[str] = []
    for key in ("bear", "base", "bull"):
        if key not in inputs or not isinstance(inputs[key], dict):
            raise ValueError(f"ke_scenario requires a '{key}' object")
        spec = inputs[key]
        rationale = spec.get("rationale")
        if not isinstance(rationale, str) or not rationale.strip():
            raise ValueError(f"ke_scenario '{key}' requires a non-empty rationale")
        method = spec.get("method", "capm")
        sub = _required(spec, "inputs")
        if not isinstance(sub, dict):
            raise ValueError(f"ke_scenario '{key}': inputs must be a dict")
        if method == "capm":
            result = capm_ke(sub)
        elif method == "build_up":
            result = build_up_ke(sub)
        else:
            raise ValueError("scenario method must be 'capm' or 'build_up'")
        result["rationale"] = rationale.strip()
        result["method"] = method
        collected_warnings.extend(f"{key}: {w}" for w in result.get("warnings", []))
        scenarios[key] = result

    bear_ke = scenarios["bear"]["ke"]
    base_ke = scenarios["base"]["ke"]
    bull_ke = scenarios["bull"]["ke"]
    if bear_ke < base_ke:
        collected_warnings.append(
            "bear Ke is below base Ke; the bear case should carry the conservative (higher) rate unless you document why not"
        )
    if bull_ke > base_ke:
        collected_warnings.append(
            "bull Ke is above base Ke; confirm the scenario definitions"
        )

    return {
        "model": "ke_scenario",
        "scenarios": scenarios,
        "ke_base": base_ke,
        "ke_spread_bull_minus_bear": bull_ke - bear_ke,
        "warnings": collected_warnings,
        "audit_note": (
            "A wider Ke spread is a statement about uncertainty, not a licence to pick the "
            "favourable end. Recompute the valuation across the range and report break-even Ke"
        ),
    }


def run_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """JSON dispatch for the Ke/WACC module (called from valuation.py)."""
    if not isinstance(payload, dict):
        raise ValueError("Input JSON must be an object")
    model = payload.get("model")
    if model == "capm_ke":
        return capm_ke(payload)
    if model == "build_up_ke":
        return build_up_ke(payload)
    if model == "unlever_beta":
        return unlever_beta(payload["beta_levered"], payload["debt_to_equity"], payload["tax_rate"])
    if model == "relever_beta":
        return relever_beta(payload["beta_asset"], payload["debt_to_equity"], payload["tax_rate"])
    if model == "bottom_up_beta":
        return bottom_up_beta(payload)
    if model == "wacc":
        return wacc(payload)
    if model == "ke_scenario":
        return ke_scenario(payload)
    raise ValueError(
        "ke/wacc model must be capm_ke, build_up_ke, unlever_beta, relever_beta, "
        "bottom_up_beta, wacc, or ke_scenario"
    )
