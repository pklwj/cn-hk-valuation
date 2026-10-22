# Ke, discount rates and uncertainty

## Keep three rates conceptually separate

1. **Model-estimated cost of equity (Ke):** a candidate estimate of required return, with method and inputs disclosed.
2. **Market-implied Ke:** a rate reverse-solved from current price and a specified cash-flow forecast. It describes what the price implies under that model; it is not independent evidence that the price is fair.
3. **Investor's target return:** a personal hurdle rate used to calculate an acceptable purchase price. It is not automatically the market's fair discount rate.

The same separation applies to WACC, cap rates and EV/P-EV multiples.

## CAPM is a reference, not a guaranteed answer

`Ke = risk-free rate + beta x equity risk premium`

- Match the risk-free rate to the cash-flow currency and a suitable horizon.
- Record the beta benchmark, lookback period, data frequency, use of total returns, standard error and R-squared where available.
- If beta is statistically weak, near zero, unstable, or inconsistent with observable business risk, do not treat the CAPM output as the sole Ke estimate. Consider a comparable-company bottom-up beta or other documented evidence where available. Low observed betas for large, dividend-paying financials are frequently statistical artefacts of a short or trending sample.
- Do not add an unexplained "China premium", liquidity premium, size premium or company premium automatically. State what risk it captures and avoid double counting.
- Do not claim CAPM universally fails for dividend stocks merely because beta is low; instead report the limitations of this estimate for the specific security.

## Use a documented Ke range

1. State a central assumption and why it is used.
2. State a defensible lower/upper range and the evidence for those bounds. Do not use the same fixed range for every stock.
3. Recalculate value across the range while holding other inputs constant, clearly labelling this as a single-variable sensitivity test.
4. Test joint bear/base/bull scenarios separately when earnings, payout, growth and rates are economically related.
5. If plausible Ke choices reverse "cheap / fair / expensive", do not force a binary classification. Report the break-even Ke and mark the valuation as rate-sensitive.

## Match the rate to the flow

- FCFF at WACC. FCFE, dividends and residual income at Ke. NAV uses market asset values; AFFO uses market cap rates or multiples; P/EV uses a documented multiple. Substituting a Ke where a market cap rate belongs (or the reverse) is a category error.
- Match discount-rate currency with cash-flow currency. If cash flows are forecast in RMB, use a consistent RMB nominal discount-rate framework; convert equity value to HKD using a documented FX rate if needed. Do not select a USD/HKD rate solely because the share trades in Hong Kong.
- Match nominal cash flows with nominal rates and real cash flows with real rates.
- In a stable-growth terminal stage, Ke must exceed terminal growth for DDM and residual income; WACC must exceed terminal growth for FCFF Gordon growth. Terminal book growth must stay below Ke in the RI model, otherwise it does not converge.
- Terminal growth should be economically defensible and consistent with long-run reinvestment and return on capital. Do not assume high perpetual growth with negligible reinvestment without justification.

## Sensitivity is not a probability

A sensitivity table shows what the model outputs under selected assumptions. Unless distributions and dependencies are supported, do not call it a probability distribution or claim a stated probability that intrinsic value falls within a range.

## Break-even discipline

Whenever the classification is sensitive to a parameter (Ke, WACC, terminal growth, cap rate, EV multiple), report the break-even value of that parameter explicitly. That single number is more honest than a forced verdict.
