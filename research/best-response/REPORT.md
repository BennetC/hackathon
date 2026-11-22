# Best response to the other teams (research agent 3)

Scripts (all under `research/best-response/`): `build.py` (per-line features + replayed income/payment curves → `data.pkl`),
`opp.py` (opponent model), `wf.py` (walk-forward best response, 96 configs → `wf_out.txt`), `robust.py` (trajectories,
curve shapes, sensitivity, bootstrap → `robust_out.txt`), `margin.py` (safety margins). Data: 201 lines, games 1-29, 6 pooled
sources (3 v1 Opus + Fable + 2 Opus). Scores are `fable_vs_opus.replay` net_lo..net_hi summed over test games 6-29; every
"walk-forward" number is fitted only on games < g.

## 1. Model

Per line, against reviewer j with acceptance limit b_j and secret fair t, a charge a earns
`a·[S·(1+0.5·R) + (1−S)·(1−R)] = a·(1 − R(a) + 1.5·S(a)·R(a))`, with S(a) = P(t ≥ a), R(a) = share of reviewers with b_j < a.
As insurer, raising b past an incoming charge a_i saves 0.5·a_i if fair and costs a_i if inflated, so
**b\* = the largest charge level where P(fair | charge) ≥ 2/3** — it does not depend on how many teams charge there, only
on where the fair/inflated mix crosses 2/3.

S and R are strongly correlated within a line (uncovered lines: t = 0 *and* everyone's b ≈ 0), so S and R are not estimated
separately: the best response is the argmax of the per-line replayed income curve summed over past lines (that sum is exactly
E[a(1−R+1.5SR)] with S, R estimated jointly), argmin of the payment curve for b.

## 2. What the other teams do (relative to our pooled median fair `med`, games 1-29, descriptive)

- Charges: median 0.84×med on agree lines (q25 0.57, q75 1.11); 0.45×med on disagree lines plus 587 hidden (all-rejected, inflated) charges.
- Acceptance (majority-covered lines): share of reviewers certainly accepting a = x·med: 0.67 @0.6, 0.51 @0.8, 0.41 @0.9, 0.31 @1.0, 0.20 @1.2, 0.07 @1.7.
  Reviewers' accepted-max median ≈ 0.80×med, rejected-min median ≈ 0.96×med → a mass of acceptance limits at ~0.93-0.96×med.
- P(fair | others' charge = x·**min** fair): 0.88 @0.6-0.7, 0.77 @0.8, 0.69 @0.9, 0.62 @1.0, 0.45 @1.1, 0.38 @1.2-1.6.
  **Crosses 2/3 at x ≈ 1.0** → b\* ≈ 1.0×min fair (consistent with formula.py's 1.04). Relative to med the curve is flat ~0.5
  (med is a worse reference for b); relative to min *low* it crosses at ~1.2-1.6 (noisier).

## 3. Best-response curves (in-sample, kEUR worst/best case, games 1-29)

Income vs a = x·med: agree 0.84: 129.5 · 0.88: 129.8 · **0.92: 135.3** · 0.96: 100.6 (cliff, −26%) · 1.04: 77.3.
some: peak 0.84 (82.3), 0.92: 80.5, 0.96: 61.2. disagree: 7-10 for every x (worst case flat; higher x only raises net_hi).
Pooled: 0.84: 219.7 · 0.88: 216.6 · **0.92: 224.3** · 0.96: 170.7.
Payments vs b = m·min: worst case 0.96: 144.2 · 1.00: 143.8 · **1.04: 143.6** · 1.08: 144.6 · 1.20: 148.6 — flat, robust.

The best response for a sits right under the other teams' acceptance mass (0.92×med); being 4% above it loses ~25%,
being 4-8% below it loses ~2-3%. Shape is asymmetric, yet a walk-forward safety margin (argmax − 0.02..0.06) did *not* help
(−4K..−6K worst case), because the cliff location was stable across games.

## 4. Walk-forward results (test games 6-29, fit on < g)

| strategy | net_lo .. net_hi | lo 6-17 / 18-29 | neg games (lo) |
|---|---|---|---|
| formula.py constants (fitted in-sample on 1-29) | +54.8K .. +255.1K | +17.4K / +37.4K | 4 |
| formula grid nested walk-forward (cv tier k, m·min) | +44.1K .. +244.8K | +13.1K / +31.0K | 5 |
| **BR pooled: a = k\*·med, b = m\*·min (walk-forward)** | **+44.8K .. +224.2K** | +17.3K / +27.5K | 4 |
| BR by coverage vote (all/maj/min) | +45.0K .. +219.3K | +16.9K / +28.1K | 4 |
| BR by tier+vote / category / tier+category | +43.4K / +30.8K / +37.7K (lo) | | 5-7 |
| BR with a on medhigh or mean instead of med | +1K .. +34K (lo) | | 4-8 |
| BR optimising mid instead of worst case | −111K .. −57K (lo) | | 15-20 |
| old rule a=0.80F b=1.00F, coverage vote | +33.7K .. +79.5K | +9.2K / +24.5K | 5 |

b side (a fixed to nested tier rule): ref = min fair best (+44.1K); medlow +40.6K, minlow +38.2K, med −10K. Bucketing b by
tier/vote/category: ±1K, no gain.

Walk-forward argmax trajectory: pooled k = 0.92 in 20/24 test games (0.84 in 4); m = 0.98-1.04; agree-tier k = 0.92 in every
game; the "disagree" k jumps 0.92 → 2.08 → 1.22 → 0.62 → 1.16 (pure noise on the worst case).

## 5. Robustness

- Bootstrap over games (300×): pooled k p10/p50/p90 = 0.82/0.92/0.92; m = 0.96/1.04/1.10; disagree k = 0.98/1.22/1.56 (unstable).
- Fixed a sensitivity (b = 1.04·min, games 6-29): 0.84: +50.6K · 0.88: +45.2K · 0.92: +50.8K · 0.94: +31.9K · 0.96: +26.2K.
  Cliff on the high side confirmed; b 0.96-1.12 moves the result < 2K.
- Optimising the optimistic/mid case is badly overfit (unproven charges counted as paid); always choose on worst case.

## 6. Recommendation (practical formula, features available live)

```
med = median of the 6 sources' fair, mn = min of the 6 sources' fair
a = 0.92 × med      (every line; no extra multiplier for "disagree" lines — worst-case gain ≈ 0, bootstrap 0.98-1.56)
b = 1.04 × mn       (P(fair | charge) crosses 2/3 at ≈ 1.0 × min fair; flat 0.96-1.08)
```

This is formula.py with the disagree multiplier 1.16 → 0.92 and the partial-disagree 0.84 → 0.92 optional (0.84 vs 0.92 for
"some" is within noise: in-sample 82.3 vs 80.5K). Walk-forward it matches the 3-tier nested formula on the worst case
(+44.8K vs +44.1K), gives up the speculative upside on disagree lines (net_hi 224K vs 245K), and has one fewer unstable
parameter. Coverage votes, category, sources' low/high add nothing walk-forward. Do **not** push a above ~0.92×med: the
other teams' acceptance limits sit at 0.93-0.96×our median and crossing them costs ~25% of issuer income.
Caveat: games 6-29 only (24 games); the 0.92 cliff could drift if other teams change their b rules — re-check the agree-tier
argmax each game (it is the single number that matters).
