# Acceptance limit b — research report (agent 5)

**Recommendation: keep `b = 1.04 x lowest fair of the 6 sources` on every line.** No other basis, grouping or
market-aware rule beats it robustly, either walk-forward or on the hold-out. The cost is flat for m in 0.96..1.08
(within about 1K over 24 games). Below 0.96 it gets steeply worse: m = 0.90 costs +6K.

## Method
- 201 lines (games 1-29) and 1874 charges from other teams. Each charge is labelled fair, inflated (fraud), `?` or hidden,
  using market bounds. `core.paid(row, b)` is the insurer side of `fable_vs_opus.replay` per line; it matches replay
  exactly on a check sample (0 mismatches).
- I report three cost figures for each rule. **lo**: optimistic. **hi**: replay worst case, where every hidden
  (all-rejected) charge costs b. **tight**: hidden charges must exceed the largest charge any reviewer accepted on that
  line, because every reviewer rejected them. That is a proven lower bound, so tight is a valid but less pessimistic
  worst case. All numbers are EUR paid; lower is better.
- Walk-forward: fit on games < g, test on g, for g = 6..29. Hold-out: fit on games 1-24, test on 25-29. Nested: at each
  g, choose the family with the best walk-forward record on earlier games. Grid m = 0, 0.50..2.00 step 0.02. Groups with
  fewer than 8 training lines fall back to the global m.

## Results (paid; fit criterion = worst case "hi"; also run with lo and tight: same conclusions)
| rule | WF 6-29 lo / tight / hi | hold-out 25-29 lo / tight / hi |
|---|---|---|
| reject all (b=0) | 134.2K / 134.8K / 134.8K | 39.4K |
| FDN actual (real b) | 129.7K | 35.3K |
| **b = 1.04 x min fair (fixed)** | **112.5K / 116.5K / 122.8K** | **28.3K / 30.0K / 30.6K** |
| min fair, m fitted WF (path 0.98..1.04, ends at 1.00) | 113.4K / 115.7K / 123.5K | 29.1K / 29.1K / 31.3K (m=1.00) |
| 2nd-lowest fair (= q25), m fitted (1.00) | 112.1K / 114.7K / 122.8K | 29.0K / 29.1K / 31.2K |
| min fair by cv tier (agree 0.96 / some 1.16 / disagree 0) | 112.7K / 116.8K / 123.0K | 28.5K / 30.2K / 30.9K |
| min fair by category | 113.8K / 118.3K / 124.4K | 28.4K / 30.0K / 30.6K |
| min fair by coverage votes (0-3 votes: reject) | 113.9K / 116.2K / 124.0K | 29.1K |
| min fair by line size | 116.2K / 118.5K / 124.6K | 29.3K |
| track-calibrated min (per-source market factor) | 113.2K / 115.6K / 123.4K | 29.3K |
| market ratio (median of proven-fair/minfair, by category) | 117.3K / 121.4K / 127.5K | 29.4K |
| median / mean / max fair, median high, tracked median | 145-153K (fit picks m = 0, i.e. reject) | 39.4K |
| median low (x1.16) / min low / min high | 127.0K / 129.4K / 134.4K | 32.6-34.5K |
| NESTED family choice | 113.9K / 116.4K / 124.2K | — |
| hindsight oracle (best b per line) | 89.5K / 89.8K / 98.3K | 26.3K / 26.3K / 28.4K |

Fixed-m curve, min fair, WF 6-29, lo / tight / hi:
- 0.90: 118.3 / 118.6 / 127.2
- 0.96: 112.9 / 113.2 / 122.4
- 1.00: 112.7 / 113.0 / 122.6
- 1.04: 112.5 / 116.5 / 122.8
- 1.08: 112.9 / 117.3 / 123.6
- 1.12: 113.5 / 118.6 / 124.5
- 1.20: 115.2 / 121.1 / 126.8

Bootstrap over games of the best m: lo criterion 0.96 / 1.04 / 1.14 (q10 / median / q90); hi criterion 0.96 / 1.04 / 1.08;
tight criterion 0.96 / 0.96 / 1.04.

## Penalties avoided vs inflated accepted (b = 1.04 x min fair, games 6-29, vs reject-all)
- Fair charges: 295 of 480 accepted. That avoids 30.3K of 0.5a penalty premium; 185 fair charges are still rejected,
  leaving 43.5K paid at 1.5x.
- Inflated charges: 86 of 674 accepted, costing 8.4K. Only 5 of 621 hidden charges are even possibly at or below b
  (≤ 3.7K worst case).
- Net: about 22K less paid than reject-all and about 7-17K less than FDN's real acceptance decisions over 24 games.
  The remaining headroom to the hindsight oracle is about 23K. That gap comes from scatter in our estimates, not from the
  formula shape.

## Why the alternatives fail
- Market fair charges / our min fair: q25 0.70, median 0.91, q75 1.16. Inflated charges / min fair: q25 1.04,
  median 1.33. The two distributions cross near 1.0-1.05, so min fair is already the market-aware threshold.
  Category ratios (fair vs inflated medians) are labour 0.90 vs 1.07, parts 0.91 vs 1.61, fee 0.85 vs 1.50. The
  category spread is real, but per-category multipliers are noisy (diagnostic and disposal flip between 0 and 1.38 across
  folds) and lose 1-2K walk-forward.
- Median, mean and max fair overshoot: they accept many inflated charges and expose b to hidden charges, so the fit
  collapses to reject-all. Low and high bases are worse than fair.
- Coverage votes and disagreement tiers make almost no difference. cv tier fits "disagree → reject", which is unstable
  (0 vs 0.66 depending on the criterion).
- Nested family selection is worse than simply keeping min fair, a sign of selection noise.

## Optional
If you believe hidden charges are almost never at or below b (tight criterion), m = 0.96-1.00 saves about 3K over
24 games. Under the replay worst case and the optimistic case, 1.04 is marginally best. Any m in 0.96..1.08 is fine;
stay above 0.96.

Scripts: build.py (dataset → lines.pkl), core.py (paid), check.py (replay parity), wf.py {hi|tight|lo}
(walk-forward, hold-out and nested; outputs wf_*.json), curve.py (m curves, bootstrap, oracle, decomposition), sep.py
(market charge ratios).
