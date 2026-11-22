# Formula agent 5: "charge below the most conservative group"

Read-only research: no submissions, no model calls, nothing written outside this folder.
Data: 398 market lines from games 1-46 (game 47 has no v3 judges). Odd games = 23 (fit), even games = 23 (validation).
Replay: my per-line `earned(a)` / `paid(b)` (`data.py`) matches `fable_vs_opus.replay` exactly. I checked games 5, 20, 33 and 41 with random a/b.
The baselines use the same teams list and the same old-Fable-judge fallback as `live_eval/ruben3_test.py`.

## The rule (2 tuned numbers)

For each line:

1. **Coverage:** `cov` = more than half of the available researcher answers (up to 9) say covered and related.
   If not `cov`, then a = 0 and b = 0. This is the approved policy. On uncovered lines the market almost always
   agrees: rejecting everything there cost only 7.4K worst case on the odd games.
2. **Base value:** `X = min over groups G in {1,2,3} of median(fair_gross_total of G's answers that vote covered)`.
   A group with no answers is skipped.
   *Reason:* overpricing loses the whole line, but underpricing costs only the difference. So the charge should sit at a
   low quantile of our belief about t. The three groups err in different directions by line type, and the
   lowest group median is the simplest robust low quantile.
3. **Charge:** `a = 0.92 · X`.
   *Reason:* the payoff has a cliff just above about 0.95·X. I chose 0.92 as the best k after averaging over
   k ± 0.03 on the odd games, so the charge stays a safe step below the cliff. The single best k was 0.94.
4. **Limit:** `b = 1.00 · X`.
   *Reason:* as insurer the loss runs the other way (rejecting a fair bill costs +0.5a, accepting an inflated one
   costs a), so b sits above a, at our conservative fair estimate. The optimum is flat between 0.97 and 1.02.

What I tested and dropped on the odd games:

- Judges as base, cap or vote. The best was j-all9 a × 0.98, which earned 251K vs 266-270K for the min-group base.
- A G3-led charge capped by the older groups, `min(G3, c·old)`. The best c was about 1.0-1.05, which is the same as the min-group base.
- Quantiles of the 9 fair values. q10 was a near tie but did worse on even games.
- Old-judge a.

## Results (net worst..best, midpoint)

| rule | odd (fit) | even (validation) | even 36-46 |
|---|---|---|---|
| **final a=0.92·X, b=1.00·X** | **+82.1K..+129.7K** (mid +105.9K) | **+53.4K..+109.0K** (mid +81.2K) | **+17.0K..+38.7K** (mid +27.8K) |
| baseline Ruben avg 2 groups (live) | +50.6K..+176.4K (mid +113.5K) | +47.2K..+198.0K (mid +122.6K) | +24.7K..+62.1K (mid +43.4K) |
| baseline Ruben avg 3 groups | +47.9K..+197.6K (mid +122.7K) | +57.0K..+197.0K (mid +127.0K) | +26.8K..+63.9K (mid +45.3K) |
| ref: group 3 alone 0.93/0.91 | +54.5K..+189.9K | +51.4K..+181.9K | +32.0K..+71.2K |
| extra (not approved): final + old-judge a on uncovered lines, as the live rule does | +87.0K..+176.7K | +57.1K..+173.8K | +17.1K..+53.6K |
| extra: Ruben 2 without its uncovered-line charges | +45.7K..+129.4K | +43.4K..+133.2K | +24.6K..+47.1K |

**The baselines' high best case mostly comes from charging uncovered lines.** The Ruben rule falls back to the
judge's a when every group says uncovered. With that fallback added to the final rule, or removed from Ruben,
the best cases are about equal.

## Robustness

Each change below moves one value and shows the worst case on odd / even / even 36-46:

- k 0.87: +64.2 / +41.6 / +13.1K
- k 0.90: +73.6 / +50.8 / +18.5K
- k 0.94: +86.8 / +38.2 / **+1.4K**
- k 0.97: -3.1 / +3.2 / -32.6K (over the cliff)
- m 0.95: +81.3 / +51.5 / +16.1K
- m 0.98: +82.2 / +52.9 / +16.9K
- m 1.02: +80.7 / +53.8 / +17.0K
- m 1.05: +75.8 / +54.8 / +18.1K

So **b is robust and k is not**: even +0.02 above the chosen value collapses the recent block.

Bootstrap over games, resampling the k choice on the odd games: 5/50/95% = 0.91 / 0.92 / 0.93.

Bootstrap of the worst-case difference, final minus baseline, over games:

| block | vs Ruben 2 | vs Ruben 3 |
|---|---|---|
| odd | +30.9K, 90% interval [-10.9, +82.8], P(>0) = 0.86 | +33.7K, P(>0) = 0.91 |
| even | +6.4K, [-12.5, +28.2], P(>0) = 0.67 | -3.5K, P(>0) = 0.38 |
| even 36-46 | -7.7K, [-10.9, -5.0], P(>0) = 0.00 | -9.6K, P(>0) = 0.05 |

The odd-game gain comes mostly from games 29 and 33. There, groups 1 and 2 overpriced and the min-group base avoided it (+20K each).

## Recommendation

- The rule is simple, explainable and the best of my family on the odd games: worst case +82K vs +51K (Ruben 2) and +48K (Ruben 3).
- On the even games it holds up only partly. It beats the live Ruben-2 rule by +6K worst case, roughly ties Ruben 3 (-3.6K), and
  **loses 8-10K on the recent block 36-46**. Group 3 is mature there, so the extra caution of the min-group base costs money.
- **I do not recommend replacing the live charge rule with it.** If anything is adopted, take the acceptance side:
  `b = 1.00 × min group median`. It is robust and no worse than live on any split (paid worst case: odd 183.6K vs 196.1K;
  even 174.5K vs 176.3K; even 36-46 97.5K vs 97.4K).
- Keep any charge multiplier at or below 0.92: the cliff sits about 0.02-0.04 above the fitted optimum.

Note on protocol: in one early diagnostic (`diag3.py`) I printed even-game values per base. I did not change the
final rule after seeing the even results. It was fixed on the odd games: smoothed k and the flat b optimum.
Scripts: `data.py` (dataset and exact replay), `fam.py`, `stab.py` and `cap.py` (odd-game search), `final.py` (evaluation;
output in `final.txt`), `decomp.py` and `unc.py` (diagnostics).
