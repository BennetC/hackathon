# Trends: market dynamics over time (research agent 10)

Data: `live_eval/tx_cache.pkl` games 1-29 (12 teams, 201 lines, 82 with a proven-fair `lo`), pooled 6 sources
(v1 3×Opus + v2 Fable+2×Opus), replay via `fable_vs_opus.replay`. FDN Bench leaderboard (GET only, saved to
`bench/leaderboard.json`) adds games 30-34. Scripts: `pre.py` (per-line precompute → `lines.pkl`), `drift.py`,
`recency.py`, `teamnet.py`, `bench_cmp.py`. Nothing submitted, no model calls.

## 1. Proven-fair level vs our sources' fair: no drift
`log(lo / median fair)` regressed on game index (covered lines with lo > 0):

| category | n | median lo/med | slope per game | g1-10 | g11-20 | g21-29 |
|---|---|---|---|---|---|---|
| ALL | 82 | 1.04 | -0.27% ± 0.95 | 0.93 | 1.13 | 1.04 |
| parts/repair | 46 | 1.06 | -1.02% ± 1.44 | 0.99 | 1.25 | 1.01 |
| labour | 13 | 0.98 | -2.27% ± 1.11 | 1.62 (n1) | 1.03 | 0.87 |
| vehicle | 9 | 1.18 | +1.85% ± 4.06 | 0.93 | 1.13 | 1.33 |
| disposal | 7 | 0.99 | +9.25% ± 3.18 | 0.92 | 1.19 | 2.09 (n2) |
| fee | 5 | 0.86 | +0.67% ± 1.08 | 0.86 | 1.03 | 0.94 |

- **Proven-fair levels do not rise as teams learn.** The overall slope is zero. Games 11-20 were a high block
  (lo > 1.2×med on 12/27 lines), and games 21-29 came back to 1.04. Proven-inflated `hi`/med is flat too (1.05, slope +0.06%).
- Disposal (+9%/game) and labour (-2%/game) slopes come from 7 and 13 lines. Treat them as noise, not a signal to act on.
- Caveat: `lo` is the highest charge that was *proven* fair, so it partly depends on what teams charge. The median
  market charge / our median fair on covered lines moves a lot from game to game (0.36 to 1.70) with no trend.

## 2. Do other teams adapt?
Each team's median charge / our median fair, on covered lines (slope of log ratio per game, ± SE):

- Mostly stable. 9 of 12 teams are within 2 SE of zero.
- **alpha** charges lower over time (-2.2%/game ± 0.7; 0.91 → 0.72).
- **Kiebler** charges lower (-1.7 ± 0.8). Kiebler's net per game also jumped from -0.4K to +4.4K in g21-29.
- **Humble Legends** charges higher (+2.1 ± 0.9; 0.83 → 1.06).
- FDN itself is at 0.72, the lowest charge level apart from vietgang.
- 404 holds about 1.05×med every block and nets about 4.5K per game in every block. It wins by being consistent, not by adapting.
- Acceptance limits (max accepted charge / med) have no significant trend except TRINNERS (+2.9 ± 1.3).
- With 12 teams, about one ">2 SE" result is expected by chance, so the adaptation evidence is weak. There is no
  market-wide shift in charges or limits.

## 3. Recency-weighted walk-forward fitting vs equal weights
Setup: refit k_agree, k_some, k_dis on the median and m on the minimum, using only past games, with weight
0.5^(age/H) or a sliding window. Test games 6-29. Equal weighting reproduces the known +48.4K..+243.6K.

| fit (W=0 worst-case criterion, as formula.py) | net 6-29 lo..hi | mid | Δmid vs equal |
|---|---|---|---|
| **equal weights** | **+48.4K..+243.6K** | **+146.0K** | 0 |
| half-life 20 games | +44.9K..+235.5K | +140.2K | -5.8K ± 4.4 |
| half-life 10 | +41.1K..+228.3K | +134.7K | -11.4K ± 5.9 |
| half-life 6 | +39.0K..+232.7K | +135.9K | -10.1K ± 6.6 |
| half-life 3 | +36.3K..+231.2K | +133.8K | -12.3K ± 6.8 |
| window last 12 / 8 / 5 | +21.8K / +16.3K / +28.8K (lo) | 129-134K | -12 to -17K |
| current fixed (in-sample, for reference only) | +54.8K..+255.1K | +155.0K | +8.9K |

With the midpoint criterion (W=0.5), half-lives of 10-20 games come out at +2K ± 3K mid and improve the worst case by about 6-8K.
Shorter half-lives and windows make the worst case drop to about 0K. Everything is within noise.

The best single k and m per block (in-sample, W=0) show no time trend:

| block | best k | best m |
|---|---|---|
| g1-10 | 0.92 | 0.98 |
| g11-20 | 0.82 | 1.10 |
| g21-29 | 0.92 | 0.96 |

The equal-weight walk-forward fit settles on k = 0.92 / 0.84 / 1.16 by game 20 and stays there through game 29.
Recency weighting mostly makes k_dis jump around (0.62 → 1.48), and k_dis is already known to be the unstable parameter.

**Recommendation:**
- Keep equal-weight, all-history fitting. Do not add a time trend or decay to k/m.
- If refitting periodically, at most use a long half-life (≥ 20 games) with the midpoint criterion.
- Cap k_dis, e.g. at 1.10, as the bench "cap1.1" variant already does.
- Market levels are stationary, so more history beats recency.

## 4. FDN Bench leaderboard (read-only, 40 strategies, games 1-34)
Top strategies by worst-case net (net_min). Almost all are rules fitted on games 1-29, so they are in-sample except games 30-34.

| strategy | worst-case net | mid |
|---|---|---|
| claude-formula-pooled6-cap1.1 | **116.5K** | 224.3K |
| claude-pooled6-minfair-0.97-1.00 | 108.2K | 149.6K |
| Ruben combined rule (Opus decider + Fable judge) | 105.7K | 176.8K |
| claude-pooled6-mean-0.91-0.93 | 100.4K | 146.4K |
| claude-formula-pooled6 (30 games) | 96.9K | 200.8K |
| FDN Live official | 61.2K | 61.2K |

- Session/judge/decider strategies and Bennet's GPT runs score far lower (net_min 20-50K or worse). Pooling many
  sources with a simple multiplier rule dominates.
- claude-formula-v2only has the widest range (29.9K..438.9K). It is high-variance with a weak worst case.
- **The bench agrees with our replay.** Per-game mid for claude-formula-pooled6 on games 1-29 has correlation 1.00
  with the local replay: 191.2K local vs 195.0K bench. The bench's worst case is about 7K more optimistic (91.1K vs
  83.9K local), probably from different handling of hidden charges.
- **Out-of-sample games 30-34 on the bench:**
  - formula-cap1.1 nets 5.0..6.9K per game, which matches or beats its 1-29 per-game level (2.3-4.0K worst case).
  - FDN Live made +8.6K per game in g30-34, after -0.7K per game in g21-29.
  - Neither shows any decay, which again points to a stationary market.
- One mismatch: the bench's "FDN Live" cumulative total (61.2K over 34 games) is above the tx-cache sum for games
  1-29 (18.4K). That is because g30-34 add about 43K.

## Bottom line
- The market is stationary. There is no drift in proven-fair levels and no market-wide adaptation, only a few teams
  slowly moving their own charges.
- Recency-weighted fitting does not help (-6K to -17K walk-forward, worst-case criterion). Keep equal weights, and cap
  the unstable k_dis rather than chasing recent games.
- The bench confirms the pooled formula, especially cap1.1, as the best family, and its numbers match our replay.
