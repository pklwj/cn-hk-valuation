# Anti-overfitting rules for valuation

A valuation model's parameters are **priors about how the world works**, not degrees of
freedom for fitting historical prices. Once parameters start chasing price, the model
degrades into an expensive moving average.

## The rule

**Never change a valuation input because it would have produced a better outcome.**
Post-outcome data (realized prices, realized returns) may only be used to *test* a model,
never to *set* its inputs.

Applies to, without exception: WACC / Ke, terminal growth, exit multiple, normalization
method and window, FCFF conversion factors, margin-of-safety thresholds, scenario widths.

## Why this is not pedantry

Empirically demonstrated on a 4-point backtest (`robustness_nofit.py`, Focus Media 002027):

- 74 valid (WACC, g) combinations were scanned. **4 of them (5.4%) scored 100% hit rate.**
- All 4 achieved it by **going silent on 3 of 4 periods** — lowering the discount rate
  shrinks the premium until the signal degrades to "neutral" and drops out of the hit count.
  **100% accuracy from 1 judgment is not skill.**

Both channels — tuning parameters, and reducing the number of judgments — can manufacture
an impressive hit rate. On small samples the hit rate carries essentially no information.

## Practice

### 1. Sensitivity is for exposure, not for search

Run `dcf_sensitivity` / scenario grids to show **where a verdict flips**, i.e. how much an
assumption must move before "expensive" becomes "fair". A verdict that holds across most of
the grid comes from the data; one that survives only at the corners was selected by the
parameter.

- Report: "expensive holds in 83% of the (WACC, g) grid."
- Never report: "we chose WACC = X because it maximized historical accuracy."

### 2. Normalization must be justified ex ante

Excluding a year as "abnormal" requires an **observable fact available at the time**
(a policy change, a one-off disposal, a customer-structure break) — **not** the later
realization that the number proved unsustainable.

State the rule in general form ("exclude years >50% from median driven by a one-off external
event"), not as a list of specific years you happen to know were bad.

### 3. Point-in-time discipline

In any historical test, every input must be as-of the valuation date. Assert this
mechanically, do not eyeball it:

- available earnings years == latest fiscal year disclosed at T0
- balance-sheet year <= T0
- no year later than T0 appears in any input

### 4. Judge a model by mechanisms, not by score

With n < ~20 observations, report **mechanisms** (where the disagreement comes from, which
assumption the verdict is sensitive to, whether the conclusion is parameter-robust) and
explicitly refuse to quote an accuracy figure. If you must show a hit rate, show alongside
it how easily it could have been manufactured.

### 5. Adding samples is the only real fix

To make a conclusion trustworthy, **collect more observations** (more tickers, more periods),
not fit the existing few better. Timestamp every valuation and record the conditions that
would falsify it — that is what the snapshot layer and `snapshot.py diff` exist for.

### 6. Never read a price chart's "adjusted" return as a holding return

Market terminals label a back-adjusted price series "前复权 / forward-adjusted", but vendors
implement it two different ways, and only one of them equals the return an investor earned:

- **Subtractive** (common in CN retail terminals): historical price − cumulative later
  dividends. The chart's percentage change then **excludes** dividends entirely.
- **Multiplicative** (ratio method): historical price × Π(1 − dividend / prior close). The
  percentage change equals total return assuming dividends are reinvested at the ex-date.

They are not close on high-payout names. Verified on 分众传媒 002027 (2021-12-30 → 2026-10-22):
the terminal reported −25.53%; the actual holding return (dividends taken as cash) was
**−1.5%** — a 24-point gap driven purely by ~1.60 yuan/share of dividends over the window.

**How to tell which one you have:** reconstruct it. Take the raw (unadjusted) price at a known
extreme, subtract every dividend with an ex-date after that day, and compare with the chart.
If it matches, the vendor is subtractive.

**What to do:** when a backtest needs a holding return, compute it yourself from the dividend
table (`total_return = (P_end + Σ dividends) / P_start − 1`), state the treatment of dividends
(received as cash vs. reinvested), and never quote the terminal's own percentage change.
When the point is *valuation* rather than return, also note that the DCF value per share is a
**nominal** price and must be compared against the **unadjusted** market price, not the
back-adjusted one.

Corollary for PB: on a high-payout company the book value shrinks as dividends exceed earnings,
so PB drifts upward with no change in the share price. 分众's equity attributable to the parent
fell from 187.01 亿 (2022Q3) to 139.90 亿 (2026H1), −25.2%, while the price rose 17% — PB went
from 3.27 to 5.12. Always state whether a PB comparison is across a constant or a shrinking
denominator (see §Valuation-multiple percentiles, gate 3).

### 7. The perpetuity growth rate must be confronted with delivered growth

`terminal_growth` is the single most dangerous free parameter in a DCF: raising it costs
nothing, no input file changes, and the terminal value moves a lot. Gate:

- **Show the company's own delivered CAGR next to the assumed g.** At minimum three
  windows: the full decade, the stretch since the last cycle peak, and the post-trough
  rebound. Measured on 分众传媒 (2015–2025 revenue): decade CAGR +4.0% looks supportive,
  but from the 2018 peak it is **−1.9%/yr over seven years** — and the longest streak of
  years ≥3% (2015–2018) belongs to a point-rollout boom that has ended. A g that only
  survives the flattering window is a fitted g.
- **A single company growing at nominal GDP in perpetuity is a claim, not a default.**
  Long-run nominal GDP is the traditional ceiling (国内评估口径: g ≤ 长期名义 GDP; IMF
  baseline puts China's 2030 real growth at 3.4% with ~2% inflation), but the *average*
  incumbent grows slower than GDP, because GDP includes entrants. Advertising revenue is
  moreover a cyclical amplifier of GDP, not a stable share of it.
- **Quantify what the one point is worth.** On 分众 at WACC 9%: g 2% → 3% lifts the model
  value 4.63 → 5.13 (+11%) and the terminal multiple 14.6x → 17.2x, flipping the verdict
  from "7% rich" to "3% cheap". When one assumption is load-bearing for the whole verdict,
  say so instead of reporting a point estimate.
- **Compare with what the price already implies** (`reverse_dcf_growth`). Market-implied g
  is descriptive, not validation, but if the price implies 2.7% and you need 3.0% to call
  it cheap, the honest statement is that the margin rests on 0.3pt of extra optimism.
- Disclosure only — this gate never mandates a particular g and must not be used to tune
  one. Observed prices may check an assumption; they may never set it (see §The rule).

## Valuation-multiple percentiles (PB, PE, PS)

A historical percentile ("PB is at the 14th percentile of the last 5 years") looks like it
escapes the parameter problem — it needs no WACC and no terminal growth. It does not escape
it; it trades parameter risk for **sample and denominator risk**, which is worse because it
is invisible.

Three gates, all mandatory:

1. **Cut at structural breaks.** Do not compute a percentile across a reverse merger,
   major asset restructuring, or a change of the reporting entity. Focus Media 002027
   backlisted in 2015-2016; PB averaged 18.12 (2015) and 97.77 (2016), peaking at 386.
   Including those years moves the current percentile from 6.4% (10y) to 44.6% (all
   history) — a 38-point swing that has nothing to do with cheapness.

2. **Pair with profitability — but know that PB/ROE IS PE, and that the denominator lies.**
   Two traps hide here, both verified on Focus Media:

   a. **PB/ROE is an identity, not a new signal — and in CN filings it is a *drifting*
      identity.** If ROE uses period-end book equity, (P/B) ÷ (E/B) = P/E exactly. But
      Chinese annual reports quote 加权平均净资产收益率 on the **weighted-average** equity
      B_avg, so PB/ROE = P/E × (B_avg / B_end) — one extra factor that is not constant.
      The factor is exactly recoverable from published numbers alone: B_avg = E ÷ weighted
      ROE. On Focus Media 2022-2025 it ran 1.111 / 0.960 / 1.012 / **1.131** — a 17.8%
      swing, largest in 2025, precisely the year equity shrank fastest. So PB/ROE does not
      normalize the denominator effect away; it **multiplies it in**, inflating both PB and
      PE by up to 13% in a shrinkage year. Verified to 4 decimals on 4 of 6 dates (the two
      misses are exactly the look-ahead and period-mismatch rows). Quote it as PE or don't
      quote it.

   b. **On a high-payout name, ROE rises mechanically as book equity shrinks.** Focus Media
      net profit was 27.9 亿 (2022) vs ~28.9 亿 (2025), essentially flat (+3.6%), while
      equity fell 187.0 -> 139.9 亿 (−25%). Weighted ROE "improved" 14.82% -> 18.28% purely
      from the shrinking denominator. Dividing PB by current-period ROE treats that
      mechanical effect as genuine profitability improvement and **understates how expensive
      the stock is** (it gave +27% where PB alone says +57%).

   c. **Using full-year ROE at an intra-year date is look-ahead.** At 2022-10-31 the FY2022
      ROE (14.82%) did not exist yet. The PIT substitute is TTM: 2022 first three quarters
      21.31 + 2021Q4 16.40 (FY 60.63 − 9M 44.23) = 37.71 亿 TTM -> TTM P/E 16.2x at the
      intraday low, not 22.1x.

   Better instruments than PB/ROE:
   - **TTM earnings yield / TTM P/E** (point-in-time), ideally on 扣非 to strip one-offs;
   - **Implied sustainable ROE** from the justified-PB identity:
     ROE_implied = PB × (r − g) + g. At r=9%, g=2%: Focus Media implied 24.9% at the 2022
     low vs 37.8% now, against a 2019-2025 normalized median of 26.2% — i.e. the 2022 low
     was priced at roughly normalized profitability while the current price embeds a +45%
     recovery. Note this uses period-end BVPS, so it inherits the shrinking-denominator
     tilt toward "expensive now" — state that when quoting it;
   - **Show profit level and equity level side by side** so the denominator effect is visible
     instead of being silently absorbed into a ratio.

3. **Restore the denominator for high-payout names.** Heavy dividends and buybacks shrink
   book value, so PB drifts up mechanically with the price flat, and the historical range
   stops being comparable. Focus Media: equity attributable to shareholders fell
   176.9 -> 142.5 (–19.5%) from 2023 to 2025, with share count flat, while paying a
   0.34 dividend against 0.20 EPS.

Also: in backtests, recompute the percentile **as of** each date using only years that had
fully elapsed by then. Using the full sample for historical dates is a look-ahead bug
(measured bias on Focus Media: ~1.4pt average, up to 2.2pt — small here by luck, not by
design).

## Backtest scripts

`robustness_nofit.py` (workspace) implements: grid sensitivity, overfitting-ease scoring
(how many parameter combos reach 100%, and whether via silence), flip boundaries, and the
point-in-time assertions above. Point it at another ticker's data to reuse.
