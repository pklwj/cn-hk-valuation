# Ke / WACC estimation: method, provenance and limitations

Companion to `scripts/ke_wacc.py`. The script is the executable contract; this
document explains the method, the data conventions and where the estimates
break down. Load this only when a task needs cost-of-capital parameters.

## 0. Four parameters that must never be confused

| Parameter | Meaning | Where it belongs |
|---|---|---|
| Ke | Estimated cost of equity: the return shareholders require | DDM, FCFE, residual income |
| WACC | Blended cost of capital | FCFF only |
| Target return | The investor's personal hurdle | Buy-price calculation, clearly labelled |
| Margin of safety | Buffer for estimation error | Applied once, at the decision layer - never inside Ke/WACC, never double-counted |

A market-implied Ke (reverse-solved from the current price) describes the
price; it is not evidence that the price is fair.

## 1. Minimum provenance record

Every rate input is either a bare number (accepted, but the output carries a
provenance warning) or a dict:

```json
{"value": 0.01627, "source": "CN 10Y CGB yield to maturity, interbank 26附息国债16", "as_of": "2026-10-23", "currency": "CNY"}
```

Dict form **must** carry a non-empty `source` or the call raises. Missing
`as_of` raises a warning. Record in the final report, for each material input:
value, unit, currency, source, retrieval date, and whether it is disclosed,
calculated or assumed.

### 1.1 The risk-free rate must be the valuation date's quote

`as_of` for the risk-free rate means **the valuation date (or the latest
trading day before it)** — not the reporting period end, not the date the
snapshot was assembled, and never a rate carried over from a previous run.

- Source: the **10-year (or longer) CGB yield to maturity** on the valuation
  date (interbank / CNY curve; 国内评估口径同样要求"剩余期限 10 年期以上国债的
  到期收益率"). Quote the yield to maturity, not the coupon.
- Cross-check at least two sources when the rate matters to the verdict, and
  note any source disagreement in `notes`.
- Backtests use the rate **as of the historical valuation date**, never
  today's — same point-in-time discipline as any other input.
- `snapshot.py check` warns when a risk-free/CGB/FX quote is more than
  `max_market_age_days` (default 3, covering a weekend) older than
  `retrieved_at`.

Why this is a hard rule and not a nicety: Rf feeds Ke one-for-one. Reusing a
stale 2.1% Rf when the market is at 1.63% adds ~47bp to Ke and cuts the DCF
value by roughly 5% — with no arithmetic error anywhere, and nothing else in
the model would flag it. The example above is dated `2026-10-23` for exactly
this reason: an Rf record without a same-period `as_of` is an input that has
stopped tracking the market.

## 2. Ke estimation

### 2.1 CAPM (default framework, not gospel)

```
Ke = rf + beta x ERP + country-risk premium + size premium + company-specific premium
```

- **Risk-free rate**: match the currency and horizon of the cash flows. A CNH/HKD
  framework for RMB flows, or the reverse, is a category error. Record tenor and date.
- **Equity risk premium**: state method (historical / survey / implied), market
  (A-share, H-share, global) and source. A-share and H-share ERP estimates differ;
  do not silently mix them.
- **Beta**: record source, estimation window, frequency, standard error and
  R-squared where available. Reliability warnings fire at: standard error > 0.20,
  R-squared < 0.30, |beta| < 0.20, |beta| > 2.00. These are advisory conventions,
  not gates. A low observed beta for a large dividend payer is frequently a
  small-sample artefact - say so and use a range or a bottom-up beta.
- **Country risk**: decide first whether your ERP already contains it. If
  `erp_includes_country_risk` is true and a separate `country_risk_premium`
  is supplied, the module warns about double counting. The default treatment
  adds the premium linearly (conservative and auditable); a beta-scaled
  treatment is acceptable if documented.
- **Other premia** (size, industry, company-specific): each requires a written
  economic rationale, data source and calculation. No unexplained premia.
- **Generic premia** (`additional_premiums`): a list of
  `{label, rate, rationale, source}` for risks that do not fit the fixed keys
  (e.g. governance, liquidity, key-man). Every entry is provenance-checked the
  same way and stacked linearly; a warning reminds you to verify the risk is
  not already inside beta, the ERP or the cash-flow scenarios.

### 2.2 Beta from comparables (bottom-up)

```
beta_A,i = beta_L,i / (1 + (1 - t_i) x D/E_i)
beta_A   = sum(w_i x beta_A,i)                       (weights must be documented)
beta_L,target = beta_A x (1 + (1 - t_target) x D/E_target)
```

Use when the subject's own beta is unstable, the listing history is short, or
the capital structure is changing. Keep every unlevered beta, weight and the
relevering step in the audit trail. Weights: equal by default; negative or
all-zero weights are refused.

### 2.3 Build-up method

`Ke = rf + ERP + size + industry + company-specific premia` - for cases where
CAPM beta is unavailable or not meaningful (e.g. recently listed, distorted
trading history). Same rationale discipline per premium.

## 3. WACC estimation

```
WACC = E/V x Ke + D/V x Kd x (1 - t)
```

- **Cost of debt** must declare a basis:
  - `observed` - an actual financing cost with source and as-of date;
  - `spread_build_up` - risk-free rate + credit spread, both with provenance
    (the module computes the sum when no explicit value is given);
  - `assumption` - requires a written rationale and raises an
    "assumption-driven" warning. A fixed percentage without evidence is not
    acceptable.
- **Weights**: market value by default. Book weights require a rationale
  (why market weights are unavailable or misleading). Weights must sum to 1.
- **Tax rate**: marginal/effective distinction must be stated.
- **Financial entities**: banks, insurers and financial institutions are
  **refused** WACC - they discount equity flows (DDM / residual income / FCFE)
  at Ke. A documented override exists for genuine exceptions (e.g. a holding
  company's non-financial FCFF) and must say why.

## 4. Scenario construction (bear / base / bull)

- Each scenario is a full CAPM or build-up estimate with its own rationale -
  not a percentage haircut on the base rate.
- Convention: bear carries the conservative (higher) Ke. The module warns if
  bear < base or bull > base so inverted definitions are caught.
- A wider spread is a statement about uncertainty, not a licence to pick the
  favourable end. Recompute the valuation across the range, report the
  break-even Ke (`reverse_ddm_ke` / `reverse_dcf_wacc`), and label the
  conclusion rate-sensitive when the classification flips.

## 5. Data source conventions (A-share / H-share)

- Risk-free rate: China government bond yields from SSE / CNINFO / central
  bank publications; HKD framework from HKMA / HKSAR government bonds. Record
  tenor and as-of date.
- ERP: state the source and method; historical estimates need the window and
  averaging convention; survey or implied estimates need the publisher and date.
- Beta: exchange or data-provider estimate with window and frequency; record
  standard error and R-squared if published.
- Credit spread: the issuer's actual bond yields where traded, else a
  documented sector curve. Do not substitute a generic fixed spread without
  saying so.
- If any input cannot be verified, leave it out, widen the range, downgrade
  confidence, or refuse the valuation. Never fabricate a parameter to make a
  number appear.

## 6. Known limitations

- CAPM is a single-period, linear-risk model; it does not capture skewness,
  liquidity or distress risk explicitly. Any premium for those must be
  itemised with its own rationale (and risks double counting).
- Hamada unlevering assumes debt beta = 0 and a static target structure;
  document deviations.
- WACC is circular for rapidly re-levering companies (market weights move
  with the value being estimated); state the convention used (current market
  weights vs target) and its direction of bias.
- The module estimates parameters; it does not validate them against the
  market. Cross-check with reverse DCF (descriptive) and comparables, and
  report the range rather than a false point estimate.
