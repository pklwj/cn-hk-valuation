# Models for banks and insurers

## Banks

### DDM (primary)

`Equity value per share = PV(forecast dividends per share) + PV(terminal value per share)`

For a stable-growth terminal stage, `TV_n = D_(n+1) / (Ke - g_terminal)`, and `Ke` must be greater than `g_terminal`. Forecast dividends for years 1...n explicitly; terminal value starts with the dividend in year n+1.

- Forecast dividends actually expected to be paid, in the currency and share count they will be paid in. For Chinese banks with interim + final dividend structures, model each tranche's fiscal-year attribution and payment timing, and say which convention you used.
- Dividend capacity check: payout must be sustainable given regulatory capital (CET1 and buffers), risk-weighted asset growth, and other equity instrument distributions (preferred share dividends and perpetual bond coupons reduce the profit available to common shareholders). Cross-check EPS-implied payout against headline payout.
- Decide the tax basis before forecasting: gross dividends with a pre-tax Ke, or net dividends after the investor's withholding with an after-tax required return. Mainland A-share holding-period tax and Stock Connect's 20% withholding differ; see `china-market.md` and state which basis the value is on.
- Payload: `{"model": "ddm", "dividends_per_share": [...], "ke": ..., "terminal_growth": ...}`

### Residual income / PB-ROE (secondary)

`Value = BVPS_0 + sum PV(RI_t) + PV(terminal RI)`, where `RI_t = (ROE_t - Ke) x BVPS_{t-1}` and `BVPS_t = BVPS_{t-1} x (1 + (1 - payout) x ROE_t)`.

- Assumes clean-surplus accounting and no equity issuance; document capital raises, buybacks and OCI shocks separately.
- The terminal stage must have ROE converging toward (not permanently far above) Ke and a terminal book growth below Ke, otherwise the model does not converge.
- A negative residual income (value below book) is legitimate output.
- Payload: `{"model": "residual_income", "bvps": ..., "roe_path": [...], "payout": ..., "ke": ..., "terminal_roe": ..., "terminal_book_growth": ...}`

### Interpreting the DDM-RI gap

DDM values only distributed cash; RI also credits retained earnings that earn above Ke. For a bank with ROE above Ke and payout below capacity, RI will exceed DDM. The gap is a diagnostic about what the market believes sustainable ROE to be - report the gap and its cause, never average the two.

### What to track for banks

Net interest margin (NIM), loan growth, credit cost, non-performing loan ratio, provision coverage, loan migration rates (e.g. special-mention migration), capital adequacy ratios, ROE/ROA, payout, dilution. Note that falling provision coverage and rising migration rates are leading indicators of future credit cost even when the NPL ratio looks stable.

## Insurers

### P/EV (primary)

`Value per share = EV x multiple x (1 - holdco discount) / shares`

- Use embedded value (EV) as disclosed, with its assumptions (risk discount rate, investment yield) stated. If the EV assumptions are unverifiable or inconsistent with peers, treat the EV figure as unreliable and refuse or downgrade.
- The multiple must come from disclosed comparables or a documented cross-check. Do not reverse-solve the multiple from the current price and call that validation.
- Value of new business (VNB) / new business value is not automatically included; add it explicitly with a stated method (e.g. PV of VNB with a stated multiple) if used, and disclose it separately.
- Payload: `{"model": "pev", "embedded_value": ..., "pev_multiple": ..., "shares": ..., "holdco_discount": ...}`

### Secondary approaches

Residual income works when book value and ROE are meaningful; segment valuation (life vs P&C vs asset management) may fit conglomerates better. Choose one primary and cross-check with another; do not blend.

### What to track for insurers

EV and EV movement (operating vs investment variances), NBV and VNB margin, persistency, combined ratio for P&C, investment yield and asset duration mismatch, solvency ratio (e.g. C-ROSS II for mainland insurers), embedded value assumptions vs peers.

## Ke discipline for financials

Financial firms' Ke estimation is no less uncertain than for industrials. Apply the same rules as `ke-and-uncertainty.md`: disclose method and inputs, use a documented range, and report break-even Ke when the classification flips. A low observed beta for a large bank is often a statistical artefact; consider a bottom-up sector beta and say so.
