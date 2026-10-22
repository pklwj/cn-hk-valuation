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

Show sufficient intermediate calculations to reproduce the base case. For FCFF, show terminal value share of enterprise value and the equity bridge. For DDM, show dividends forecast for each explicit year and terminal value. For RI, show the ROE path and book-value roll-forward. For P/EV, show the EV source and multiple evidence. For NAV, show asset-by-asset values with bases. For AFFO, show the FFO-to-AFFO bridge and cap-rate/multiple evidence.

## 5. Sensitivity and reverse valuation

Show Ke/WACC (or cap rate / EV multiple) x terminal-growth sensitivity where applicable, plus any single-variable sensitivity the primary model needs. State which parameters are held constant. If the conclusion changes under reasonable inputs, report "sensitive to assumptions" rather than selecting the favorable result. Report break-even parameters explicitly. Reverse-solved Ke, cap rate or multiple is descriptive of current market pricing, not independent validation.

## 6. Model divergence diagnosis

When primary and secondary models disagree, diagnose: forecast period alignment, share count, units, currencies, debt/cash treatment, rate definitions, retained cash and reinvestment, payout policy, regulatory capital, financing. State which model is trusted more and why. **Never average model results mechanically.** If no model is valid with available inputs, return "insufficient basis for a reliable valuation".

## 7. Risks and falsification conditions

List the 3-5 factors most likely to invalidate the valuation, with observable indicators and the next reporting date/event to check.

## 8. Sources and limitations

List primary documents and relevant pages/tables. State data gaps, model limitations, and whether the conclusion is robust or assumption-sensitive.

## 9. Valuation record (for future updates)

One line, kept with the report: `date | ticker | price | model(s) | bear/base/bull value | verdict | key assumptions (Ke/g or cap rate/multiple, payout)`. The next update on the same security must diff against this record and state what changed.
