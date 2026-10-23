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

Record every material input in a research ledger (value, unit, currency, period, status, source/source_type, as_of; `rationale` for assumptions, `formula`/`input_refs` for calculated figures). Before any calculation, run the ledger through `scripts/audit_ledger.py`: `python scripts/audit_ledger.py ledger.json` fails on missing provenance and warns on placeholder text, unknown records and date inconsistencies. A structural pass does not prove a source is real - verify material figures against primary filings (see `references/china-market.md`).

Freeze the period's inputs in a snapshot (`references/snapshot-format.md`) and gate it with `python scripts/snapshot.py check snapshot.json`. On a re-run, write a new snapshot rather than editing the old one and run `python scripts/snapshot.py diff old.json new.json`: a value that moved while its source and as-of date did not is a correction, not new information, and must be explained before it changes a verdict.

**Anti-overfitting (applies to every step below):** never change an input (WACC/Ke, terminal growth, exit multiple, normalization window, margin-of-safety threshold) because it would have produced a better outcome. Realized prices may test a model, never set its inputs. Use sensitivity grids to show where a verdict flips, not to search for the parameter that fits history. In historical tests, assert point-in-time inputs mechanically. See `references/anti-overfitting.md`.

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

### 5. Estimate the cost of capital, then calculate and test

Use `scripts/ke_wacc.py` for every Ke / WACC estimate (CAPM, build-up,
bottom-up beta, WACC, bear/base/bull scenarios). Hard rules:

- **No default rates.** There is no default Ke, no default ERP, no assumed
  cost of debt. Missing or unverifiable inputs raise; a refusal is a valid
  output. Never write "assume Ke = 10%".
- Every rate input carries source and as-of date (dict form) or triggers a
  provenance warning (bare number). Country-risk, size, industry and
  company-specific premia each need a written economic rationale; stacking is
  flagged when the ERP already includes country risk.
- **Financial entities (banks, insurers) are refused WACC.** Discount
  equity flows at Ke. A documented override must say why.
- Match the rate to the flow. Report the break-even Ke/WACC, not just a point.

Use `scripts/valuation.py` for deterministic calculations (standard library
only; all invalid inputs raise instead of guessing). If it cannot be run,
show the formulas and intermediate calculations so another person can
reproduce them.

| Model | Payload `model` | Discount rate | Module |
|---|---|---|---|
| FCFF-DCF (Gordon growth or exit-multiple terminal value) | `dcf_fcff` | WACC | `references/models-cashflow.md` |
| FCFE-DCF | `fcfe` | Ke | `references/models-cashflow.md` |
| DDM | `ddm` | Ke | `references/models-banks-insurers.md` |
| Residual income / PB-ROE | `residual_income` | Ke | `references/models-banks-insurers.md` |
| P/EV (insurers) | `pev` | multiple | `references/models-banks-insurers.md` |
| NAV / asset revaluation | `nav` | n/a (asset-based) | `references/models-assetbased.md` |
| REIT property cap rate | `reit_noi` | property cap rate on NOI | `references/models-assetbased.md` |
| AFFO (REITs) | `affo` | equity cap rate or multiple | `references/models-assetbased.md` |
| Mid-cycle normalization | `normalize_cycle` | n/a (helper) | `references/models-cashflow.md` |
| Comparable multiples (cross-check) | `comparable_multiples` | multiple | `references/models-cashflow.md` |
| Sensitivity matrices | `dcf_sensitivity`, `ddm_sensitivity` | varied | `references/ke-and-uncertainty.md` |
| Reverse DCF: implied growth / break-even WACC / implied flow scale | `reverse_dcf_growth`, `reverse_dcf_wacc`, `reverse_dcf_fcff_scale` | solved | `references/models-cashflow.md` |
| Reverse DDM: break-even Ke | `reverse_ddm_ke` | solved | `references/models-banks-insurers.md` |
| Ke estimation | `capm_ke`, `build_up_ke` | n/a | `references/ke-wacc-estimation.md` |
| Beta unlever / relever / bottom-up | `unlever_beta`, `relever_beta`, `bottom_up_beta` | n/a | `references/ke-wacc-estimation.md` |
| WACC estimation | `wacc` | n/a | `references/ke-wacc-estimation.md` |
| Ke scenarios | `ke_scenario` | n/a | `references/ke-wacc-estimation.md` |
| Default routing lookup | `route` | n/a | `references/model-routing.md` |

Match the rate to the flow: FCFF at WACC; FCFE, dividends and residual
income at Ke; NAV uses market asset values; REIT property valuation uses a
NOI-based property cap rate while AFFO uses an equity-level rate or multiple
- the two cap-rate bases are not interchangeable; P/EV uses a documented
multiple. Match nominal cash flows with nominal rates, and keep
currency/inflation assumptions consistent. Declare `currency` / `unit` /
`as_of` in the payload when known; the result echoes the input under
`input_echo` so the same inputs reproduce the same outputs.

Choose the terminal value method explicitly. `terminal_method: "gordon"`
(default) needs a positive terminal FCFF and a defensible `terminal_growth`;
`terminal_method: "exit_multiple"` needs an `ebitda` series aligned to the
forecast years plus `exit_ev_ebitda`, and stays usable when explicit FCFF is
still negative. Both return `terminal_value_share_of_ev`; the exit-multiple
route also returns `implied_perpetuity_growth` - the growth rate the multiple
implies. A warning on that figure is a contradiction to explain (or a lower
multiple to test), not something to suppress. An exit multiple is an
assumption about the terminal buyer, not market evidence of fair value.
Sensitivity matrices (`dcf_sensitivity`) are Gordon-only.

### 6. Challenge the conclusion

Before reporting a valuation:
- Check formula boundaries, units, share count, and any enterprise-to-equity bridge (no double counting of cash or assets).
- Show sensitivity to the key assumptions (Ke/WACC, terminal growth, cap rate, EV multiple as applicable).
- Show how much of total value comes from the terminal value or from a single assumption.
- Run the reverse solvers: `reverse_dcf_growth` (implied terminal growth), `reverse_dcf_wacc` (break-even WACC), `reverse_ddm_ke` (break-even Ke), `reverse_dcf_fcff_scale` (implied flow level). Report what the current price implies; this is descriptive of market pricing, never validation.
- If reasonable discount-rate or multiple assumptions reverse the valuation classification, state **discount-rate/multiple sensitive; no robust high/low valuation classification** and give the break-even parameter.
- Diagnose model divergence: align forecast periods, share count, units, currencies and rate definitions first; explain retained cash, reinvestment returns, payout policy, regulatory capital or financing differences. **Never average model results mechanically.**
- Do not use a market-implied Ke, cap rate or multiple reverse-solved from the current price as independent proof that the current price is fair.
- Report fundamental condition and valuation separately. A good company can be expensive; a weak company can be optically cheap.
- Present the investor's target return and margin of safety separately from the company's estimated cost of capital. If a target return is used to derive a buy price, label it "buy price at a X% required return", not "intrinsic value".

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
| REIT | AFFO / distributable cash flow (equity level) or `reit_noi` property cap rate (NOI level) | NAV | AFFO not forecastable; property NOI or cap-rate basis unverifiable |

## References to load on demand

- Routing principles, overrides, refusal rules: `references/model-routing.md`
- Banks and insurers: `references/models-banks-insurers.md`
- FCFF / FCFE / normalization / staged models: `references/models-cashflow.md`
- NAV / REITs: `references/models-assetbased.md`
- Ke, discount rates, cap rates and uncertainty (concepts): `references/ke-and-uncertainty.md`
- Ke / WACC estimation method, provenance rules, limitations: `references/ke-wacc-estimation.md`
- Mainland China / Hong Kong data rules: `references/china-market.md`
- Snapshot format, gate and diff semantics: `references/snapshot-format.md`
- Report structure: `references/report-template.md`
- Script, examples and tests: `scripts/valuation.py`, `scripts/ke_wacc.py`, `scripts/snapshot.py`, `examples/`, `tests/`

## Method references

- CFA Institute, *Free Cash Flow Valuation*: https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/free-cash-flow-valuation
- CFA Institute, *Discounted Dividend Valuation*: https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/discounted-dividend-valuation
- CFA Institute, *Equity Asset Valuation* (residual income, P/B-ROE) and *Market-Based Valuation* (P/EV, price multiples)
- Damodaran, *Valuing Financial Service Firms*: https://pages.stern.nyu.edu/~adamodar/pdfiles/papers/finfirm09.pdf
