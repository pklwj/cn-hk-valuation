#!/usr/bin/env python3
"""Deterministic valuation calculators for China A-share / Hong Kong stocks.
Python standard library only.

Models: FCFF-DCF (dcf_fcff), DDM (ddm), FCFE (fcfe), residual income / PB-ROE
(residual_income), P/EV for insurers (pev), asset-based NAV (nav), AFFO-based
REIT valuation (affo), mid-cycle normalization (normalize_cycle), plus
sensitivity matrices (dcf_sensitivity, ddm_sensitivity) and a default
model-routing table by company type (route_model).

Units: keep monetary units consistent. For example, if FCFF is RMB million and
shares are million shares, the calculated per-share value is RMB/share.

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


def dcf_fcff(
    fcff: Sequence[float],
    wacc: float,
    terminal_growth: float,
    diluted_shares: float,
    net_debt: float = 0.0,
    non_operating_assets: float = 0.0,
    minority_interest: float = 0.0,
    preferred_equity: float = 0.0,
) -> dict[str, Any]:
    """Value equity from annual FCFF forecasts using a Gordon-growth terminal value.

    net_debt = interest-bearing debt minus cash and cash equivalents already
    included in that definition. Do not include that same cash again in
    non_operating_assets. All amounts must use the same currency/unit.
    """
    flows = _nonempty_finite_list("fcff", fcff)
    wacc = _discount_rate("wacc", wacc)
    g = _finite("terminal_growth", terminal_growth)
    shares = _finite("diluted_shares", diluted_shares)
    if shares <= 0:
        raise ValueError("diluted_shares must be > 0")
    if g <= -1:
        raise ValueError("terminal_growth must be > -100%")
    if wacc <= g:
        raise ValueError("wacc must be greater than terminal_growth")
    if flows[-1] <= 0:
        raise ValueError("last explicit FCFF must be positive for a Gordon-growth terminal value; model the transition to positive stable cash flow explicitly")

    pv_flows = [cf / ((1.0 + wacc) ** year) for year, cf in enumerate(flows, start=1)]
    terminal_value = flows[-1] * (1.0 + g) / (wacc - g)
    pv_terminal = terminal_value / ((1.0 + wacc) ** len(flows))
    ev = sum(pv_flows) + pv_terminal

    nd = _finite("net_debt", net_debt)
    noa = _finite("non_operating_assets", non_operating_assets)
    mi = _finite("minority_interest", minority_interest)
    pref = _finite("preferred_equity", preferred_equity)
    equity = ev - nd + noa - mi - pref
    return {
        "model": "dcf_fcff",
        "currency_unit_note": "All inputs must use one consistent currency and scale.",
        "years": len(flows),
        "pv_explicit_fcff": sum(pv_flows),
        "terminal_value_at_year_n": terminal_value,
        "pv_terminal_value": pv_terminal,
        "terminal_value_share_of_ev": (pv_terminal / ev) if ev != 0 else None,
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
    return {
        "model": "ddm",
        "years": len(dividends),
        "pv_explicit_dividends_per_share": sum(pv_dividends),
        "terminal_dividend_per_share_d_n_plus_1": terminal_dividend,
        "terminal_value_at_year_n_per_share": terminal_value,
        "pv_terminal_value_per_share": pv_terminal,
        "terminal_value_share_of_total": (pv_terminal / value) if value != 0 else None,
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
    return {
        "model": "fcfe",
        "currency_unit_note": "All inputs must use one consistent currency and scale.",
        "years": len(flows),
        "pv_explicit_fcfe": sum(pv_flows),
        "terminal_value_at_year_n": terminal_value,
        "pv_terminal_value": pv_terminal,
        "terminal_value_share_of_total": (pv_terminal / equity_value) if equity_value != 0 else None,
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


def normalize_cycle(values: Sequence[float], method: str = "median") -> dict[str, Any]:
    """Mid-cycle normalization of a full-cycle annual series (EPS, unit margin, ...).

    The input series must span at least one full cycle; a series covering only
    a boom or only a trough normalizes to the wrong level. Check whether a
    structural break (policy, technology, capacity, demand) makes history
    irrelevant before trusting any normalization.
    """
    series = _nonempty_finite_list("values", values)
    if method not in ("median", "mean"):
        raise ValueError("method must be 'median' or 'mean'")
    ordered = sorted(series)
    n = len(series)
    if method == "median":
        mid = n // 2
        normalized = ordered[mid] if n % 2 == 1 else (ordered[mid - 1] + ordered[mid]) / 2.0
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


def run_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Input JSON must be an object")
    model = payload.get("model")
    if model == "dcf_fcff":
        return dcf_fcff(
            payload["fcff"], payload["wacc"], payload["terminal_growth"],
            payload["diluted_shares"], payload.get("net_debt", 0),
            payload.get("non_operating_assets", 0), payload.get("minority_interest", 0),
            payload.get("preferred_equity", 0),
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
    if model == "normalize_cycle":
        return normalize_cycle(payload["values"], payload.get("method", "median"))
    if model == "route":
        return route_model(payload["company_type"])
    raise ValueError(
        "model must be dcf_fcff, ddm, dcf_sensitivity, ddm_sensitivity, fcfe, "
        "residual_income, pev, nav, affo, normalize_cycle, or route"
    )


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
