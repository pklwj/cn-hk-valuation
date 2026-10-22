---
name: cn-hk-valuation
description: General valuation skill for mainland China A-shares and Hong Kong stocks. Given a ticker, screen fundamentals first, route to the right model by company type (bank, insurer, dividend payer, consumer/manufacturing, cyclical, growth, real estate, REIT), compute bear/base/bull value ranges with explicit assumptions and sensitivity, and produce a source-checked report. Refuses to value when data or model fit do not support it.
---

# China A-share / Hong Kong General Valuation

## Purpose

Answer two questions, in this order:
1. Has the company's fundamental condition improved, remained stable, or deteriorated?
2. Is the current price reasonable relative to a defensible value range?

This is an analysis tool, not a price-prediction engine. A refusal to value ("insufficient basis") is a valid output and is preferred over a forced number.

## Operating rules

- Keep the workflow compact. Load only the reference modules relevant to the company and question.
- Reuse prior research only after checking data freshness. Historical facts and business analysis may be reused; price, market parameters, share count, dividends, and valuation conclusions must be refreshed as relevant.
- Separate **[Fact]** company/market disclosures, **[Calculated]** values derived from sourced data, and **[Assumption]** forecasts or analyst choices.
- For every material number, record period, unit, currency, source, and retrieval/as-of date. Prefer official filings for reported financial facts. Third-party data can speed discovery and provide cross-checks, but do not silently substitute it for a conflicting source.
- Never invent missing data. If a critical input cannot be verified, mark it unknown and either widen the range, downgrade confidence, or withhold the affected conclusion.
- A formula test proves arithmetic consistency, not that the assumptions are true. State that distinction explicitly.

## Workflow

### 1. Establish the analysis basis

Identify security, market, share class, reporting currency, valuation date, latest available reporting period, current price, diluted share count, and user intent (fundamental check, valuation, or update). Do not use information published after the valuation date in historical tests.

### 2. Check fundamental condition

Compare at least the latest reported period with the comparable prior period and, where available, a 3-5 year history. Explain causes rather than merely listing ratios.

Review: revenue / operating income, normalized earnings, margins and ROE/ROIC; operating cash flow and cash conversion; capex and working-capital needs; debt, liquidity, asset impairment, dilution, related-party dealings, audit opinion; capital allocation, dividend sustainability, buybacks, reinvestment needs and competitive position; industry-specific indicators (for banks and insurers see `references/models-banks-insurers.md`).

Classify fundamentals as **improving / broadly stable / deteriorating / structurally deteriorating / insufficient evidence**. Give the evidence and the conditions that would change the classification. Do not collapse this into a single score.

### 3. Route the model

Use the routing table below; full rules and refusal conditions are in `references/model-routing.md`. State the chosen primary model, the secondary cross-check (if any), and why. A documented override of the default is allowed but must say why the default does not fit. If routing says refuse, refuse - do not force a valuation to cover the stock.

### 4. Build forecasts

- Normalize one-off earnings/cash-flow effects before projecting them forward. For cyclicals, normalize across a full cycle first (`scripts/valuation.py` model `normalize_cycle`; see `references/models-cashflow.md`).
- Forecast business drivers where practical; do not mechanically extrapolate a single historical CAGR.
- Keep revenue growth, margins, reinvestment, working capital, payout, and share-count assumptions economically consistent.
- Build bear/base/bull scenarios with explicit assumptions. Do not use Monte Carlo simulation unless the input distributions and dependencies have a defensible basis.

### 5. Calculate and test

Use `scripts/valuation.py` for deterministic calculations (standard library only; all invalid inputs raise instead of guessing). If it cannot be run, show the formulas and intermediate calculations so another person can reproduce them.

| Model | Payload `model` | Discount rate | Module |
|---|---|---|---|
| FCFF-DCF | `dcf_fcff` | WACC | `references/models-cashflow.md` |
| FCFE-DCF | `fcfe` | Ke | `references/models-cashflow.md` |
| DDM | `ddm` | Ke | `references/models-banks-insurers.md` |
| Residual income / PB-ROE | `residual_income` | Ke | `references/models-banks-insurers.md` |
| P/EV (insurers) | `pev` | multiple | `references/models-banks-insurers.md` |
| NAV / asset revaluation | `nav` | n/a (asset-based) | `references/models-assetbased.md` |
| AFFO (REITs) | `affo` | cap rate or multiple | `references/models-assetbased.md` |
| Mid-cycle normalization | `normalize_cycle` | n/a (helper) | `references/models-cashflow.md` |
| Sensitivity matrices | `dcf_sensitivity`, `ddm_sensitivity` | varied | `references/ke-and-uncertainty.md` |
| Default routing lookup | `route` | n/a | `references/model-routing.md` |

Match the rate to the flow: FCFF at WACC; FCFE, dividends and residual income at Ke; NAV and AFFO use market cap rates or multiples, not a Ke. Match nominal cash flows with nominal rates, and keep currency/inflation assumptions consistent.

### 6. Challenge the conclusion

Before reporting a valuation:
- Check formula boundaries, units, share count, and any enterprise-to-equity bridge (no double counting of cash or assets).
- Show sensitivity to the key assumptions (Ke/WACC, terminal growth, cap rate, EV multiple as applicable).
- Show how much of total value comes from the terminal value or from a single assumption.
- If reasonable discount-rate or multiple assumptions reverse the valuation classification, state **discount-rate/multiple sensitive; no robust high/low valuation classification** and give the break-even parameter.
- Diagnose model divergence: align forecast periods, share count, units, currencies and rate definitions first; explain retained cash, reinvestment returns, payout policy, regulatory capital or financing differences. **Never average model results mechanically.**
- Do not use a market-implied Ke, cap rate or multiple reverse-solved from the current price as independent proof that the current price is fair.
- Report fundamental condition and valuation separately. A good company can be expensive; a weak company can be optically cheap.

### 7. Report and keep a record

Use `references/report-template.md`. Keep a one-line dated record of every completed valuation (ticker, date, price, model, value range, verdict, key assumptions) so the next update can diff against it.

## Routing summary (defaults, not mandates)

| Company type | Primary | Secondary cross-check | Refuse when |
|---|---|---|---|
| Bank | DDM | Residual income / PB-ROE | Recapitalisation, sharp asset-quality shifts, payout not forecastable |
| Insurer | P/EV | Residual income | EV assumptions unverifiable or NBV persistently negative |
| Stable dividend payer | DDM | FCFE | Dividends persistently diverge from capacity to pay |
| Consumer / manufacturing | FCFF-DCF | FCFE | Operating cash flows not forecastable from disclosures |
| Cyclical / resource | FCFF-DCF on normalized earnings | `normalize_cycle` | Structural break unidentified, or only a single-point commodity price available |
| High-growth / loss-making | FCFF-DCF staged / scenario | (none default) | No defensible revenue and margin path |
| Real estate / asset holder | NAV + debt stress | FCFF-DCF | Underlying assets cannot be reliably revalued |
| REIT | AFFO / distributable cash flow | NAV | AFFO not forecastable |

## References to load on demand

- Routing principles, overrides, refusal rules: `references/model-routing.md`
- Banks and insurers: `references/models-banks-insurers.md`
- FCFF / FCFE / normalization / staged models: `references/models-cashflow.md`
- NAV / REITs: `references/models-assetbased.md`
- Ke, discount rates, cap rates and uncertainty: `references/ke-and-uncertainty.md`
- Mainland China / Hong Kong data rules: `references/china-market.md`
- Report structure: `references/report-template.md`
- Script, examples and tests: `scripts/valuation.py`, `examples/`, `tests/`

## Method references

- CFA Institute, *Free Cash Flow Valuation*: https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/free-cash-flow-valuation
- CFA Institute, *Discounted Dividend Valuation*: https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/discounted-dividend-valuation
- CFA Institute, *Equity Asset Valuation* (residual income, P/B-ROE) and *Market-Based Valuation* (P/EV, price multiples)
- Damodaran, *Valuing Financial Service Firms*: https://pages.stern.nyu.edu/~adamodar/pdfiles/papers/finfirm09.pdf
