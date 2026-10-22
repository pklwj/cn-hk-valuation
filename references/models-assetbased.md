# Asset-based models: NAV, revaluation, debt stress, REITs

## NAV / asset revaluation (real estate, asset holders)

`NAV per share = (sum of asset values - liabilities) / shares`

- Value assets item by item with a stated basis (market comparables, appraisal, or book) and pass each item separately: `{"model": "nav", "asset_values": [...], "liabilities": ..., "shares": ..., "scenario": "base"}`. A single blended number hides the valuation work and defeats stress testing.
- Include all material claims in liabilities: interest-bearing debt, minority interests in project companies, preferred claims, and known contingent liabilities. State what is excluded.
- Run at least two scenarios: base (current market evidence) and stress (revaluation haircut on assets, higher funding costs, debt maturities within the window). A negative stressed NAV is legitimate output and must be reported as such.
- Do not mix currencies: value assets and liabilities in one consistent currency, converting at a documented FX rate and as-of time.

## Debt stress scenarios

For leveraged asset holders, the question is usually not "what is the asset worth" but "does the capital structure survive". Model:
- Asset value decline sufficient to breach debt covenants or trigger margin calls.
- Refinancing of debt maturing within 12-24 months at current market rates.
- Distributable cash after debt service, taxes and maintenance capex.
State the covenant thresholds you used and their source; do not assume covenants you have not read.

## REITs: AFFO / distributable cash flow

`Value per share = AFFO / cap rate` or `Value per share = AFFO x multiple`

- AFFO must be a repeatable distributable figure: recurring maintenance capex deducted, straight-lining and one-off items removed. Show the FFO-to-AFFO bridge.
- The cap-rate method assumes a flat perpetuity; an observed market cap rate already embeds growth expectations. The multiple method uses comparable REIT trading multiples. Choose one and disclose the comparable set and as-of date.
- Cross-check with NAV (asset values less debt, often at a market cap rate) and report the gap; for REITs the AFFO/NAV gap usually traces to cap-rate selection, lease duration and occupancy quality - explain, do not average.
- For mainland public REITs and Hong Kong REITs, distributable income follows fund-level rules; use the fund's disclosed distributable amount, not a recomputed accounting figure, unless you can reconcile the difference.
- Payload: `{"model": "affo", "affo_per_share": ..., "cap_rate": ...}` or `{"model": "affo", "affo_per_share": ..., "multiple": ...}` (exactly one method).

## When to refuse

- Assets cannot be reliably revalued (no comparables, no appraisal, opaque related-party transfers).
- Liabilities are not disclosed in enough detail to model maturities and covenants.
- The fund/REIT's distributable figure cannot be reconciled to disclosed financials.
