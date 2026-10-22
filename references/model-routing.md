# Model routing: which valuation model, and when to refuse

Select based on cash-flow economics and forecastability, not the industry label alone. The table below gives defaults; the principles after the table govern overrides. A documented override must state why the default does not fit. When routing says refuse, refuse - a withheld conclusion is better than a manufactured number.

## Default routing by company type

| Type | Primary | Secondary | Key data | Refuse when |
|---|---|---|---|---|
| Bank | DDM | Residual income / PB-ROE | Payout policy, ROE, BVPS, capital adequacy, NIM, NPL, provision coverage | Recapitalisation period, sharp asset-quality shifts, payout not forecastable |
| Insurer | P/EV | Residual income, segment valuation | EV and EV assumptions, NBV / VNB margin, investment yield, solvency | EV assumptions unverifiable, NBV persistently negative, or insurance-specific data unavailable |
| Stable dividend payer | DDM | FCFE | Sustainable dividends, payout ratio, Ke | Dividends persistently diverge from capacity to pay |
| Consumer / manufacturing | FCFF-DCF | FCFE | Revenue drivers, margins, reinvestment, working capital | Operating cash flows not forecastable from disclosures |
| Cyclical / resource | FCFF-DCF on normalized earnings | `normalize_cycle` | Mid-cycle price / volume / unit margin, capacity cycle | Structural break (policy, technology, capacity, demand) not identified; only a single-point commodity price available |
| High-growth / loss-making | FCFF-DCF staged or scenario | (none default) | Revenue path, margin convergence, dilution, cash burn, funding runway | No defensible revenue and margin path |
| Real estate / asset holder | NAV + debt stress | FCFF-DCF | Asset-by-asset values with basis, debt maturities, funding costs | Underlying assets cannot be reliably revalued |
| REIT | AFFO / distributable cash flow | NAV | AFFO bridge, occupancy, lease profile, cap rates | AFFO / distributable cash flow not forecastable |

## Selection principles

1. **Cash-flow predictability first.** A model is only as good as the forecastability of its cash flow. Banks' operating cash flow is not meaningfully forecastable as FCFF; developers' NAV depends on revaluation quality; a retailer's FCFF depends on unit economics.
2. **Dividend policy matters.** DDM requires a discernible policy where dividends bear a reasonable relationship to sustainable equity cash flows. If dividends differ materially from capacity to pay, explain why before using DDM as the sole model - or route to FCFE.
3. **Life cycle matters.** Mature payers support DDM; growth companies need staged or scenario models; perpetual-growth models applied immediately to a loss-making company are a category error.
4. **Capital structure and regulatory capital.** For banks and insurers, capital requirements are a reinvestment constraint, not a financing detail. Do not treat "net income minus a loosely defined change in equity" as distributable.
5. **Data quality gates everything.** If the disclosures do not support the model's inputs, the routing answer is "insufficient basis", not a weaker model with invented inputs.

## Cyclical specifics

- Do not extrapolate peak or trough earnings as normal earnings. Normalize unit margins, volume/utilization, capex and working capital across a relevant cycle before any DCF.
- Examine whether policy, supply capacity, technology or demand has caused a structural break; if history is irrelevant, say so and use scenario analysis or refuse.
- A single implied commodity price is inappropriate for multi-product firms, long-term contracts, integrated businesses, or firms with material hedges; model the key drivers separately.

## Growth / loss-making specifics

- Use a staged or scenario DCF: explicit forecast years until the path is defensible, then a terminal value only after margins and reinvestment stabilize.
- Model dilution explicitly (share count path, not a single diluted figure) and the cash burn / funding runway that precedes positive cash flow.
- Cross-checks for pre-profit companies are weak by nature; state that plainly rather than importing a multiple as "validation".

## Model-conflict rules

- DCF, DDM, RI, P/EV and NAV use different value definitions; a gap is a diagnostic clue, not automatic proof that either model is right.
- First align forecast periods, share count, units, currencies, debt/cash treatment and discount-rate definitions.
- Explain retained cash, reinvestment returns, required regulatory capital, debt repayment, excess cash, buybacks, or unreliable payouts.
- **Never average model results mechanically.** Report the range, diagnose the gap, and say which model you trust more and why.
- If no model is valid with available inputs, return "insufficient basis for a reliable valuation" rather than manufacturing a number.
