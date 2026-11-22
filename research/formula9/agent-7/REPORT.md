# Formula 9: agent 7

Read-only. I tuned only on odd games 1-45 and validated on even games 2-46 (games 1-46 have every source; game 47 has no judges, so it is left out).
Scripts are in this folder: `final.py` produces every number below, and `data.py` is an exact per-line copy of `fable_vs_opus.replay`, checked against it to the euro on 5 games (`check.py`).

## Rule
Each line gets up to four independent estimates of the secret fair value t:

- E1, E2, E3: the median `fair_gross_total` of researcher group 1, 2 and 3.
- EJ: the judges' midpoint, the geometric mean of all 8 judge numbers (a and b of j-all9, j-g1, j-g2, j-g3) that are > 0.

```
T = lower median of the available {E1, E2, E3, EJ}   (2nd lowest of 4; the median of 3)
covered = more than half of all available researchers (up to 9) say covered AND related
a = 0.90 * T,  b = 0.98 * T      if covered and T exists, else a = b = 0
```

Why each term is there:
- **Four estimates.** The three groups and the judges make mostly separate errors. The judges have also learned from market feedback.
- **EJ = geometric mean of the judges' a and b.** Judges set a below fair and b above it on purpose, so the midpoint of the two is their implied fair value.
- **Lower median.** An overpriced charge loses the whole line, but an underpriced one loses only a little. So we sit below the consensus. The very lowest estimate is often an outlier (one group misread the line), so we skip it. Games 29 and 33 show this: one big line each where the group means overshot the market's proven-fair level. The baselines earned 0 on those lines; this rule earned +19.6K and +16.7K.
- **0.90 on the charge.** This keeps a safety margin below the cliff at k ≈ 0.94-0.96. I picked k by the best average over k ± 0.04 on odd games, which I fixed before looking (the single peak was 0.92).
- **0.98 on the limit.** The loss on the limit is soft and nearly symmetric: a rejected fair bill costs 0.5a, an accepted inflated one costs a. So b sits at about T.
- **Coverage gate.** Majority of the researchers, as Daniil approved. Dropping the gate is shown only as an extra column.

There are 2 tuned numbers. I tried about 60 estimators on odd games: single groups, min, means, quantiles, judge-only, blends, and spread-dependent shading. The 2-number refinements gained at most 7K on odd, which is within the noise, so I rejected them.

## Results (net in EUR, worst .. best, midpoint in brackets)
| split | **this rule** | Ruben 2 groups (live) | Ruben 3 groups | extra: no coverage gate |
|---|---|---|---|---|
| odd (fit) | **+81.0K** .. +132.3K (106.7K) | +50.6K .. +176.4K (113.5K) | +47.9K .. +197.6K (122.7K) | +59.9K .. +177.3K |
| even (validation) | **+54.7K** .. +113.2K (83.9K) | +47.2K .. +198.0K (122.6K) | +57.0K .. +197.0K (127.0K) | +50.5K .. +122.0K |
| even 36-46 | **+19.8K** .. +39.4K (29.6K) | +24.7K .. +62.1K (43.4K) | +26.8K .. +63.9K (45.3K) | +19.4K .. +40.6K |

Paired by game, worst case, rule minus baseline, with a 5000× bootstrap over games:

| split | vs Ruben 2 | vs Ruben 3 |
|---|---|---|
| odd | +30.4K (5-95%: -10.8K..+78.9K) | +33.1K |
| even | +7.6K (5-95%: -11.1K..+29.3K; P(<0) = 0.28) | -2.3K (P(<0) = 0.58) |
| even 36-46 | -4.9K (better in 1 of 6 games) | -7.0K |

What the paired numbers show:
- **Where the worst-case gain comes from.** Almost all of it comes from avoiding a few large overcharged lines. On most games the rule earns 1-4K less than the baselines on the charge side, because 0.90·T sits below the consensus when the consensus was right.
- **Best case and midpoint.** Both are much lower than either baseline. The lower charges land in proven-fair territory, so the upside of 1.5× on uncertain lines is gone.

Robustness, worst case odd / even (base case: k_a 0.90, k_b 0.98 → +81.0K / +54.7K):

| change | odd | even |
|---|---|---|
| k_a 0.88 | +71.5K | +51.6K |
| k_a 0.92 | +87.4K | +55.8K |
| k_a 0.85 | +67.1K | +44.3K |
| k_a 0.95 | +59.8K | +29.9K (cliff) |
| k_b 0.96 | +81.9K | +53.6K |
| k_b 1.00 | +80.9K | +55.2K |
| k_b 0.93 | +73.7K | +52.7K |
| k_b 1.03 | +79.0K | +54.5K |

When I re-picked the values on 2000 bootstrap resamples of the odd games, k_a came out at 0.88-0.90 in 85% of them and k_b at 0.98-1.00 in 90%.

## The robust part: the acceptance limit
Keeping each baseline's charge a but replacing its limit with **b = 0.98·T (0 if not covered)** improves both baselines on every split and on worst, best and midpoint alike. Nothing extra was tuned for this:

| | odd | even | even 36-46 |
|---|---|---|---|
| Ruben 2 a + this b | +62.9K .. +188.4K (from +50.6K .. +176.4K) | +50.3K .. +200.8K (from +47.2K .. +198.0K) | +25.3K .. +62.9K (from +24.7K .. +62.1K) |
| Ruben 3 a + this b | +56.3K .. +205.4K (from +47.9K .. +197.6K) | +58.2K .. +198.3K (from +57.0K .. +197.0K) | +27.4K .. +64.7K (from +26.8K .. +63.9K) |

## Recommendation
1. **Adopt the limit b = 0.98 × lower-median(E1, E2, E3, EJ), with b = 0 on lines a majority of researchers call uncovered.** It is a consistent, low-variance gain on both splits and every metric. With 3 groups, Ruben 3's charge plus this limit is the best combination on the even (validation) games: +58.2K .. +198.3K.
2. **Use the full rule (a = 0.90·T as well) only as worst-case insurance.** It gives the best odd worst case (+81.0K) and beats Ruben 2 on even (+54.7K vs +47.2K). But it roughly ties Ruben 3 on even, loses on the recent even block, and gives up 40K+ of midpoint. The gain rests on a few big lines where the consensus overshoots. I would not switch the charge on this evidence alone.
