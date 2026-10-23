#!/usr/bin/env python3
"""Deterministic valuation calculators for China A-share / Hong Kong stocks.
Python standard library only.

Models: FCFF-DCF (dcf_fcff), DDM (ddm), FCFE (fcfe), residual income / PB-ROE
(residual_income), P/EV for insurers (pev), asset-based NAV (nav), AFFO-based
REIT valuation (affo), property-level REIT valuation (reit_noi), mid-cycle
normalization (normalize_cycle), comparable-multiple cross-checks
(comparable_multiples), sensitivity matrices (dcf_sensitivity,
ddm_sensitivity), reverse solvers (reverse_dcf_growth, reverse_dcf_wacc,
reverse_dcf_fcff_scale, reverse_ddm_ke), a default model-routing table by
company type (route_model), and auditable cost-of-capital estimation
(capm_ke, build_up_ke, unlever_beta, relever_beta, bottom_up_beta, wacc,
ke_scenario - implemented in ke_wacc.py, dispatched from here).

Units: keep monetary units consistent. For example, if FCFF is RMB million and
shares are million shares, the calculated per-share value is RMB/share.
run_payload echoes the original input under "input_echo" so the same inputs
reproduce the same outputs, and validates optional currency/unit/as_of
metadata declarations.

Every function raises ValueError on invalid input instead of guessing: a
refusal to compute is a valid result when the data do not support a model.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Sequence

try:
    import ke_wacc
except ImportError:  # pragma: no cover - direct script execution fallback
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import ke_wacc


def _finite(name: str, value: float) -> float:
    try:
        x = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(x):
        raise ValueError(f"{name} must be finite")
    return x


def _nonempty_finite_list(name: str, values: Sequence[float]) -> list[float]:
    if not isinstance(values, (list, tuple)) or len(values) == 0:
        raise ValueError(f"{name} must be a non-empty list")
    return [_finite(f"{name}[{i}]", v) for i, v in enumerate(values)]


def _discount_rate(name: str, rate: float) -> float:
    rate = _finite(name, rate)
    if rate <= -1:
        raise ValueError(f"{name} must be greater than -100%")
    return rate


TERMINAL_VALUE_SHARE_WARN = 0.75
TERMINAL_IMPLIED_GROWTH_WARN = 0.05


def _terminal_share_warnings(share: float | None) -> list[str]:
    """Flag over-reliance on a Gordon-growth terminal value."""
    if share is not None and share > TERMINAL_VALUE_SHARE_WARN:
        return [
            f"terminal value is {share:.1%} of total value (> {TERMINAL_VALUE_SHARE_WARN:.0%}); "
            "the estimate is dominated by long-horizon assumptions - stress the explicit-period "
            "flows and the perpetuity inputs before relying on the point estimate"
        ]
    return []


def bisect_root(f: Any, lo: float, hi: float, tol: float = 1e-10, max_iter: int = 200) -> dict[str, Any]:
    """Bisection root-finder for monotone objective functions.

    f(lo) and f(hi) must have opposite signs (a bracket). Used by the reverse
    solvers; numerical stability matters more than speed here, so the default
    tolerance is tight and the iteration cap is explicit. Raises when the
    root is not bracketed instead of returning an arbitrary point.
    """
    flo = f(lo)
    fhi = f(hi)
    if flo == 0:
        return {"root": lo, "iterations": 0, "converged": True}
    if fhi == 0:
        return {"root": hi, "iterations": 0, "converged": True}
    if (flo > 0) == (fhi > 0):
        raise ValueError("root not bracketed: f(lo) and f(hi) have the same sign")
    iterations = 0
    while (hi - lo) > tol and iterations < max_iter:
        mid = (lo + hi) / 2.0
        fmid = f(mid)
        if fmid == 0:
            return {"root": mid, "iterations": iterations + 1, "converged": True}
        if (fmid > 0) == (flo > 0):
            lo, flo = mid, fmid
        else:
            hi, fhi = mid, fmid
        iterations += 1
    return {"root": (lo + hi) / 2.0, "iterations": iterations, "converged": (hi - lo) <= tol}


def dcf_fcff(
    fcff: Sequence[float],
    wacc: float,
    terminal_growth: float | None = None,
    diluted_shares: float | None = None,
    net_debt: float = 0.0,
    non_operating_assets: float = 0.0,
    minority_interest: float = 0.0,
    preferred_equity: float = 0.0,
    terminal_method: str = "gordon",
    ebitda: Sequence[float] | None = None,
    exit_ev_ebitda: float | None = None,
) -> dict[str, Any]:
    """Value equity from annual FCFF forecasts with a Gordon or exit-multiple terminal value.

    net_debt = interest-bearing debt minus cash and cash equivalents already
    included in that definition. Do not include that same cash again in
    non_operating_assets. All amounts must use the same currency/unit.

    terminal_method:
      - "gordon": TV_n = FCFF_n x (1 + g) / (WACC - g); requires terminal_growth
        and a positive last explicit FCFF.
      - "exit_multiple": TV_n = exit_ev_ebitda x EBITDA_n; requires an ebitda
        series aligned to the forecast years and a positive terminal EBITDA.
        Negative explicit FCFF is allowed. terminal_growth is not used, but the
        perpetuity growth implied by the exit multiple is reported and warned on
        so an aggressive multiple cannot hide behind the label "market-based".
    """
    flows = _nonempty_finite_list("fcff", fcff)
    wacc = _discount_rate("wacc", wacc)
    if diluted_shares is None:
        raise ValueError("diluted_shares is required")
    shares = _finite("diluted_shares", diluted_shares)
    if shares <= 0:
        raise ValueError("diluted_shares must be > 0")

    method = str(terminal_method).strip().lower()
    if method not in ("gordon", "exit_multiple"):
        raise ValueError("terminal_method must be 'gordon' or 'exit_multiple'")
    warnings: list[str] = []
    g: float | None = None
    implied_g: float | None = None
    terminal_ebitda: float | None = None
    multiple: float | None = None

    if method == "gordon":
        if terminal_growth is None:
            raise ValueError("terminal_growth is required when terminal_method is 'gordon'")
        g = _finite("terminal_growth", terminal_growth)
        if g <= -1:
            raise ValueError("terminal_growth must be > -100%")
        if wacc <= g:
            raise ValueError("wacc must be greater than terminal_growth")
        if flows[-1] <= 0:
            raise ValueError("last explicit FCFF must be positive for a Gordon-growth terminal value; model the transition to positive stable cash flow explicitly")
        terminal_value = flows[-1] * (1.0 + g) / (wacc - g)
    else:
        if terminal_growth is not None:
            warnings.append(
                "terminal_growth is ignored because terminal_method is 'exit_multiple'"
            )
        if ebitda is None:
            raise ValueError("ebitda series is required when terminal_method is 'exit_multiple'")
        ebitda_series = _nonempty_finite_list("ebitda", ebitda)
        if len(ebitda_series) != len(flows):
            raise ValueError(
                f"ebitda must have one value per forecast year (got {len(ebitda_series)} for {len(flows)} FCFF years)"
            )
        if exit_ev_ebitda is None:
            raise ValueError("exit_ev_ebitda is required when terminal_method is 'exit_multiple'")
        multiple = _finite("exit_ev_ebitda", exit_ev_ebitda)
        if multiple <= 0:
            raise ValueError("exit_ev_ebitda must be > 0")
        terminal_ebitda = ebitda_series[-1]
        if terminal_ebitda <= 0:
            raise ValueError("terminal-year ebitda must be positive for an exit-multiple terminal value")
        terminal_value = multiple * terminal_ebitda
        denominator = terminal_value + flows[-1]
        if denominator <= 0:
            warnings.append(
                "exit-multiple terminal value plus the terminal FCFF is not positive; "
                "implied perpetuity growth cannot be computed - treat the terminal value as unsupported"
            )
        else:
            implied_g = (terminal_value * wacc - flows[-1]) / denominator
            if implied_g >= wacc:
                warnings.append(
                    f"exit multiple implies perpetuity growth of {implied_g:.2%}, at or above WACC "
                    f"({wacc:.2%}); the terminal value is not economically consistent"
                )
            elif implied_g > TERMINAL_IMPLIED_GROWTH_WARN:
                warnings.append(
                    f"exit multiple implies perpetuity growth of {implied_g:.2%} (> {TERMINAL_IMPLIED_GROWTH_WARN:.0%}); "
                    "test a lower multiple or explain why above-trend growth persists forever"
                )
            elif implied_g < -0.02:
                warnings.append(
                    f"exit multiple implies perpetuity shrinkage of {implied_g:.2%}; "
                    "check whether the multiple and terminal EBITDA are consistent"
                )

    pv_flows = [cf / ((1.0 + wacc) ** year) for year, cf in enumerate(flows, start=1)]
    pv_terminal = terminal_value / ((1.0 + wacc) ** len(flows))
    ev = sum(pv_flows) + pv_terminal

    nd = _finite("net_debt", net_debt)
    noa = _finite("non_operating_assets", non_operating_assets)
    mi = _finite("minority_interest", minority_interest)
    pref = _finite("preferred_equity", preferred_equity)
    equity = ev - nd + noa - mi - pref
    share = (pv_terminal / ev) if ev > 0 else None
    return {
        "model": "dcf_fcff",
        "currency_unit_note": "All inputs must use one consistent currency and scale.",
        "years": len(flows),
        "terminal_method": method,
        "pv_explicit_fcff": sum(pv_flows),
        "terminal_value_at_year_n": terminal_value,
        "pv_terminal_value": pv_terminal,
        "terminal_value_share_of_ev": share,
        "warnings": _terminal_share_warnings(share) + warnings,
        "enterprise_value": ev,
        "net_debt": nd,
        "non_operating_assets": noa,
        "minority_interest": mi,
        "preferred_equity": pref,
        "equity_value": equity,
        "diluted_shares": shares,
        "value_per_share": equity / shares,
        "wacc": wacc,
        "terminal_growth": g,
        "exit_ev_ebitda": multiple,
        "terminal_ebitda": terminal_ebitda,
        "implied_perpetuity_growth": implied_g,
    }


def ddm(
    dividends_per_share: Sequence[float],
    ke: float,
    terminal_growth: float,
) -> dict[str, Any]:
    """Value one share from explicit annual dividends D1...Dn and a Gordon TV."""
    dividends = _nonempty_finite_list("dividends_per_share", dividends_per_share)
    ke = _discount_rate("ke", ke)
    g = _finite("terminal_growth", terminal_growth)
    if g <= -1:
        raise ValueError("terminal_growth must be > -100%")
    if ke <= g:
        raise ValueError("ke must be greater than terminal_growth")
    if any(d < 0 for d in dividends):
        raise ValueError("dividends_per_share cannot contain negative dividends")
    if dividends[-1] <= 0:
        raise ValueError("last explicit dividend must be positive for a Gordon-growth terminal value")

    pv_dividends = [d / ((1.0 + ke) ** year) for year, d in enumerate(dividends, start=1)]
    terminal_dividend = dividends[-1] * (1.0 + g)
    terminal_value = terminal_dividend / (ke - g)
    pv_terminal = terminal_value / ((1.0 + ke) ** len(dividends))
    value = sum(pv_dividends) + pv_terminal
    share = (pv_terminal / value) if value > 0 else None
    return {
        "model": "ddm",
        "years": len(dividends),
        "pv_explicit_dividends_per_share": sum(pv_dividends),
        "terminal_dividend_per_share_d_n_plus_1": terminal_dividend,
        "terminal_value_at_year_n_per_share": terminal_value,
        "pv_terminal_value_per_share": pv_terminal,
        "terminal_value_share_of_total": share,
        "warnings": _terminal_share_warnings(share),
        "value_per_share": value,
        "ke": ke,
        "terminal_growth": g,
    }


def dcf_sensitivity(
    fcff: Sequence[float],
    wacc_values: Sequence[float],
    growth_values: Sequence[float],
    diluted_shares: float,
    net_debt: float = 0.0,
    non_operating_assets: float = 0.0,
    minority_interest: float = 0.0,
    preferred_equity: float = 0.0,
) -> dict[str, Any]:
    """Return value-per-share matrix: rows are WACC, columns are terminal growth."""
    rates = _nonempty_finite_list("wacc_values", wacc_values)
    growths = _nonempty_finite_list("growth_values", growth_values)
    matrix: list[list[float | None]] = []
    for rate in rates:
        row: list[float | None] = []
        for growth in growths:
            try:
                result = dcf_fcff(
                    fcff, rate, growth, diluted_shares, net_debt,
                    non_operating_assets, minority_interest, preferred_equity,
                )
                row.append(result["value_per_share"])
            except ValueError:
                row.append(None)
        matrix.append(row)
    return {"model": "dcf_sensitivity", "wacc_values": rates,
            "terminal_growth_values": growths, "value_per_share_matrix": matrix}


def ddm_sensitivity(
    dividends_per_share: Sequence[float],
    ke_values: Sequence[float],
    growth_values: Sequence[float],
) -> dict[str, Any]:
    """Return DDM value-per-share matrix: rows are Ke, columns are terminal growth."""
    rates = _nonempty_finite_list("ke_values", ke_values)
    growths = _nonempty_finite_list("growth_values", growth_values)
    matrix: list[list[float | None]] = []
    for rate in rates:
        row: list[float | None] = []
        for growth in growths:
            try:
                result = ddm(dividends_per_share, rate, growth)
                row.append(result["value_per_share"])
            except ValueError:
                row.append(None)
        matrix.append(row)
    return {"model": "ddm_sensitivity", "ke_values": rates,
            "terminal_growth_values": growths, "value_per_share_matrix": matrix}


def fcfe(
    fcfe: Sequence[float],
    ke: float,
    terminal_growth: float,
    diluted_shares: float,
) -> dict[str, Any]:
    """Value equity from annual FCFE forecasts discounted at Ke (Gordon terminal).

    FCFE is cash flow to common shareholders after debt service, regulatory
    capital needs and reinvestment, so it is already an equity flow: discount at
    the cost of equity and apply NO enterprise-to-equity bridge. Forecast the
    cash actually distributable, not FCFE relabelled as dividends.
    """
    flows = _nonempty_finite_list("fcfe", fcfe)
    ke = _discount_rate("ke", ke)
    g = _finite("terminal_growth", terminal_growth)
    shares = _finite("diluted_shares", diluted_shares)
    if shares <= 0:
        raise ValueError("diluted_shares must be > 0")
    if g <= -1:
        raise ValueError("terminal_growth must be > -100%")
    if ke <= g:
        raise ValueError("ke must be greater than terminal_growth")
    if flows[-1] <= 0:
        raise ValueError("last explicit FCFE must be positive for a Gordon-growth terminal value")

    pv_flows = [cf / ((1.0 + ke) ** year) for year, cf in enumerate(flows, start=1)]
    terminal_value = flows[-1] * (1.0 + g) / (ke - g)
    pv_terminal = terminal_value / ((1.0 + ke) ** len(flows))
    equity_value = sum(pv_flows) + pv_terminal
    share = (pv_terminal / equity_value) if equity_value > 0 else None
    return {
        "model": "fcfe",
        "currency_unit_note": "All inputs must use one consistent currency and scale.",
        "years": len(flows),
        "pv_explicit_fcfe": sum(pv_flows),
        "terminal_value_at_year_n": terminal_value,
        "pv_terminal_value": pv_terminal,
        "terminal_value_share_of_total": share,
        "warnings": _terminal_share_warnings(share),
        "equity_value": equity_value,
        "diluted_shares": shares,
        "value_per_share": equity_value / shares,
        "ke": ke,
        "terminal_growth": g,
    }


def residual_income(
    bvps: float,
    roe_path: Sequence[float],
    payout: float,
    ke: float,
    terminal_roe: float,
    terminal_book_growth: float,
) -> dict[str, Any]:
    """Residual income (PB-ROE) model.

    RI_t = (ROE_t - ke) * BVPS_{t-1}; BVPS_t = BVPS_{t-1} * (1 + (1 - payout) * ROE_t).
    Value = BVPS_0 + sum PV(RI_t) + PV(terminal RI), where the terminal stage
    assumes ROE converges to terminal_roe and book grows at terminal_book_growth.

    Assumes clean-surplus accounting and no equity issuance; document capital
    raises, buybacks and OCI shocks separately. A negative residual income is
    legitimate output (value below book), not an error.
    """
    bvps0 = _finite("bvps", bvps)
    if bvps0 <= 0:
        raise ValueError("bvps must be > 0")
    roes = _nonempty_finite_list("roe_path", roe_path)
    pay = _finite("payout", payout)
    if not 0.0 <= pay <= 1.0:
        raise ValueError("payout must be between 0 and 1")
    ke = _discount_rate("ke", ke)
    roe_t = _finite("terminal_roe", terminal_roe)
    g_b = _finite("terminal_book_growth", terminal_book_growth)
    if ke <= g_b:
        raise ValueError("ke must be greater than terminal_book_growth")

    bvps_t = bvps0
    ri_list: list[float] = []
    bvps_list: list[float] = []
    pv_ri = 0.0
    for year, roe in enumerate(roes, start=1):
        ri = (roe - ke) * bvps_t
        ri_list.append(ri)
        bvps_list.append(bvps_t)
        pv_ri += ri / ((1.0 + ke) ** year)
        bvps_t = bvps_t * (1.0 + (1.0 - pay) * roe)
    terminal_ri = (roe_t - ke) * bvps_t
    terminal_value = terminal_ri / (ke - g_b)
    pv_terminal = terminal_value / ((1.0 + ke) ** len(roes))
    value = bvps0 + pv_ri + pv_terminal
    return {
        "model": "residual_income",
        "bvps_0": bvps0,
        "roe_path": roes,
        "payout": pay,
        "ri_per_year": ri_list,
        "bvps_per_year_start": bvps_list,
        "bvps_terminal_start": bvps_t,
        "pv_explicit_ri": pv_ri,
        "terminal_ri": terminal_ri,
        "pv_terminal_value": pv_terminal,
        "value_per_share": value,
        "implied_pb": value / bvps0,
        "ke": ke,
        "terminal_roe": roe_t,
        "terminal_book_growth": g_b,
    }


def pev(
    embedded_value: float,
    pev_multiple: float,
    shares: float,
    holdco_discount: float = 0.0,
) -> dict[str, Any]:
    """P/EV multiple valuation for insurers.

    value per share = EV * multiple * (1 - holdco_discount) / shares.
    The multiple must come from disclosed comparables or a documented
    cross-check; do not reverse-solve it from the current price and call that
    validation. Value of new business (VNB) is not automatically included -
    add it explicitly with a stated method if used.
    """
    ev = _finite("embedded_value", embedded_value)
    mult = _finite("pev_multiple", pev_multiple)
    sh = _finite("shares", shares)
    disc = _finite("holdco_discount", holdco_discount)
    if ev <= 0:
        raise ValueError("embedded_value must be > 0")
    if mult <= 0:
        raise ValueError("pev_multiple must be > 0")
    if sh <= 0:
        raise ValueError("shares must be > 0")
    if not 0.0 <= disc < 1.0:
        raise ValueError("holdco_discount must be in [0, 1)")
    equity = ev * mult * (1.0 - disc)
    return {
        "model": "pev",
        "embedded_value": ev,
        "pev_multiple": mult,
        "holdco_discount": disc,
        "implied_equity_value": equity,
        "shares": sh,
        "value_per_share": equity / sh,
    }


def nav(
    asset_values: Sequence[float],
    liabilities: float,
    shares: float,
    scenario: str = "base",
) -> dict[str, Any]:
    """Asset-based NAV: (sum of asset values - liabilities) / shares.

    Value assets item by item with a stated basis (market comparables,
    appraisal, or book) and pass them one by one; a single blended number
    hides the valuation work and defeats stress testing. Negative NAV is a
    legitimate stressed-scenario output, not an error.
    """
    assets = _nonempty_finite_list("asset_values", asset_values)
    liab = _finite("liabilities", liabilities)
    sh = _finite("shares", shares)
    if sh <= 0:
        raise ValueError("shares must be > 0")
    gross = sum(assets)
    nav_total = gross - liab
    return {
        "model": "nav",
        "scenario": scenario,
        "gross_asset_value": gross,
        "liabilities": liab,
        "nav_total": nav_total,
        "shares": sh,
        "value_per_share": nav_total / sh,
    }


def affo(
    affo_per_share: float,
    cap_rate: float | None = None,
    multiple: float | None = None,
) -> dict[str, Any]:
    """AFFO-based REIT valuation. Provide exactly one of cap_rate or multiple.

    cap_rate method: value = AFFO / cap_rate (flat perpetuity; an observed
    market cap rate already embeds growth expectations).
    multiple method: value = AFFO * multiple.
    AFFO must be a repeatable distributable figure: recurring maintenance
    capex deducted, straight-lining and one-off items removed.
    """
    affo = _finite("affo_per_share", affo_per_share)
    if affo <= 0:
        raise ValueError("affo_per_share must be > 0")
    if (cap_rate is None) == (multiple is None):
        raise ValueError("provide exactly one of cap_rate or multiple")
    if cap_rate is not None:
        r = _finite("cap_rate", cap_rate)
        if r <= 0:
            raise ValueError("cap_rate must be > 0")
        return {
            "model": "affo",
            "method": "cap_rate",
            "affo_per_share": affo,
            "cap_rate": r,
            "value_per_share": affo / r,
        }
    m = _finite("multiple", multiple)
    if m <= 0:
        raise ValueError("multiple must be > 0")
    return {
        "model": "affo",
        "method": "multiple",
        "affo_per_share": affo,
        "multiple": m,
        "value_per_share": affo * m,
    }


def reit_noi(
    noi: float,
    property_cap_rate: float,
    liabilities: float,
    shares: float,
    other_assets: float = 0.0,
    scenario: str = "base",
) -> dict[str, Any]:
    """Property-level REIT valuation: property value = NOI / property cap rate,
    then the SAME equity bridge as nav().

    Two cap-rate bases exist and they are not interchangeable:
    - property cap rate (NOI-based): used HERE, on property-level NOI;
    - equity-level rates applied to AFFO: used by affo().

    Feeding a property cap rate into affo(), or an equity AFFO into this
    function, is a口径 error. The bridge (liabilities, other assets) is
    identical to nav() so the stress scenario stays comparable.
    """
    noi_v = _finite("noi", noi)
    if noi_v <= 0:
        raise ValueError("noi must be > 0")
    r = _finite("property_cap_rate", property_cap_rate)
    if r <= 0:
        raise ValueError("property_cap_rate must be > 0")
    property_value = noi_v / r
    assets = [property_value]
    oa = _finite("other_assets", other_assets)
    if oa:
        assets.append(oa)
    result = nav(assets, liabilities, shares, scenario)
    result["model"] = "reit_noi"
    result["bridge_model"] = "nav"
    result["noi"] = noi_v
    result["property_cap_rate"] = r
    result["property_value"] = property_value
    result["note"] = (
        "Property-level direct capitalisation: value = NOI / property cap rate. This is NOT the "
        "affo() cap_rate method, which capitalises an equity-level distributable figure. Do not mix "
        "the two bases; cross-check with affo() and report the gap and its cause."
    )
    return result


def comparable_multiples(inputs: dict[str, Any]) -> dict[str, Any]:
    """Relative-valuation cross-check on disclosed comparables.

    Supported methods: pe (needs per_share_metrics.eps), pb (needs
    per_share_metrics.bvps), p_affo (needs per_share_metrics.affo_per_share),
    ev_ebitda (needs entity_metrics.ebitda, net_debt and shares - the
    EV-to-equity bridge is explicit: equity = EV - net_debt).

    Each multiple is either a bare number (provenance warning) or a dict
    {"value", "comparable_set", "as_of"} - dict form must name the comparable
    set and as-of date. Relative valuation is a cross-check on intrinsic
    models, never a substitute, and results are never averaged mechanically
    with DCF / DDM outputs.
    """
    if not isinstance(inputs, dict):
        raise ValueError("inputs must be a dict")
    warnings: list[str] = []
    per_share = inputs.get("per_share_metrics") or {}
    entity = inputs.get("entity_metrics") or {}
    if not isinstance(per_share, dict) or not isinstance(entity, dict):
        raise ValueError("per_share_metrics and entity_metrics must be dicts")
    multiples = inputs.get("multiples")
    if not isinstance(multiples, dict) or not multiples:
        raise ValueError("multiples must be a non-empty dict")

    def _multiple(name: str) -> tuple[float, dict[str, Any]]:
        spec = multiples[name]
        if isinstance(spec, dict):
            if "value" not in spec or spec["value"] is None:
                raise ValueError(f"multiples.{name} dict form must contain 'value'")
            value = _finite(f"multiples.{name}", spec["value"])
            comp_set = spec.get("comparable_set")
            as_of = spec.get("as_of")
            if not isinstance(comp_set, str) or not comp_set.strip():
                raise ValueError(f"multiples.{name} dict form requires 'comparable_set'")
            if not isinstance(as_of, str) or not as_of.strip():
                raise ValueError(f"multiples.{name} dict form requires 'as_of'")
            return value, {k: v for k, v in spec.items() if k != "value"}
        value = _finite(f"multiples.{name}", spec)
        warnings.append(
            f"multiples.{name}: bare number without comparable set / as-of date; "
            "record the comparables and date in the report"
        )
        return value, {"comparable_set": None, "as_of": None}

    methods: dict[str, Any] = {}

    if "pe" in multiples:
        m, meta = _multiple("pe")
        if "eps" not in per_share:
            raise ValueError("pe requires per_share_metrics.eps")
        eps = _finite("eps", per_share["eps"])
        methods["pe"] = {
            "metric": "eps", "metric_per_share": eps, "multiple": m,
            "implied_value_per_share": eps * m, "provenance": meta,
            "note": "Use a normalized (mid-cycle) EPS, not a one-off year",
        }

    if "pb" in multiples:
        m, meta = _multiple("pb")
        if "bvps" not in per_share:
            raise ValueError("pb requires per_share_metrics.bvps")
        bvps = _finite("bvps", per_share["bvps"])
        methods["pb"] = {
            "metric": "bvps", "metric_per_share": bvps, "multiple": m,
            "implied_value_per_share": bvps * m, "provenance": meta,
            "note": "P/B is only meaningful against ROE vs Ke; cross-check with residual_income",
        }

    if "p_affo" in multiples:
        m, meta = _multiple("p_affo")
        if "affo_per_share" not in per_share:
            raise ValueError("p_affo requires per_share_metrics.affo_per_share")
        affo_ps = _finite("affo_per_share", per_share["affo_per_share"])
        methods["p_affo"] = {
            "metric": "affo_per_share", "metric_per_share": affo_ps, "multiple": m,
            "implied_value_per_share": affo_ps * m, "provenance": meta,
            "note": "AFFO must be a repeatable distributable figure (recurring maintenance capex deducted)",
        }

    if "ev_ebitda" in multiples:
        m, meta = _multiple("ev_ebitda")
        for key in ("ebitda", "net_debt", "shares"):
            if key not in entity:
                raise ValueError(f"ev_ebitda requires entity_metrics.{key}")
        ebitda = _finite("ebitda", entity["ebitda"])
        nd = _finite("net_debt", entity["net_debt"])
        sh = _finite("shares", entity["shares"])
        if sh <= 0:
            raise ValueError("entity_metrics.shares must be > 0")
        ev_implied = ebitda * m
        equity = ev_implied - nd
        methods["ev_ebitda"] = {
            "metric": "ebitda", "ebitda": ebitda, "multiple": m,
            "implied_enterprise_value": ev_implied, "net_debt": nd, "shares": sh,
            "implied_equity_value": equity, "implied_value_per_share": equity / sh,
            "provenance": meta,
            "bridge": "equity = EV - net_debt; do not add back cash already netted, and subtract minority/preferred claims where material",
        }

    if not methods:
        raise ValueError(
            "no recognised multiple method; use pe, pb, p_affo and/or ev_ebitda"
        )

    return {
        "model": "comparable_multiples",
        "methods": methods,
        "normalization_note": inputs.get("normalization_note"),
        "warnings": warnings,
        "note": (
            "Relative valuation cross-check only. Never average mechanically with intrinsic-model "
            "outputs; diagnose the gap (growth, margins, reinvestment, risk) instead"
        ),
    }


def normalize_cycle(values: Sequence[float], method: str = "median") -> dict[str, Any]:
    """Mid-cycle normalization of a full-cycle annual series (EPS, unit margin, ...).

    The input series must span at least one full cycle; a series covering only
    a boom or only a trough normalizes to the wrong level. Check whether a
    structural break (policy, technology, capacity, demand) makes history
    irrelevant before trusting any normalization.
    """
    series = _nonempty_finite_list("values", values)
    if method not in ("median", "mean", "trimmed_mean"):
        raise ValueError("method must be 'median', 'mean' or 'trimmed_mean'")
    ordered = sorted(series)
    n = len(series)
    if method == "median":
        mid = n // 2
        normalized = ordered[mid] if n % 2 == 1 else (ordered[mid - 1] + ordered[mid]) / 2.0
    elif method == "trimmed_mean":
        cut = int(n * 0.1)
        kept = ordered[cut:n - cut] if cut else ordered
        normalized = sum(kept) / len(kept)
    else:
        normalized = sum(series) / n
    return {
        "model": "normalize_cycle",
        "method": method,
        "n_years": n,
        "normalized_value": normalized,
        "min": ordered[0],
        "max": ordered[-1],
        "note": "Normalization is only as good as the cycle coverage of the input series.",
    }


def reverse_dcf_growth(
    fcff: Sequence[float],
    wacc: float,
    diluted_shares: float,
    target_price: float,
    net_debt: float = 0.0,
    non_operating_assets: float = 0.0,
    minority_interest: float = 0.0,
    preferred_equity: float = 0.0,
    g_lower: float = -0.5,
    g_upper: float | None = None,
) -> dict[str, Any]:
    """Solve the terminal growth rate g that makes dcf_fcff equal target_price.

    Descriptive of what the current price implies under this forecast - NOT
    independent evidence that the price is fair. Value per share is monotone
    increasing in g, so bisection is stable inside the bracket
    (-1, wacc).
    """
    flows = _nonempty_finite_list("fcff", fcff)
    wacc_v = _discount_rate("wacc", wacc)
    shares = _finite("diluted_shares", diluted_shares)
    if shares <= 0:
        raise ValueError("diluted_shares must be > 0")
    target = _finite("target_price", target_price)
    lo = _finite("g_lower", g_lower)
    hi = _finite("g_upper", wacc_v - 1e-6 if g_upper is None else g_upper)
    if not -1.0 < lo < hi <= wacc_v:
        raise ValueError("require -1 < g_lower < g_upper <= wacc")

    def f(g: float) -> float:
        return dcf_fcff(
            flows, wacc_v, g, shares, net_debt, non_operating_assets,
            minority_interest, preferred_equity,
        )["value_per_share"] - target

    if f(lo) > 0:
        return {
            "model": "reverse_dcf_growth",
            "status": "target_below_min_modelled_value",
            "implied_terminal_growth": None,
            "value_at_g_lower": f(lo) + target,
            "bracket": [lo, hi],
            "wacc": wacc_v,
            "interpretation": (
                "Even the lowest-growth scenario in the bracket values the equity above the target "
                "price; the price sits below the entire modelled range"
            ),
        }
    sol = bisect_root(f, lo, hi)
    g_star = sol["root"]
    value = dcf_fcff(
        flows, wacc_v, g_star, shares, net_debt, non_operating_assets,
        minority_interest, preferred_equity,
    )["value_per_share"]
    return {
        "model": "reverse_dcf_growth",
        "status": "solved",
        "implied_terminal_growth": g_star,
        "value_at_solution": value,
        "residual": value - target,
        "bracket": [lo, hi],
        "wacc": wacc_v,
        "converged": sol["converged"],
        "iterations": sol["iterations"],
        "interpretation": (
            "The terminal growth rate the current price implies under this forecast. Descriptive "
            "of market pricing, not independent validation; compare with your defensible g range"
        ),
    }


def reverse_dcf_wacc(
    fcff: Sequence[float],
    terminal_growth: float,
    diluted_shares: float,
    target_price: float,
    net_debt: float = 0.0,
    non_operating_assets: float = 0.0,
    minority_interest: float = 0.0,
    preferred_equity: float = 0.0,
    wacc_lower: float | None = None,
    wacc_upper: float = 3.0,
) -> dict[str, Any]:
    """Solve the WACC at which dcf_fcff equals target_price (break-even rate).

    Value per share is monotone decreasing in WACC, so bisection is stable.
    Compare the break-even WACC with your estimated WACC: a large gap flags
    discount-rate sensitivity - report it instead of forcing a verdict.
    """
    flows = _nonempty_finite_list("fcff", fcff)
    g = _finite("terminal_growth", terminal_growth)
    if g <= -1:
        raise ValueError("terminal_growth must be > -100%")
    shares = _finite("diluted_shares", diluted_shares)
    if shares <= 0:
        raise ValueError("diluted_shares must be > 0")
    target = _finite("target_price", target_price)
    lo = _finite("wacc_lower", g + 1e-9 if wacc_lower is None else wacc_lower)
    hi = _finite("wacc_upper", wacc_upper)
    if not g < lo < hi:
        raise ValueError("require terminal_growth < wacc_lower < wacc_upper")

    def f(w: float) -> float:
        return dcf_fcff(
            flows, w, g, shares, net_debt, non_operating_assets,
            minority_interest, preferred_equity,
        )["value_per_share"] - target

    if f(hi) > 0:
        return {
            "model": "reverse_dcf_wacc",
            "status": "target_below_value_at_max_rate",
            "break_even_wacc": None,
            "value_at_wacc_upper": f(hi) + target,
            "terminal_growth": g,
            "interpretation": (
                "Even a 300% discount rate values the equity above the target price; the price is "
                "below every plausible discount rate under this forecast"
            ),
        }
    sol = bisect_root(f, lo, hi)
    w_star = sol["root"]
    value = dcf_fcff(
        flows, w_star, g, shares, net_debt, non_operating_assets,
        minority_interest, preferred_equity,
    )["value_per_share"]
    return {
        "model": "reverse_dcf_wacc",
        "status": "solved",
        "break_even_wacc": w_star,
        "value_at_solution": value,
        "residual": value - target,
        "terminal_growth": g,
        "converged": sol["converged"],
        "iterations": sol["iterations"],
        "interpretation": (
            "Break-even WACC: the discount rate at which the model equals the current price. "
            "Descriptive of market pricing; compare with the estimated WACC and report the gap"
        ),
    }


def reverse_dcf_fcff_scale(
    fcff: Sequence[float],
    wacc: float,
    terminal_growth: float,
    diluted_shares: float,
    target_price: float,
    net_debt: float = 0.0,
    non_operating_assets: float = 0.0,
    minority_interest: float = 0.0,
    preferred_equity: float = 0.0,
) -> dict[str, Any]:
    """Solve the uniform scaling k of every explicit FCFF (and the terminal
    flow) that makes dcf_fcff equal target_price.

    Equity value is exactly linear in the flow scale, so this is solved
    algebraically rather than by iteration: k = (target x shares - bridge) / EV.
    A proxy for the cash-flow level (margins, volumes) the market price implies.
    """
    flows = _nonempty_finite_list("fcff", fcff)
    wacc_v = _discount_rate("wacc", wacc)
    g = _finite("terminal_growth", terminal_growth)
    if g <= -1:
        raise ValueError("terminal_growth must be > -100%")
    shares = _finite("diluted_shares", diluted_shares)
    if shares <= 0:
        raise ValueError("diluted_shares must be > 0")
    target = _finite("target_price", target_price)

    base = dcf_fcff(
        flows, wacc_v, g, shares, net_debt, non_operating_assets,
        minority_interest, preferred_equity,
    )
    ev = base["enterprise_value"]
    bridge = base["equity_value"] - ev  # -net_debt + non-operating assets - minority - preferred

    if ev <= 0:
        return {
            "model": "reverse_dcf_fcff_scale",
            "status": "no_positive_scale_solution",
            "implied_flow_scale": None,
            "enterprise_value_at_unit_scale": ev,
            "interpretation": (
                "Unit-scale enterprise value is not positive; no positive flow scale equates the "
                "model to the target price"
            ),
        }
    k = (target * shares - bridge) / ev
    if k <= 0:
        return {
            "model": "reverse_dcf_fcff_scale",
            "status": "non_positive_scale",
            "implied_flow_scale": k,
            "interpretation": (
                "The implied flow scale is not positive; the target price is below the "
                "enterprise-to-equity bridge value alone"
            ),
        }
    value = (k * ev + bridge) / shares
    return {
        "model": "reverse_dcf_fcff_scale",
        "status": "solved",
        "implied_flow_scale": k,
        "value_at_solution": value,
        "residual": value - target,
        "interpretation": (
            "Uniform scaling of every explicit FCFF (and the terminal flow) that equates model "
            "value to the current price; a proxy for the market's implied cash-flow level"
        ),
    }


def reverse_ddm_ke(
    dividends_per_share: Sequence[float],
    target_price: float,
    terminal_growth: float,
    ke_lower: float | None = None,
    ke_upper: float = 1.0,
) -> dict[str, Any]:
    """Solve the Ke at which ddm equals target_price (break-even Ke).

    Value per share is monotone decreasing in Ke. The break-even Ke is the
    single most honest number when the cheap/fair/expensive classification
    flips across the plausible Ke range.
    """
    dividends = _nonempty_finite_list("dividends_per_share", dividends_per_share)
    g = _finite("terminal_growth", terminal_growth)
    if g <= -1:
        raise ValueError("terminal_growth must be > -100%")
    target = _finite("target_price", target_price)
    lo = _finite("ke_lower", g + 1e-9 if ke_lower is None else ke_lower)
    hi = _finite("ke_upper", ke_upper)
    if not g < lo < hi:
        raise ValueError("require terminal_growth < ke_lower < ke_upper")

    def f(ke: float) -> float:
        return ddm(dividends, ke, g)["value_per_share"] - target

    if f(hi) > 0:
        return {
            "model": "reverse_ddm_ke",
            "status": "target_below_value_at_max_ke",
            "break_even_ke": None,
            "value_at_ke_upper": f(hi) + target,
            "terminal_growth": g,
            "interpretation": (
                "Even a 100% cost of equity values the share above the target price; the price is "
                "below every plausible discount rate under this dividend forecast"
            ),
        }
    sol = bisect_root(f, lo, hi)
    ke_star = sol["root"]
    value = ddm(dividends, ke_star, g)["value_per_share"]
    return {
        "model": "reverse_ddm_ke",
        "status": "solved",
        "break_even_ke": ke_star,
        "value_at_solution": value,
        "residual": value - target,
        "terminal_growth": g,
        "converged": sol["converged"],
        "iterations": sol["iterations"],
        "interpretation": (
            "Break-even Ke: the cost of equity at which the DDM equals the current price. "
            "Descriptive of market pricing; compare with the estimated Ke range and report the gap"
        ),
    }


# Default model routing by company type. These are starting points chosen from
# cash-flow predictability, dividend policy, life cycle, capital structure and
# data quality - not mandates. A documented override (e.g. a dividend payer
# with an erratic payout switching to FCFE as primary) must state why the
# default does not fit. Unknown types error out rather than guess.
DEFAULT_ROUTING: dict[str, dict[str, Any]] = {
    "bank": {
        "primary": "ddm",
        "secondary": ["residual_income"],
        "refuse_if": "recapitalisation, sharp asset-quality shifts, or payout not forecastable",
    },
    "insurer": {
        "primary": "pev",
        "secondary": ["residual_income"],
        "refuse_if": "embedded-value assumptions unverifiable or new-business value persistently negative",
    },
    "dividend_payer": {
        "primary": "ddm",
        "secondary": ["fcfe"],
        "refuse_if": "dividends persistently diverge from the capacity to pay",
    },
    "consumer_manufacturing": {
        "primary": "dcf_fcff",
        "secondary": ["fcfe"],
        "refuse_if": "operating cash flows not forecastable from disclosures",
    },
    "cyclical_resource": {
        "primary": "dcf_fcff",
        "secondary": ["normalize_cycle"],
        "refuse_if": "structural break not identified, or only a single-point commodity price is available",
    },
    "growth": {
        "primary": "dcf_fcff",
        "secondary": [],
        "refuse_if": "no defensible revenue and margin path",
    },
    "real_estate": {
        "primary": "nav",
        "secondary": ["dcf_fcff"],
        "refuse_if": "underlying assets cannot be reliably revalued",
    },
    "reit": {
        "primary": "affo",
        "secondary": ["nav"],
        "refuse_if": "AFFO / distributable cash flow not forecastable",
    },
}


def route_model(company_type: str) -> dict[str, Any]:
    """Return the default routing for a company type (copy; safe to mutate)."""
    key = str(company_type).strip().lower()
    if key not in DEFAULT_ROUTING:
        raise ValueError(
            "unknown company_type; expected one of: " + ", ".join(sorted(DEFAULT_ROUTING))
        )
    route = dict(DEFAULT_ROUTING[key])
    route["company_type"] = key
    return route


_METADATA_KEYS = ("currency", "unit", "as_of", "price_as_of")


def _validate_metadata(payload: dict[str, Any]) -> dict[str, str]:
    """Optional top-level currency / unit / as-of declarations.

    When present they must be non-empty strings; they are echoed into the
    output so a calculation can be reproduced with its declared basis.
    """
    meta: dict[str, str] = {}
    for key in _METADATA_KEYS:
        if key in payload:
            value = payload[key]
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{key} must be a non-empty string when declared")
            meta[key] = value.strip()
    return meta


def check_units(declarations: dict[str, Any]) -> dict[str, Any]:
    """Declared-unit consistency guard.

    Keys are field names, values are unit strings (or None = undeclared).
    Conflicting declared units raise ValueError; undeclared fields produce a
    warning so gaps stay visible instead of silently assumed consistent.
    """
    if not isinstance(declarations, dict):
        raise ValueError("declarations must be a dict")
    warnings: list[str] = []
    grouped: dict[str, list[str]] = {}
    for field, unit in declarations.items():
        if unit is None:
            warnings.append(f"{field}: unit not declared; state currency and scale in the report")
            continue
        if not isinstance(unit, str) or not unit.strip():
            raise ValueError(f"{field}: unit must be a non-empty string or None")
        grouped.setdefault(unit.strip(), []).append(str(field))
    if len(grouped) > 1:
        detail = "; ".join(f"'{u}' used by {fields}" for u, fields in grouped.items())
        raise ValueError(f"unit conflict: {detail}")
    return {"consistent": True, "declared_units": {u: fs for u, fs in grouped.items()},
            "warnings": warnings}


def _run_model(payload: dict[str, Any]) -> dict[str, Any]:
    model = payload.get("model")
    if model == "dcf_fcff":
        return dcf_fcff(
            payload["fcff"], payload["wacc"], payload.get("terminal_growth"),
            payload["diluted_shares"], payload.get("net_debt", 0),
            payload.get("non_operating_assets", 0), payload.get("minority_interest", 0),
            payload.get("preferred_equity", 0),
            terminal_method=payload.get("terminal_method", "gordon"),
            ebitda=payload.get("ebitda"), exit_ev_ebitda=payload.get("exit_ev_ebitda"),
        )
    if model == "ddm":
        return ddm(payload["dividends_per_share"], payload["ke"], payload["terminal_growth"])
    if model == "dcf_sensitivity":
        return dcf_sensitivity(
            payload["fcff"], payload["wacc_values"], payload["growth_values"],
            payload["diluted_shares"], payload.get("net_debt", 0),
            payload.get("non_operating_assets", 0), payload.get("minority_interest", 0),
            payload.get("preferred_equity", 0),
        )
    if model == "ddm_sensitivity":
        return ddm_sensitivity(payload["dividends_per_share"], payload["ke_values"], payload["growth_values"])
    if model == "fcfe":
        return fcfe(
            payload["fcfe"], payload["ke"], payload["terminal_growth"], payload["diluted_shares"]
        )
    if model == "residual_income":
        return residual_income(
            payload["bvps"], payload["roe_path"], payload["payout"],
            payload["ke"], payload["terminal_roe"], payload["terminal_book_growth"],
        )
    if model == "pev":
        return pev(
            payload["embedded_value"], payload["pev_multiple"], payload["shares"],
            payload.get("holdco_discount", 0.0),
        )
    if model == "nav":
        return nav(
            payload["asset_values"], payload["liabilities"], payload["shares"],
            payload.get("scenario", "base"),
        )
    if model == "affo":
        return affo(payload["affo_per_share"], payload.get("cap_rate"), payload.get("multiple"))
    if model == "reit_noi":
        return reit_noi(
            payload["noi"], payload["property_cap_rate"], payload["liabilities"],
            payload["shares"], payload.get("other_assets", 0.0), payload.get("scenario", "base"),
        )
    if model == "comparable_multiples":
        return comparable_multiples(payload)
    if model == "normalize_cycle":
        return normalize_cycle(payload["values"], payload.get("method", "median"))
    if model == "reverse_dcf_growth":
        return reverse_dcf_growth(
            payload["fcff"], payload["wacc"], payload["diluted_shares"], payload["target_price"],
            payload.get("net_debt", 0), payload.get("non_operating_assets", 0),
            payload.get("minority_interest", 0), payload.get("preferred_equity", 0),
            payload.get("g_lower", -0.5), payload.get("g_upper"),
        )
    if model == "reverse_dcf_wacc":
        return reverse_dcf_wacc(
            payload["fcff"], payload["terminal_growth"], payload["diluted_shares"],
            payload["target_price"], payload.get("net_debt", 0),
            payload.get("non_operating_assets", 0), payload.get("minority_interest", 0),
            payload.get("preferred_equity", 0), payload.get("wacc_lower"), payload.get("wacc_upper", 3.0),
        )
    if model == "reverse_dcf_fcff_scale":
        return reverse_dcf_fcff_scale(
            payload["fcff"], payload["wacc"], payload["terminal_growth"],
            payload["diluted_shares"], payload["target_price"], payload.get("net_debt", 0),
            payload.get("non_operating_assets", 0), payload.get("minority_interest", 0),
            payload.get("preferred_equity", 0),
        )
    if model == "reverse_ddm_ke":
        return reverse_ddm_ke(
            payload["dividends_per_share"], payload["target_price"], payload["terminal_growth"],
            payload.get("ke_lower"), payload.get("ke_upper", 1.0),
        )
    if model == "route":
        return route_model(payload["company_type"])
    if model in ("capm_ke", "build_up_ke", "unlever_beta", "relever_beta",
                 "bottom_up_beta", "wacc", "ke_scenario"):
        return ke_wacc.run_payload(payload)
    raise ValueError(
        "model must be dcf_fcff, ddm, dcf_sensitivity, ddm_sensitivity, fcfe, "
        "residual_income, pev, nav, affo, reit_noi, comparable_multiples, normalize_cycle, "
        "reverse_dcf_growth, reverse_dcf_wacc, reverse_dcf_fcff_scale, reverse_ddm_ke, route, "
        "capm_ke, build_up_ke, unlever_beta, relever_beta, bottom_up_beta, wacc, or ke_scenario"
    )


def run_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate metadata, dispatch, then echo the input for reproducibility."""
    if not isinstance(payload, dict):
        raise ValueError("Input JSON must be an object")
    meta = _validate_metadata(payload)
    result = _run_model(payload)
    if isinstance(result, dict):
        result["input_metadata"] = meta
        result["input_echo"] = payload
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", help="JSON input file; use - or omit to read stdin")
    args = parser.parse_args()
    try:
        if args.input and args.input != "-":
            payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
        else:
            payload = json.load(sys.stdin)
        result = run_payload(payload)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
