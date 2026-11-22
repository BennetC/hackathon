# Charge side (a): best robust formula — research agent 4

Scope: only earned(a) (issuer part of `replay`, worst case = `issuer[0]`), 201 lines, games 1-29, 6 pooled sources
(v1 opus-1..3 + v2 fable-1/opus-1/opus-2). The vectorised earned(a) in `lib.py` matches `fable_vs_opus.replay` on 603/603
checks. Scripts: `prep.py`, `lib.py`, `core.py`, `search.py` (170 families x 4 smoothing widths + nested WF), `robust.py`,
`curves.py`, `final.py`; outputs `*.out`, `search.json`, `nested.json`.

"Jitter" = test-time earnings averaged over k shifted by -0.05..+0.05 (step 0.01). This stands in for the noise in a
model's fair value. A raw number can be luck: a charge that happens to sit just under a market-proven-fair bound.

## Recommendation
**a = 0.86 x median fair (all 6 sources), on every line; one multiplier and no tiers.**
(Optional: 1.10 on lines that a majority call not covered. This is worth about +0.7K in total and is not significant.)

## Why the current multipliers sit at a cliff
The k +0.02 drop comes almost entirely from 2 lines. On g29 l1, 0.92 x 1650 = 1518 sits under the proven-fair bound 1531.8
(ratio 0.928). On g5 l1, 0.92 x 1250 sits under the bound 1165.9 (ratio 0.933). Above those ratios the line becomes "?",
and the worst case keeps only the accepting reviewers: -22.0K and -16.7K. The fitted optimum k=0.92 is tuned to these
two coincidences.

## Out-of-sample numbers (worst-case earned)
| formula | WF 6-29 raw | WF jitter | hold-out 1-24 -> 25-29 raw / jitter |
|---|---|---|---|
| **global k on median, fitted with 0.05 smoothing (-> k 0.87-0.88 every year of the WF)** | 167.4K | 167.1K | 54.9K / 54.7K (k fitted = 0.87) |
| live type (cv tiers 0.15/0.40, raw argmax), refit WF | 171.7K | 169.6K | 56.0K / 54.9K |
| live type with smoothed fit (0.05) | 147.5K | 151.8K | 34.3K / 38.1K (the "some" tier jumps to 0.96 and loses the 22K line) |
| best raw WF of all 680 (cv tiers x max fair) | 181.7K | 164.3K | 56.4K / 46.0K |
| per-source track-record correction (median / weighted) | 146-166K | 156-164K | 46-57K |
| per category (trkw base) | 170.6K | 169.1K | 54.1K / 52.4K |
| **NESTED WF (family + smoothing chosen on earlier games only)** | **153.1K** | – | – |

Paired bootstrap over games (jittered WF): no candidate beats the live-type refit with any confidence. Global median
with 0.06 smoothing: difference -0.1K, P(better) 0.47. Category (trkw base): -0.5K, P 0.45. Size (trkw base): +0.1K,
P 0.47. The nested result (153K, below every simple refit) shows that searching over richer models is net overfitting.
Without the 2 cliff lines, every candidate lands within 141-153K jittered WF.

## Things that do not help (and why)
- **Tiers on disagreement (cv).** The "disagree" tier is 105 of 106 lines that most sources call not covered. Those 106
  lines are worth only 7.5-10K over k 0.7-1.3, so the 1.16 multiplier is noise. The agree and some tiers both have
  their jitter optimum at 0.87-0.88. Moving the thresholds to 0.05/0.25, 0.10/0.30, 0.20/0.50, ... does not help.
- **Coverage-vote tiers.** The votes are all-or-nothing (95 lines at 6/6, 101 at 0/6, 5 split), so they give the same
  split as above.
- **Quantile or blend base.** Min, q25 and the track-record bases are about equal to the median. Mean, q75, max,
  "high" and blends with "high" lose 15-35K on the hold-out. The max base looks good raw only by luck at the thresholds.
- **Track-record correction.** Across sources, the market's proven-fair bound divided by the median fair has a median of
  1.04 (IQR 0.83-1.38), so the bias is not consistent. The corrected bases are no better.
- **Category or size multipliers.** Tied with the live type, with more parameters.

## Sensitivity and the cost of a safety margin (worst-case earned, all games; in-sample, so secondary)
Jittered curve for the global multiplier on the median: 0.70 183.8K · 0.76 201.8K · 0.80 211.0K · 0.84 215.2K ·
**0.86 216.6K · 0.87 217.5K (peak)** · 0.88 216.1K · 0.90 210.2K · 0.92 202.6K · 0.94 194.2K · 1.00 163.0K.
The jitter peak is 0.87 on all lines, on games 1-24 alone, on 25-29 alone, and in the agree and some tiers alike.
- k=0.86, raw values in its ±0.04 neighbourhood: 217.7 / 219.7 / 212.4 / 216.6 / 218.4K. **Flat.**
  Compare the live formula: +0.02 = -22K, +0.04 = -39K.
- Live formula raw 227.5K but jittered 211.9K. 0.86 everywhere: raw 212.4K, jittered 216.6K.
  On the 25-29 hold-out: 55.97K vs 53.95K raw, 54.9K vs 54.1K jittered.
- **Margin cost** (from the 0.87 peak, jittered): -0.03 costs about 2.3K, -0.07 about 6.5K, -0.11 about 15.7K.
  Over-charging is costlier: +0.05 costs 15K and +0.07 costs 23K. Walk-forward with the fitted k shaded by m:
  m = 0 .. 0.10 keeps 164-168K, and m = 0.15 gives 154K.
  **A 0.02-0.04 downward margin is close to free. Never shade upward.**

## Bottom line
The richer models are no better out of sample than one multiplier on the median. Choose the multiplier on the jittered
curve and k ≈ 0.86-0.87 is stable in every walk-forward step. It gives up about 15K of in-sample "fit" (the two
coincidental lines) in exchange for a flat neighbourhood. The earned side's upside is limited. The remaining gap to the
top teams is not in the charge multiplier.
