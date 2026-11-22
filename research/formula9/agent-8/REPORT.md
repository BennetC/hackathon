# Formula agent 8: "median of three families" rule

All numbers are replayed net (K EUR) as **worst / best / midpoint**. Games 1-46 are the games with all 9 researchers and the 4 judges.
Odd games (23) are the fit set; even games (23) are the validation set and were never tuned on. My per-line replay
(`lib.py`) matches `fable_vs_opus.replay` to 4e-11 on every game, and it reproduces the baselines exactly.

## The rule (per line)

```
cov  = share of the 9 researchers saying covered AND related
if cov <= 1/2:  a = 0, b = 0                          (Daniil's rule: don't charge lines the majority calls uncovered)
F3 = median fair of group 3          (2 Fable + 1 Opus: bottom-up prompt with market price book)
F6 = median fair of groups 1+2       (the 6 old sessions pooled)
J  = median charge a of the 4 judges  (j-all9, j-g1, j-g2, j-g3; zeros dropped)
E  = median(F3, F6, J)                (zeros dropped)
a  = 0.90 * E        (raw odd-game peak is 0.92)
b  = 0.98 * E
```

Why each term is there:
- **E = median of three independent families.** Each family can be badly wrong on its own: group 3 is weak in early games,
  the old 6 sometimes split widely, and the judges sometimes lowball. The median of three throws away whichever family is the outlier on that
  line. Nearly all of the gain over the baselines comes from lines where one family was far off. Examples: g29 line 1
  (F6 1650, F3 2000, J 700, market lo 1532) and g33 (old groups 1700 vs F3 1250). There Ruben's mean was pulled above t
  and got rejected, worth +21.6K and +19.1K in the worst case.
- **a = 0.90-0.92 × E.** Overpricing loses the whole line, while underpricing loses only the gap. Other teams also accept
  only up to their own threshold, which is near t, so the best charge sits a few percent under an unbiased estimate.
- **b = 0.98 × E.** Rejecting a fair bill costs an extra 0.5a, and accepting an inflated one costs the full a. So we should
  accept only while P(fair) > 2/3, which means b sits slightly under the central estimate. Using the same E for both a and b keeps
  the rule to one estimate and two multipliers.
- **Coverage = majority of the 9 researchers.** On the odd games, 187 of 193 lines are 9/9 or 0/9, so this choice hardly matters.
  Using the group-3 majority instead gives the same results to within 1K.

How I chose it, on odd games only: I compared 14 bases for a and 18 bases for b (single groups, judges, mins, means,
the P10-to-median quantile of group 3, discounts for disagreement). `median(F3, F6, J)` was the best base on both
sides and is also one of the simplest. I chose k by the worst case of its ±0.02 neighbourhood, so it sits on a plateau
rather than at the cliff. That criterion gave k = 0.90, and I computed it before looking at any even game. The raw
odd peak is k = 0.92. m = 0.98 is both the peak and the plateau.

## Results (worst / best / mid, K EUR)

| rule | odd games (fit) | even games (validation) | even 36-46 |
|---|---|---|---|
| **a=0.90E, b=0.98E** | **+84.1** / +135.5 / +109.8 | **+60.4** / +112.4 / +86.4 | +24.9 / +42.7 / +33.8 |
| a=0.92E, b=0.98E (odd peak) | +92.1 / +143.1 / +117.6 | +61.8 / +119.0 / +90.4 | +23.4 / +46.2 / +34.8 |
| Ruben avg 2 groups (live) | +50.6 / +176.4 / +113.5 | +47.2 / +198.0 / +122.6 | +24.7 / +62.1 / +43.4 |
| Ruben avg 3 groups | +47.9 / +197.6 / +122.7 | +57.0 / +197.0 / +127.0 | +26.8 / +63.9 / +45.3 |
| (ref) Ruben, group 3 alone | +54.5 / +189.9 / +122.2 | +51.4 / +181.9 / +116.7 | +32.0 / +71.2 / +51.6 |
| extra column, not approved: uncovered lines a=0.90·J | +86.0 / +138.0 / +112.0 | +60.4 / … | +24.9 / … |

Split into the two sides, odd games (earned / paid, worst case): rule 0.92 earned 275.5K, paid 183.4K. Ruben-2 earned 246.7K, paid 196.1K.
Both sides improve.

## Robustness (worst-case net: odd / even / even 36-46)

- k: 0.85 → +70.5/+44.0/+15.7 · 0.88 → +74.7/+54.9/+22.1 · **0.90 → +84.1/+60.4/+24.9** · 0.92 → +92.1/+61.8/+23.4 ·
  0.95 → +56.3/+35.9/+6.8 · 0.97 → −19.9/+5.7/−24.8. **There is a cliff just above 0.92.** Going 0.02 lower costs little,
  but going 0.03-0.05 higher loses 30-110K. This is the reason to use 0.90 live.
- m: flat. Values from 0.93 to 1.03 all land within 7K of the best on odd and within 3K on even.
- Bootstrap over games (4000 resamples), worst-case difference rule(0.90) − baseline:
  - odd vs Ruben-2: median +31K, P(>0) = 0.90
  - even vs Ruben-2: median +12K, P(>0) = 0.88
  - even vs Ruben-3: median +3K, P(>0) = 0.63
- Bootstrap of the best k on odd games: 0.92 in 51% of resamples, the rest spread over 0.84-0.95. The best m is 0.96 or 0.98 in 92% of resamples.

## Caveats (honest)

- **The best case and the midpoint are worse than the baselines** (even midpoint +86K vs +123K). All of that gap is on the charge side.
  The best case counts every unproven charge as "fair, rejected, paid 1.5a", so it rewards charging into the unknown zone.
  The worst case does the opposite. If the midpoint matters as much as the worst case, this rule is not a clear win.
- **The gain is concentrated in a few games** (g29, g33, g18, g32: lines where one family was far off). In the recent
  block the rule only matches the baselines: even 36-46 gives +24.9 vs +24.7 and +26.8, and odd 37-45 gives +12.6 vs +12.9 and +12.5.
  Group 3 alone does better there (+32.0), because group 3 has improved over time and the other two families now dilute it.

## Recommendation

If the target is the worst case, use **a = 0.90·median(F3, F6, J), b = 0.98·median(F3, F6, J), and charge 0/0 when the majority
says uncovered.** On worst-case net it beats both baselines on the fit set (+84K vs +51K / +48K) and on the validation set
(+60K vs +47K / +57K). It has only two multipliers, b is robust, and k sits 0.02 below a cliff. Keep watching
group 3 alone: if its lead in the recent games continues, weighting F3 more heavily is the next thing to test (that should be fitted on odd games again).

Scripts: `lib.py` (loader, exact per-line replay, baselines), `common.py`, `aside*.py` / `bside.py` (searches on odd games),
`evar.py` (variants of E), `final.py` / `final2.py` (results, robustness, bootstrap).
