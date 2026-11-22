# Sources: how good is each estimator, and how to combine them (research agent 7)

Data: 201 lines in games 1-29 (all 6 sources answered every line). Market bounds: 82 lines proven covered (lo>0),
47 two-sided, 76 with only hi, 43 with no information. Money is measured with a fast per-line replay that matches
`fable_vs_opus.replay` exactly on 60 random (line, a, b) checks. Scripts: `common.py`, `accuracy.py` (full tables in
`accuracy.md`), `combine.py` (`combine.out`), `judges_wf.py`, `x_cov.py`.

## TL;DR
1. **The six sources are almost the same estimator.** Fair vs the two-sided midpoint: median bias between +2% and +7%
   for every source; mean absolute error 39-50%; 41-56% of proven-covered lines are priced **below lo**. Coverage
   calls are 91-98% right on proven-covered lines. No source is clearly better or worse.
2. **Hidden asymmetry: v1/opus-2 and v1/opus-3 are the only sources that put fair = 0 on lines they call not
   covered.** v1/opus-1, v2/fable-1, v2/opus-1 (most lines) and v2/opus-2 report the gross price anyway. So
   `b = 1.04 x min(fair)` is 0 on uncovered lines only because v1/opus-2/3 are in the pool. Dropping v1/opus-2
   costs -30K worst-case walk-forward. Using v2 only costs -73K (negative worst case).
3. **No bias correction or weighting beats the equal-weight median of all 6 walk-forward** (games 6-29, live formula
   type, k/m refit on earlier games). Baseline: **+48.4K..+243.6K**. Bias corrections lose 6-31K. Inverse-error,
   recent-window and shrinkage weights lose about 5-9K. Dropping any single source loses 9-12K worst-case and is worse
   in 13-19 of 22 games.
4. **Recommendation: keep all 6 sources with equal weights and the true median (average of the 3rd and 4th values).
   Don't drop or up-weight any source.** If you rebuild the pipeline, make the "fair = 0 when not covered" behaviour
   explicit instead of relying on two sessions' habits. Adding more independent sources looks more valuable than
   re-weighting the ones we have.
5. The judges are worse than the formula on the same games 6-29: v1 decider +15.8K..+76.9K, Fable judge
   +6.8K..+106.2K, Astra judge -24.7K..+40.7K. The walk-forward formula gets +48.4K..+243.6K.

## A. Accuracy vs market bounds (games 1-29; value metrics only on lines the source itself calls covered)

| source | fair: inside [lo,hi) | fair < lo (proven covered) | fair >= hi | median bias vs mid | mean abs err vs mid | censored err (covered) | covered call right (lo>0) |
|---|---|---|---|---|---|---|---|
| v1/opus-1 | 18.6% | 47.4% | 65.1% | +6.1% | 39.3% | -8.7% | 92.7% |
| v1/opus-2 | 22.2% | 54.4% | 58.5% | +2.9% | 44.1% | -13.3% | 96.3% |
| v1/opus-3 | 16.7% | 56.0% | 64.5% | +6.3% | 40.3% | -11.7% | 91.5% |
| v2/fable-1 | 26.1% | **41.2%** | 63.6% | +5.8% | 50.1% | **-4.0%** | **97.6%** |
| v2/opus-1 | 19.0% | 49.3% | 61.3% | +1.8% | **38.6%** | -6.9% | 91.5% |
| v2/opus-2 | **28.9%** | 45.6% | **56.9%** | +3.7% | 45.5% | -5.6% | 96.3% |
| median of 6 | 21.3% | 53.7% | 75.6% | +0.3% | 44.3% | -9.8% | — |

How to read the table: estimates are **two-sided wrong**. On proven-covered lines about half the fairs sit below lo
(too low), yet where an upper bound exists about 60% sit at or above hi (too high). The midpoint bias is about 0, so the
problem is spread, not level. That is why a level correction can't help.

- `low` is far too low (77-87% below lo; bias -16% to -31%). `high` is far too high (bias +61% to +110%). Their only
  use is as a spread signal; neither is usable as a price.
- **By category** (two-sided n is tiny except parts/repair, n=29): parts/repair bias is about 0 for every source.
  Labour is +10% to +36% vs mid, yet 23-54% of labour fairs are below lo (n=13): wide dispersion, no consistent
  direction. Vehicle/call-out is +39% to +59% vs mid (n=2 two-sided) but 56-67% below lo (n=9), so it is
  contradictory and too thin to correct. No source has a category edge that holds up.
- **Over time** (do they learn?) **no**. Mean censored |error| for the median is 18% in g1-10, 37% in g11-20 and 34% in
  g21-29. Every source moves together, so the change comes from the cases, not from learning. The slope of the censored
  error is -4.4 to +6.8 log-points per 10 games, which is noise. The v1 sessions, which get market feedback, don't
  improve more than v2.

### Judges (a, b vs bounds; replay money)
| judge | a <= lo on covered | a < 0.8 lo | a >= hi (a>0) | b < lo on covered (rejects fair) | b >= hi (accepts inflated) | median a/lo | net g1-29 | net g6-29 |
|---|---|---|---|---|---|---|---|---|
| v1 decider | 79% | 54% | 36% | 48% | 33% | 0.80 | +40.7K..+109.1K | +15.8K..+76.9K |
| Fable judge | 78% | 44% | 44% | **22%** | 47% | 0.87 | +31.9K..+140.7K | +6.8K..+106.2K |
| Astra judge | 84% | 67% | 22% | 39% | 50% | **0.62** | -12.0K..+59.4K | -24.7K..+40.7K |

Astra under-charges badly (median a = 0.62 x lo). The decider rejects fair bills on about half the covered lines. The
Fable judge's limits are the best of the three, but all three lose to the formula on the median fair.

## B. Combination schemes: walk-forward money (test games 6-29; k per cv tier and m refit worst-case on games < g)

| scheme | WF worst..best | g6-17 | g18-29 | Δ worst vs base (se) | games better/worse |
|---|---|---|---|---|---|
| **baseline: equal-weight median of 6 (live type)** | **+48.4K..+243.6K** | +17.4K..+101.9K | +31.0K..+141.7K | 0 | — |
| upper median (4th of 6) | +50.3K..+290.1K | +16.6K..+99.9K | +33.6K..+190.2K | +1.8K (3.4K) | 9/12 |
| lower median (3rd of 6) | +32.9K..+161.5K | +14.5K..+95.3K | +18.4K..+66.1K | -15.5K (9.0K) | 5/16 |
| mean / geo-mean | +21.6K / +25.1K worst | | | -26.9K / -23.3K | |
| inverse-error weights | +43.0K..+260.2K | +13.0K..+99.8K | +30.0K..+160.3K | -5.4K (4.2K) | 7/13 |
| inverse-error weights, last 8 games | +39.5K..+255.0K | | | -8.9K (4.7K) | 7/13 |
| shrink weights 50% (and 25%) to equal | +43.2K..+260.2K | | | -5.2K (3.8K) | 6/14 |
| bias corr per source (all history) | +17.3K..+251.5K | | | -31.1K (20.7K) | 7/15 |
| bias corr per source, last 8 games | +42.6K..+241.5K | | | -5.8K (4.3K) | 7/15 |
| bias corr per source x category | +29.0K..+248.5K | | | -19.4K (20.8K) | 8/14 |
| bias corr per category (common to all sources) | +21.4K..+242.3K | | | -27.0K (20.2K) | 7/15 |
| bias per source + inverse-error weights | +36.5K..+159.8K | | | -11.9K (5.0K) | 6/15 |
| coverage-aware fairs (0 if source says not covered) | +42.2K..+111.4K | | | -6.2K (2.2K) | **0/13** |
| drop v1/opus-1 | +36.3K..+159.6K | | | -12.2K (4.3K) | 3/19 |
| drop v1/opus-2 | +18.2K..+305.6K | | | -30.3K (21.6K) | 10/11 |
| drop v1/opus-3 | +38.6K..+289.4K | | | -9.8K (10.1K) | 8/13 |
| drop v2/fable-1 | +36.3K..+150.7K | | | -12.1K (4.9K) | 6/16 |
| drop v2/opus-1 | +39.1K..+267.5K | | | -9.3K (5.6K) | 6/16 |
| drop v2/opus-2 | +36.3K..+150.5K | | | -12.1K (3.9K) | 6/15 |
| v1 only (3 Opus) | +41.1K..+100.3K | | | -7.4K (10.4K) | 8/14 |
| v2 only (Fable + 2 Opus) | **-24.3K**..+293.6K | -23.5K.. | | -72.8K (28.6K) | 4/18 |

In-sample reference (secondary; fitted on games 1-29): live formula on games 6-29 gives +54.8K..+255.1K.

Notes:
- Bias corrections are fitted as an L1 censored log-bias against [lo,hi) on proven-covered lines, shrunk with n0=10.
  Weights are 1/(censored MSE + 0.01). A global correction factor cancels against the refit k, so only relative
  corrections matter. The relative biases are small (±5%) and noisy, so corrections add noise and move the fitted k
  (k_agree fell to 0.72-0.86).
- **The mean of the two middle values matters.** The 3rd-of-6 median loses 15.5K worst-case. The 4th-of-6 median is
  marginally better (+1.8K, not significant) and has a much higher best case, but its disagree-tier k drops to 0.96,
  which is the unstable multiplier flagged in the brief. Keep the plain median.
- The best-case column swings ±100K with the fitted disagree-tier k (0.96 vs about 1.2). Judge schemes on the
  worst-case column and the per-game win counts.
- **Coverage-aware** (a = 0 on lines the median calls not covered) loses 6.2K and wins in 0 of 22 games. The current
  pool's habit of charging 0.92 x the median gross price on lines **all** sources call not covered earns +4.0K certain
  (up to +117.6K) in g6-29, because some reviewers accept. As the issuer, a charge never loses, so keep doing it on
  purpose.

## Recommendation
- Formula input: **equal-weight true median of all 6 sources' `fair_gross_total`**, as live. Add no per-source,
  per-category or learned bias corrections, and no inverse-error or recent-window weights. All of them lose money
  walk-forward.
- Drop no source. Every single drop costs 9-12K worst-case, and the v1/opus-2 or v2-only drops break the b = 0 gate on
  uncovered lines (-30K and -73K). No source earns an up-weight: v2/fable-1 and v2/opus-2 are slightly more accurate,
  but inverse-error weighting still loses 5K.
- Robustness fix (not fitted, so no walk-forward claim): compute `b` from coverage-gated fairs (0 when the source says
  not covered) and `a` from gross fairs. That makes today's accidental behaviour explicit, so a prompt change in
  v1/opus-2/3 can't silently turn on accept-limits for uncovered lines.
- Higher leverage than re-weighting: the error is spread, not bias (about 50% below lo and about 60% above hi at once).
  More independent sources, or better per-line information, would help more than calibration.
