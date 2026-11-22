# Synthesis S3 (free hand): an improved live formula

Data: 250 lines from games 1-34. Games 1-29 use `tx_cache` with the 6 pooled sources. Games 30-34 use
`opponents/tx_30_34.pkl` with the live v2 answers: 3 sources in games 30-33 and 6 in game 34. The Fable judge's `a`
comes from the training `judge_ab` for games 1-29 and the live one for games 30+. The evaluator is `robustness/ev.py`,
which is identical to `fable_vs_opus.replay`. It reproduces formula.py at +83.9K (in-sample, games 1-29) and +54.8K
(games 6-29). All scores are worst-case (lo) net unless a range lo..hi is shown, and every fit uses the worst case.

Scripts: `prep.py` builds `lines.pkl`. `lib.py` and `exp.py` hold the evaluator and the walk-forward, hold-out and
bootstrap code. `run1.py`..`run8.py` run the experiments. `formula_s3.py` is the recommended formula; it matches the
evaluated rule on games 30-34 with 0 mismatches. Nothing was submitted and no models were called.

## Final recommendation

```
nc  = share of sources that say "not covered" or "not related"
if nc >= 5/6:  a = 0, b = 0                                  # uncovered guard (honest, and b = 0 is explicit)
else:          a = max(0.86 x median fair, min(J_a, 2 x median fair))   # J_a = Fable judge charge, if available
               b = 1.04 x lowest fair                         # unchanged
```

| (worst case unless lo..hi) | formula.py | **S3 final** | LIVE + J + guard (k tiers kept) |
|---|---|---|---|
| games 6-29, fixed constants | +54.8K..+255.1K | +47.6K..+117.2K | +51.7K..+122.2K |
| games 23-29 | +29.7K | +30.6K | +31.4K |
| **games 30-34, true out-of-sample** | +19.5K..+35.2K | **+22.6K..+56.6K** | +21.7K..+38.8K |
| honest walk-forward, family refit, games 6-34 (formula.py family W = +64.9K) | +64.9K | +68.3K (single smoothed k + J + guard) | +68.6K |
| **±5% noise on our median (jitter), games 6-29 / 30-34** | 44.3K / 13.2K (with guard) | **49.8K / 22.8K** | 49.5K / 16.4K |
| all multipliers shifted −0.06..+0.06, games 1-29 | 41.2 – 83.9K (+0.02 → −22K) | **77.0 – 83.4K (flat)** | 47.2 – 82.0K |
| same shift, games 30-34 | −34.5 – 19.5K | **18.7 – 25.2K** | −34.5 – 25.4K |
| bootstrap p5, games 6-34 | — | +23.8K | +25.0K |
| worst single game | −10.2K | −7.2K | −10.2K |

On raw replay over games 6-29, the final formula is about 7K below formula.py. 3-5K of that is the uncovered guard
giving up the free charge in games 10-22, which earns nothing since game 23. The rest is the two "cliff" lines that
the live 0.92 multiplier only just misses (g29 l1 at 0.928, g5 l1 at 0.933). On every forward-looking test it is equal
or better: games 30-34 +3.1K, median noise +5.5K / +9.6K, and the walk-forward family about +3.4K. It has no cliff:
moving every multiplier by ±0.06 changes the result by at most 6K, where formula.py loses 22K at +0.02.

Why the combination works: a lower base multiplier is flat but loses about 18K on its own (0.86 alone: −18K vs live,
P = 0.02). Taking the higher of that and the judge's charge recovers almost all of it, because the judge is the one
source that is sometimes higher than the formula and still fair. The judge works as cheap insurance against setting
the base too low, and the base no longer has to sit at the cliff.

If the team wants the smallest possible change instead, use **formula.py + J max + guard** (last column). It is best
on the raw replay, but it keeps the cliff: −16K to −18K worst case at a +0.02 shift.

## What worked (numbers)
1. **a = max(formula a, judge a)** is the only addition that is positive in every split.
   - Walk-forward family refit: +7.2K on games 6-29 (bootstrap P = 0.99, p5 +0.9K) and +10.6K on games 6-34
     (P = 1.00, p5 +3.2K).
   - Hold-out 25-29: +1.5K. Games 30-34: +3.3K.
   - Against the fixed in-sample constants the gain is smaller and less certain: +2.0K on games 6-29, P = 0.72,
     because one line (g19 l2, "?" worst case) costs 7K.
   - The gain comes from about 5 lines where the judge sat 0-2% under the proven-fair bound: g21 l17 +3.8K,
     g27 l1 +2.2K, g31 l3 +2.1K, g18 l2 +1.1K.
   - Capping the judge charge at c × median for c < 1.5 removes the gain. c = 2 is a free sanity cap.
   - Caveat: in g31 (and g32) FDN itself submitted the judge's charge, so the market `lo` there is FDN's own charge.
     That favours the judge in those games.
2. **Uncovered guard (>= 5/6 say not covered → 0/0).**
   - It costs −5.0K walk-forward over games 6-29 (the free option earned in games 10-22) and 0 since game 23: identical
     worst case on 23-29, and −1.2K on 30-34, from judge charges on uncovered lines that someone accepted.
   - "b = 0 only, keep a" costs −0.7K.
   - The guard is worth having for honesty and safety. It makes b = 0 explicit, so it does not depend on 2 sources
     writing fair = 0, and it stops the judge charging uncovered lines (judge `a` = 8000 on g30 l7).
3. **One flat multiplier, 0.86** (the charge-side finding). Combined with the judge max and the guard, it gives the
   flat curve in the table above.

## What did not work (numbers)
- **Charging near fair, as team 404 does** (all multipliers +0.04 / +0.07 / +0.10): −38K / −36K / −54K on games 1-29
  and −14K / −54K / −54K on games 30-34. 404's 1.5x farming depends on 404's own pricing. On our median, every step
  above 0.92 falls off the cliff. A higher k for the very tight sources (cv < 0.05, 22 lines): 0.94 → −16.5K,
  0.96 → −32K.
- **b floor on large lines** (b = max(1.04 × min, β × median) when median ≥ X):
  - On all lines: −13K to −68K, because it accepts hidden inflated bills on lines where the sources split.
  - Only on lines all sources call covered: −1.2K to −4.5K on games 1-29 and −2K to −4K on games 30-34.
  - The walk-forward fit never picks it.
  - The g31 disaster (404 and Humble Legends with b ≤ 1440 against t ≥ 2900) does not happen to us. Our sources agreed,
    so b = 3068.
- **Per-line expected-value fit** (smoothed income curve, σ = 0.02-0.05, or a drift-robust argmax over the tiers):
  −5K to −29K walk-forward. It lands on 0.82-0.90 in some steps and loses whole lines. A smoothed single k
  (0.84-0.86) is −12K alone but +8.3K with the judge max.
- **Fixed or capped disagree multiplier** (0.92 or 1.10): −0.6K / +0.3K, which is noise. With the guard, this tier is
  almost only uncovered lines, so it no longer matters.
- **Single k with tiered fit**: +0.7K, P = 0.53, noise.

## Caveats
- Games 30-34 are only 5 games, with about 6 informative lines: g31 l3, g33 l1, g33 l3, g34. Game 33 l1 (−9-10K for
  every rule: the sources were 15% above the inflated bound) dominates the variance.
- Games 30-33 have only 3 sources. Live now uses 6, as in game 34.
- The judge has to be available at decision time. If it is missing, the rule falls back to 0.86 × median, which is
  about 18K worse over games 6-29. Make sure the judge call succeeds, or fall back to formula.py's 0.92 tiers for that
  game.
