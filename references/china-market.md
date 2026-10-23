# A-share / Hong Kong data and market conventions

## Data verification workflow

Data quality gates model complexity. Order of operations:

1. **Fetch from primary sources first**: exchange announcements, periodic reports, results announcements. CNINFO / SSE / SZSE for A-shares; HKEXnews for Hong Kong issuers.
2. **Record every core input** in the minimum record below before it enters any calculation.
3. **Classify each input**: [Fact] disclosed, [Calculated] derived from sourced data, [Assumption] your forecast or an analyst estimate. Never blur the three.
4. **Cross-check conflicts** against the original disclosure; when a third-party database disagrees with the filing, the filing wins and the conflict is reported, not silently resolved.
5. **Alert on gaps**: missing, stale (beyond the latest reporting period), or inaccessible sources are stated explicitly. If a real-time quote or the latest report cannot be verified, say so - do not claim to have fetched it.
6. **Preserve raw inputs** alongside calculations (the script echoes every payload under `input_echo`) so the same inputs reproduce the same outputs.

### Minimum record per material input

| Field | Content |
|---|---|
| value | the number used |
| unit / currency | e.g. RMB million; RMB per share |
| period | reporting period or as-of date of the input |
| basis | consolidated vs parent; basic vs diluted shares; disclosed vs calculated vs assumed |
| source | document name, table/page, URL |
| retrieved | retrieval date |
| classification | [Fact] / [Calculated] / [Assumption] |

## Research ledger gate

Keep the records above in one JSON ledger per valuation (see `examples/research-ledger.example.json`) and run it through the executable gate before calculating:

```
python scripts/audit_ledger.py ledger.json
```

It fails on missing required metadata, on a fact/calculated record without source, on a calculated record without formula/input_refs, and on an assumption without rationale. It warns on `unknown` records (which must not feed a formal calculation), placeholder text left in source/rationale, `published_at` later than `as_of`, and duplicate record names. Passing is a structural check only - it does not prove the source is real or the figure correct.

## Data sources and audit trail

- Use company filings and official disclosure platforms as primary sources for reported financial facts: CNINFO and the relevant mainland exchange for A-shares; HKEXnews for Hong Kong-listed issuers.
- Third-party financial databases may support discovery, history and cross-checks. Record the provider and reconcile material conflicts to original disclosures where possible.
- For each important figure record: value, unit, currency, reporting period, consolidated/parent-company basis, source document and page/table if available, publication date, retrieval date, and whether it is disclosed, calculated or assumed.
- For PDF extraction, verify units, current/comparative columns, period, consolidated vs parent statement, sign, table position, and cross-statement consistency. Text extraction success alone is not proof that the figure was read correctly.
- Distinguish annual, interim, quarterly, TTM, and annualized figures. Do not mix them silently.

## Price, shares and corporate actions

- Use the unadjusted market price for a contemporaneous per-share valuation comparison. Use a dividend/corporate-action-adjusted total-return series when analyzing investment performance.
- Refresh share count for buybacks, new issuance, stock splits, conversions and potential dilution. State whether the valuation uses basic or diluted shares.
- Avoid double counting cash: if net debt already subtracts cash, do not add the same cash again as a non-operating asset.
- For financials, remember that preferred share dividends and perpetual bond coupons reduce the profit attributable to common shareholders; reconcile EPS-implied payout with headline payout ratios.

## Currency and A/H shares

- Match cash-flow currency and discount-rate currency. Listing venue alone does not determine the correct currency framework.
- Record the FX rate and as-of time used to convert intrinsic equity value into the traded share currency.
- For dual-listed A/H companies, estimate the same underlying business consistently before separately discussing A/H price differences. Do not treat a historical A/H premium/discount as a fixed intrinsic-value adjustment.
- Liquidity, ownership structure, investor access and taxes may affect the investor's realized return or market price; do not silently fold them into operating cash flows.

## Dividends and investor-specific taxes

- Distinguish regular dividends, interim dividends, special dividends and buybacks. Forecast recurring dividends; treat special dividends as non-recurring unless evidence supports repetition.
- Report pre-investor-tax intrinsic value separately from investor-specific after-tax income. Tax handling depends on investor type, holding period and investment channel; verify current official rules before calculating it.
- A company's dividend yield is not automatically its expected total return. Consider payout sustainability, growth, price paid, and relevant taxes/fees separately.

### Mainland individual investor on A-shares (differentiated dividend tax)

Tax is levied on the **holding period**, not on the receipt date (财税〔2015〕101号; individual investors in listed A-shares):

| Holding period at sale | Effective tax on the dividend | Mechanic |
|---|---|---|
| ≤ 1 month | 20% | Full amount taxable |
| > 1 month, ≤ 1 year | 10% | 50% of the amount is taxable |
| > 1 year | 0% | Temporarily exempt |

Because the rate depends on the eventual holding period, the tax is generally **not** withheld when the dividend is paid; it is settled when the shares are sold. Consequences for a DDM:

- A DDM built on gross dividends overstates what an individual investor receives unless they hold beyond one year. State which assumption the valuation uses.
- When the holding period is unknown, report the valuation on a pre-tax basis and show the after-tax sensitivity, rather than picking one rate silently.
- Enterprise investors on A-share dividends are generally exempt under the resident-enterprise participation exemption, and public fund distributions to individuals have their own rules - do not apply the individual holding-period table to them.

### Mainland investor buying Hong Kong shares (Stock Connect)

- Individual investors accessing HK-listed shares through Shanghai/Shenzhen-Hong Kong Stock Connect: dividends are subject to **20%** individual income tax (财税〔2014〕81号 for Shanghai Connect, 财税〔2016〕127号 for Shenzhen Connect), withheld through ChinaClear/HKSCC arrangements. The H-share and non-H-share channels can differ in withholding mechanics; check the issuer's dividend announcement.
- Enterprise investors through Stock Connect include dividends in taxable income, with relief for qualifying long-held H-share dividends and credit for withholding already suffered.
- Hong Kong does not levy a dividend withholding tax at the company level for ordinary HK-incorporated issuers, so "HK dividends are tax-free" is only true for the HK layer, not for a mainland investor's own tax position.
- Some H-share issuers disclose an additional enterprise-level withholding on distributions; reconcile the announced net dividend per share against the gross figure before using it as a DDM input.

Use one consistent basis throughout: forecast, discount and compare on the same gross or net dividend definition, and state it in the report. Do not mix a net dividend with a pre-tax Ke, or a gross dividend with an after-tax required return.

*Rates above reflect the rules in force at the time of writing; re-verify against the current 财税 documents and the issuer's dividend announcement before relying on them.*

## Sector disclosure notes

- **Banks (A and H):** interim and final dividend plans are disclosed in interim/annual reports; payout denominators differ (attributable net profit vs profit attributable to common shareholders). Capital ratios are disclosed on both advanced and standardised approaches - state which you use.
- **Insurers:** embedded value and VNB disclosures differ between mainland and Hong Kong listings; H-share annual reports often carry the fuller EV appendix. Use the EV as disclosed and state its assumptions.
- **REITs:** mainland public REITs and Hong Kong REITs report fund-level distributable income; use the fund's disclosed distributable amount as the AFFO input and reconcile to the financial statements.
- **Asset holders:** revaluation bases (fair value vs cost model) and the valuation firm's basis should be recorded asset by asset.

## Sources to prefer

- CNINFO: https://www.cninfo.com.cn/
- Shanghai Stock Exchange: https://www.sse.com.cn/
- Shenzhen Stock Exchange: https://www.szse.cn/
- HKEXnews: https://www1.hkexnews.hk/search/titlesearch.xhtml
