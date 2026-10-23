# Cash-flow models: FCFF, FCFE, normalization, staged DCF

## FCFF-DCF (consumer / manufacturing, and normalized cyclicals)

`FCFF = EBIT x (1 - operating tax rate) + D&A - capex - change in operating NWC`

Discount FCFF at WACC to estimate enterprise value. Convert enterprise value to common equity value only after accounting for net debt, non-operating assets, preferred claims, and non-controlling interests. Do not count an asset or liability twice (if net debt already subtracts cash, do not add the same cash as a non-operating asset).

- Forecast business drivers (volume, price, margin, capex intensity, working capital) rather than extrapolating a single CAGR.
- The output carries `terminal_value_share_of_ev` plus a `warnings` entry when that share exceeds 75%: the estimate is then dominated by perpetuity assumptions, so stress the explicit-period flows and the terminal inputs before relying on the point estimate.
- Payload: `{"model": "dcf_fcff", "fcff": [...], "wacc": ..., "terminal_growth": ..., "diluted_shares": ..., "net_debt": ..., "non_operating_assets": ..., "minority_interest": ..., "preferred_equity": ...}`

### Terminal value: Gordon growth vs exit multiple

`terminal_method` selects the terminal value. Default is `"gordon"`.

| Method | Terminal value | Requires | Use when |
|---|---|---|---|
| `gordon` | `FCFF_n x (1 + g) / (WACC - g)` | `terminal_growth`, positive terminal FCFF | stable, mature economics; nominal g at or below long-run GDP/inflation compatible rate |
| `exit_multiple` | `exit_ev_ebitda x EBITDA_n` | `ebitda` series (one value per forecast year), positive terminal EBITDA | cyclicals, asset-heavy or M&A-driven businesses where a perpetuity growth rate is not interpretable |

Rules for `exit_multiple`:

- Justify the multiple from comparable transactions or trading levels observed **at the valuation date**, and record the comparable set. A multiple carried over from a different cycle is an assumption, not evidence.
- The output reports `implied_perpetuity_growth`, back-solved from the multiple. If the script warns that the implied growth is above a sustainable rate, at or above WACC, or negative beyond a small margin, the multiple and the terminal EBITDA are inconsistent - fix one of them or state why the residual is real.
- Negative explicit FCFF is allowed here (unlike Gordon), but the terminal year still needs positive EBITDA.
- Never present an exit multiple as "market-based" and therefore safer than Gordon. It is a different assumption, not less of one.
- `dcf_sensitivity` supports Gordon only; for exit-multiple sensitivity, vary `exit_ev_ebitda` in separate runs and tabulate the outcome.

Example: `examples/dcf-exit-multiple-example.json`.

## Trap: lease payments under the new lease standard (IFRS 16 / CAS 21)

Under the current lease standard, a lessee splits lease payments: the right-of-use asset
depreciation stays in operating cash flow (as a non-cash add-back), while **the principal and
interest of the lease liability are presented as financing cash outflows**. The consequence:

**reported operating cash flow is overstated and capex looks tiny, because the single largest
cash cost of the business never appears in either line.**

Sectors where this dominates: cinemas, outdoor/advertising media, retail and convenience
chains, restaurants, airlines, hotels, logistics warehousing, hospital chains.

Worked case — Focus Media 002027, FY2025 (all figures from the annual report and its notes):

| Line | CNY 100m |
|---|---|
| Reported operating cash flow | 72.09 |
| Capex (purchase of long-term assets) | 1.57 |
| **Reported FCF (naive)** | **70.52** |
| Elevator/cinema rent, presented under "other financing cash payments" | 26.43 |
| **True FCF after lease adjustment** | **44.09** |

Using the naive 70.52 as FCFF lifts the DCF value per share to 7.25 against a 4.96 price
(i.e. "32% cheap"); the lease-adjusted 44.09 gives 4.81 (+3%). The entire "it looks cheap"
signal was one reclassification line.

Always:
- read the cash-flow statement note for lease/right-of-use payments, and the financing section
  for "other financing cash payments" — do not stop at the operating total;
- cross-check by a second path from the bottom up: normalized earnings + D&A − maintenance
  capex. On Focus Media the two paths gave 44.09 and 40.12 against the skill's 42.20 —
  agreement within ~10% is the signal that the FCFF is sound;
- if lease cash outflows cannot be found, treat the reported FCF as an **upper bound** and say
  so explicitly rather than using it silently.

## FCFE-DCF (dividend payers as secondary, leveraged manufacturers)

`Equity value per share = PV(FCFE) + PV(terminal value)`, discounted at Ke.

FCFE is cash flow to common shareholders after debt service and reinvestment, so it is already an equity flow: **no enterprise-to-equity bridge**. Use FCFE when equity cash flow and future net borrowing can be forecast directly. Forecast the cash actually distributable - do not relabel FCFE as "dividends".

- With a stable capital structure, FCFF and FCFE equity values should land in the same neighbourhood; a large gap flags inconsistent debt, cash or reinvestment assumptions. Diagnose it; do not average.
- Payload: `{"model": "fcfe", "fcfe": [...], "ke": ..., "terminal_growth": ..., "diluted_shares": ...}`

## Mid-cycle normalization (cyclical / resource)

Before any DCF on a cyclical, normalize earnings or cash flow across a full cycle:

- Use a series that spans at least one complete cycle. A series covering only a boom or only a trough normalizes to the wrong level.
- `normalize_cycle` returns the median (default), mean or trimmed_mean (10% off each end) of the input series with min/max for context. Median is the default because a single extreme year distorts the mean.
- Check for a structural break (policy, technology, capacity, demand) before trusting any normalization; if history is irrelevant, say so.
- Then run the DCF on normalized flows with explicit bear/base/bull around the normalized level.

Payload: `{"model": "normalize_cycle", "values": [...], "method": "median"}`

## Staged / scenario DCF (high-growth, loss-making)

- Model explicit forecast years until margins and reinvestment stabilize, then a Gordon terminal value only after the terminal year is positive and the path is economically interpretable.
- Model the share-count path explicitly (dilution), not a single diluted figure, and the cash burn and funding runway that precede positive cash flow.
- Losses in early explicit years are allowed by the script; the terminal year must be positive for a Gordon-growth terminal value.
- The honest output is the scenario spread (bear/base/bull), not a point estimate. Pre-profit cross-checks are weak by nature; state that plainly.

## WACC discipline

- WACC applies to FCFF only. Do not discount FCFE, dividends or residual income at WACC, and do not discount FCFF at Ke.
- Keep the capital structure weights and cost components consistent with the cash-flow currency; document the source of each component and its as-of date.
- Estimate WACC with `scripts/ke_wacc.py` (model `wacc`); it enforces the cost-of-debt basis, weight-basis rationale and the financial-entity refusal. See `ke-wacc-estimation.md`.

## Reverse DCF: what the current price implies

Solvers in `scripts/valuation.py`; all are descriptive of market pricing, never independent validation:

- `reverse_dcf_growth` - the terminal growth rate g that makes the DCF equal the target price. If the implied g exceeds your defensible range, the market is pricing in more growth than you can justify.
- `reverse_dcf_wacc` - the break-even WACC. Compare with your estimated WACC; a large gap means the cheap/expensive verdict is rate-sensitive.
- `reverse_dcf_fcff_scale` - the uniform scaling of explicit FCFF (and the terminal flow) that equates model value to the target price; a proxy for the market's implied cash-flow level (margins, volumes).
- `reverse_ddm_ke` - the break-even Ke for a DDM (see `models-banks-insurers.md`).

Report the implied parameter next to your defensible range; when the price implies something you cannot support, say so instead of forcing a verdict.

## Comparable multiples (cross-check only)

`comparable_multiples` supports P/E, P/B, EV/EBITDA and P/AFFO with explicit bridges:

- EV/EBITDA bridges to equity as EV - net_debt (subtract minority/preferred claims where material; do not add back cash already netted).
- Every multiple names its comparable set and as-of date (dict form) or triggers a provenance warning.
- Use normalized metrics: mid-cycle EPS for P/E, latest audited BVPS for P/B, repeatable AFFO for P/AFFO.
- Relative valuation is a cross-check on intrinsic models. Never average multiple-based values with DCF/DDM outputs; diagnose the gap (growth, margins, reinvestment, risk) instead.
