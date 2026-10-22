# Cash-flow models: FCFF, FCFE, normalization, staged DCF

## FCFF-DCF (consumer / manufacturing, and normalized cyclicals)

`FCFF = EBIT x (1 - operating tax rate) + D&A - capex - change in operating NWC`

Discount FCFF at WACC to estimate enterprise value. Convert enterprise value to common equity value only after accounting for net debt, non-operating assets, preferred claims, and non-controlling interests. Do not count an asset or liability twice (if net debt already subtracts cash, do not add the same cash as a non-operating asset).

- Forecast business drivers (volume, price, margin, capex intensity, working capital) rather than extrapolating a single CAGR.
- Payload: `{"model": "dcf_fcff", "fcff": [...], "wacc": ..., "terminal_growth": ..., "diluted_shares": ..., "net_debt": ..., "non_operating_assets": ..., "minority_interest": ..., "preferred_equity": ...}`

## FCFE-DCF (dividend payers as secondary, leveraged manufacturers)

`Equity value per share = PV(FCFE) + PV(terminal value)`, discounted at Ke.

FCFE is cash flow to common shareholders after debt service and reinvestment, so it is already an equity flow: **no enterprise-to-equity bridge**. Use FCFE when equity cash flow and future net borrowing can be forecast directly. Forecast the cash actually distributable - do not relabel FCFE as "dividends".

- With a stable capital structure, FCFF and FCFE equity values should land in the same neighbourhood; a large gap flags inconsistent debt, cash or reinvestment assumptions. Diagnose it; do not average.
- Payload: `{"model": "fcfe", "fcfe": [...], "ke": ..., "terminal_growth": ..., "diluted_shares": ...}`

## Mid-cycle normalization (cyclical / resource)

Before any DCF on a cyclical, normalize earnings or cash flow across a full cycle:

- Use a series that spans at least one complete cycle. A series covering only a boom or only a trough normalizes to the wrong level.
- `normalize_cycle` returns the median (default) or mean of the input series with min/max for context. Median is the default because a single extreme year distorts the mean.
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
