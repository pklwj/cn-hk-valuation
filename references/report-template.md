# Report template

## 1. Conclusion at a glance

- Security / market / valuation date / price:
- Latest financial period and data cutoff:
- Fundamental status: improving / broadly stable / deteriorating / structurally deteriorating / insufficient evidence
- Primary model and why it fits:
- Value range: bear / base / bull:
- Valuation state: below range / within range / above range / rate-sensitive / insufficient basis
- Confidence: high / medium / low, with reasons

## 2. Fundamental check

Summarize the most material changes versus the prior comparable period and 3-5 year trend where available. Explain the causes. Separate temporary, cyclical and structural drivers. Note important data gaps.

## 3. Model and inputs

**Model routing record:** primary model, secondary cross-check, models rejected or limited and why. If the default routing was overridden, state why the default did not fit.

For every material input, identify [Fact], [Calculated], or [Assumption], as well as period, units, currency and source. State the model form (FCFF / FCFE / DDM / RI / P-EV / NAV / AFFO) and why it is appropriate.

## 4. Valuation scenarios

| Scenario | Operating assumptions | Discount rate / cap rate / multiple | Terminal growth / method | Value per share |
|---|---|---|---|---|
| Bear | | | | |
| Base | | | | |
| Bull | | | | |

Show sufficient intermediate calculations to reproduce the base case. For FCFF, show the terminal value share of enterprise value, the terminal method (Gordon growth with its `g`, or the exit multiple with the comparable basis and the implied perpetuity growth it back-solves to), and the equity bridge. For DDM, show dividends forecast for each explicit year and terminal value. For RI, show the ROE path and book-value roll-forward. For P/EV, show the EV source and multiple evidence. For NAV, show asset-by-asset values with bases. For AFFO, show the FFO-to-AFFO bridge and cap-rate/multiple evidence.

## 5. Sensitivity, reverse valuation and parameters

Show Ke/WACC (or cap rate / EV multiple) x terminal-growth sensitivity where applicable, plus any single-variable sensitivity the primary model needs. State which parameters are held constant. If the conclusion changes under reasonable inputs, report "sensitive to assumptions" rather than selecting the favorable result. Report break-even parameters explicitly. Reverse-solved Ke, cap rate or multiple is descriptive of current market pricing, not independent validation.

Include the reverse-solver results (`reverse_dcf_growth`, `reverse_dcf_wacc`, `reverse_dcf_fcff_scale`, `reverse_ddm_ke`) beside the defensible range.

## 5a. Cost-of-capital audit trail

Per the Ke/WACC module output, for each scenario (bear/base/bull):

- the estimate and the formula;
- every key input with source and as-of date (risk-free rate and tenor; ERP method, market and source; beta window, frequency, standard error, R-squared; cost of debt basis; weights and their basis; tax rate);
- intermediate results (beta x ERP, unlevered/relevered betas, WACC legs);
- the parameter with the largest valuation impact and why;
- warnings: provenance gaps, beta reliability, possible premium double counting, assumption-driven debt cost.

## 5b. Margin of safety and target return (kept separate)

- Intrinsic value range from the models above (at the company's estimated Ke/WACC).
- Buy price at the investor's required return, labelled "buy price at a X% required return" - never relabelled as intrinsic value.
- The margin of safety applied once, at the decision layer, with its size and reason. It must not be baked into Ke/WACC and must not be counted twice.

## 6. Model divergence diagnosis

When primary and secondary models disagree, diagnose: forecast period alignment, share count, units, currencies, debt/cash treatment, rate definitions, retained cash and reinvestment, payout policy, regulatory capital, financing. State which model is trusted more and why. **Never average model results mechanically.** If no model is valid with available inputs, return "insufficient basis for a reliable valuation".

## 7. Risks and falsification conditions

List the 3-5 factors most likely to invalidate the valuation, with observable indicators and the next reporting date/event to check.

## 8. Sources and limitations

List primary documents and relevant pages/tables. State data gaps, model limitations, and whether the conclusion is robust or assumption-sensitive.

## 9. Valuation record (for future updates)

One line, kept with the report: `date | ticker | price | model(s) | bear/base/bull value | verdict | key assumptions (Ke/g or cap rate/multiple, payout)`. The next update on the same security must diff against this record and state what changed.
