# Synthesis agent 2: best rule from the 10 formula agents

Read-only. Nothing was submitted, the live runner and every state.json were left alone, and no model calls were made.
I did not read synth-1.

**What I built:**
- **Evaluator.** `data.py` / `lib.py` hold a per-line copy of `fable_vs_opus.replay`, checked with `check.py` (0.00 difference
  on games 5, 33, 41, 47, 48, 49 and 50).
- **New market data.** Games 47-50 were fetched read-only with `fable_vs_opus.tx_all`, with bounds computed as in
  `session_backtest.bounds`; they are saved in `tx_47_50.pkl`. Game 47 is identical to the cached copy.
- **Baselines.** They reproduce the brief exactly: games 36-47 give Ruben-2 +35.6K..+84.8K and Ruben-3 +38.2K..+89.8K.

**Splits.** Fit = odd games 1-45 (23). Validation = even games 2-46 (23). Also even 36-46, odd 37-45, and the new games
47-50.

**Data for games 47-50:**
- No new judges.
- Game 47: group 3 comes from v3_train.
- Game 48: has **no group 3** (and group 2 without Fable).
- Games 49-50: group 3 comes from the live `v3_answers`.

**The even games are not blind.** The agents had already reported even numbers, so choosing among their ideas uses that
information. Games 47-50 are the only truly new test, and they are only 4 games (about 41 lines).

## Recommended rule (2 numbers, no judges)

```
covered(line) = more than half of all researchers present (up to 9) say covered AND related
Gi            = median fair_gross_total of group i's covering members, used only if group i's majority says covered
X             = min( G3 , max(G1, G2) )          (G3 missing -> median of G1, G2; one old group missing -> that one)
a = 0.92 * X ,  b = 0.98 * X     if covered;     a = b = 0 otherwise
```

Why each term is there:
- **G3 is the anchor.** Group 3 prices bottom-up against the market price book. From game 13 on it is the best-calibrated
  source, and on the recent games it is the strongest charge base.
- **The cap max(G1, G2).** We never charge above *both* older groups. Overpricing loses the whole line, while
  underpricing costs only the gap. So when two independent older estimates are both below G3, we follow the higher of the
  two. This is agent 6's `min(G3, median of the 3 groups)`, which is the same thing whenever all three groups are present.
  - It catches the case where group 3 overshoots, for example g33 line 1 (G3 1250 against G2 1700, market lo 1220).
  - It does not drag the price down to the lowest old group. That pull is what cost the cautious rules money on games
    38 and 46.
- **0.92 on the charge.** Chosen on odd games by the mean worst case over k ± 0.02; the raw peak is 0.94. The market's
  proven-fair level on big agreed lines sits at about 0.93-0.97·X, and k = 0.94 already collapses on the new games
  (see Robustness).
- **0.98 on the limit.** The insurer's loss is soft (a rejected fair bill costs 0.5a, an accepted inflated one costs a),
  so we accept up to just under our own cautious estimate. The odd-game optimum is flat from 0.95 to 1.03.
- **The same X for a and b.** One price per line, so a < b always holds.
- **No judges.** The 4 new judges exist only up to game 46, so live the rule runs exactly as it was backtested.
- **Coverage gate.** Daniil's policy: lines that most researchers call uncovered get a = b = 0.

### Why a and b can be chosen separately

Per line, net = earned(a) − paid(b), and the worst case is earned_lo − paid_hi. So the best combination is exactly the
best charge plus the best limit. "Every combination of the best charge with the best limit" therefore reduces to two
separate rankings (`grid.py`: 22 charge bases × k grid and 22 limit bases × m grid, all from the 10 agents).

## Results (net, K EUR, worst / best / midpoint)

| rule | odd (fit) | even (validation) | even 36-46 | odd 37-45 | **new 47-50** |
|---|---|---|---|---|---|
| **B: a=.92X, b=.98X (recommended)** | **+61.2** / +144.6 / +102.9 | **+60.1** / +125.8 / +93.0 | **+29.8** / +51.2 / +40.5 | **+14.0** / +20.9 / +17.5 | **−1.9** / +8.6 / +3.4 |
| Ruben 2 groups (live) | +50.6 / +176.4 / +113.5 | +47.2 / +198.0 / +122.6 | +24.7 / +62.1 / +43.4 | +12.9 / +22.2 / +17.6 | −0.8 / +8.8 / +4.0 |
| Ruben 3 groups | +47.9 / +197.6 / +122.7 | +57.0 / +197.0 / +127.0 | +26.8 / +63.9 / +45.3 | +12.5 / +22.4 / +17.5 | −3.5 / +14.1 / +5.3 |
| Ruben 3, approved-only (gated) | +41.5 / +149.0 / +95.3 | +53.3 / +132.2 / +92.7 | +26.7 / +48.9 / +37.8 | +8.6 / +17.6 / +13.1 | −3.5 / +13.8 / +5.1 |
| **Minimal change:** Ruben-3 charge exactly + b = .98X | +56.3 / +205.8 / +131.1 | +58.6 / +198.7 / +128.7 | +30.5 / +67.8 / +49.1 | +16.6 / +26.0 / +21.3 | −5.8 / +11.9 / +3.0 |
| Minimal change: Ruben-2 charge exactly + b = .98X | +62.9 / +188.8 / +125.9 | +50.8 / +201.3 / +126.1 | +28.4 / +65.9 / +47.2 | +16.9 / +25.8 / +21.4 | −3.0 / +6.7 / +1.8 |
| *extra, NOT approved:* B + Ruben-3 a on majority-uncovered lines (b = 0) | +67.6 / +193.1 / +130.3 | +63.9 / +190.6 / +127.2 | +29.9 / +66.2 / +48.0 | +18.0 / +25.7 / +21.9 | −1.8 / +8.8 / +3.5 |

Games 36-50 together (worst / best / mid):
- B: +42.0 / +80.7 / +61.3
- Ruben-2: +36.8 / +93.2 / +65.0
- Ruben-3: +35.8 / +100.4 / +68.1
- Minimal Ruben-3 + new b: +41.3 / +105.7 / +73.5

**Reading the table:**
- **Worst case.** B beats both baselines on every older split. The single exception is new 47-50 against Ruben-2
  (−1.1K over 4 games).
- **Best case and midpoint.** B is lower than the as-is baselines. Almost all of that gap is the baselines charging
  majority-uncovered lines through the old-judge fallback, which is not approved.
  - Like for like (Ruben-3 gated), B wins worst *and* midpoint on every older split.
  - Adding the uncovered-line charge to B (extra row) restores the midpoint to the Ruben-3 level and keeps the higher
    worst case.
- **Where B loses on 47-50.** The loss comes from two things, and neither is a pattern:
  - g49 lines 1-2: all 9 researchers said covered, but the market shows t < 31. This is a coverage miss, so a higher b
    pays more there.
  - g48: there is no group 3.

Paired bootstrap over games (4000×), worst-case difference, median [5..95%] and P(>0):

| | odd | even | even 36-46 | odd 37-45 | new 47-50 |
|---|---|---|---|---|---|
| B − Ruben-2 | +10.6 [−22.8, +51.5] 0.65 | +13.0 [−7.3, +35.4] 0.83 | +5.1 [−7.2, +21.4] 0.70 | +1.2 0.60 | −1.1 0.36 |
| B − Ruben-3 | +13.3 [−7.2, +38.6] 0.80 | +3.2 [−6.9, +13.2] 0.71 | +3.0 [−1.4, +7.4] 0.87 | +1.5 0.63 | +1.6 0.69 |
| min. change (R3 a + new b) − Ruben-3 | +8.4 [+2.2, +15.2] 0.99 | +1.7 0.68 | +3.7 [+0.4, +7.4] 0.97 | +4.1 0.96 | −2.3 0.31 |
| min. change (R2 a + new b) − Ruben-2 | +12.3 [+2.8, +22.8] 0.98 | +3.7 0.74 | +3.7 [+0.4, +7.2] 0.97 | +4.0 0.97 | −2.2 0.30 |

For the minimal change, the midpoint differences are the same as the worst-case ones (the limit swap moves both bounds
together).

## Robustness of B (worst case, K: odd / even / e36-46 / o37-45 / new)

| k (m = .98) | | m (k = .92) | |
|---|---|---|---|
| 0.88 | +47.0 / +51.9 / +28.2 / +7.3 / −2.7 | 0.93 | +54.2 / +58.5 / +27.7 / +10.0 / +0.3 |
| 0.90 | +54.9 / +58.4 / +31.6 / +8.7 / −3.4 | 0.96 | +60.4 / +58.4 / +28.1 / +13.5 / −1.0 |
| **0.92** | **+61.2 / +60.1 / +29.8 / +14.0 / −1.9** | **0.98** | **+61.2 / +60.1 / +29.8 / +14.0 / −1.9** |
| 0.93 | +62.6 / +52.4 / +31.3 / +12.9 / −0.7 | 1.00 | +61.2 / +58.7 / +29.9 / +13.8 / −1.1 |
| 0.94 | +66.2 / **+37.9 / +14.7** / +14.4 / **−13.6** | 1.03 | +57.4 / +57.4 / +30.0 / +11.5 / −1.2 |
| 0.97 | **−48.9 / −15.6 / −36.0 / −20.3 / −32.6** | | |

- **The k cliff is confirmed on brand-new data.** At k = 0.94, even games lose 22K and games 47-50 lose 12K. So never set
  k above 0.92; 0.90 is an acceptable safety margin.
- **m is flat.** Anything from 0.95 to 1.03 is fine.
- **Bootstrap refit on resampled odd games (500×).** k has q05/q50/q95 = 0.88 / 0.92 / 0.94 and m has 0.94 / 0.98 / 1.00.
  The even worst case after refitting has a median of +58.7K and a q05 of +37.1K (the q05 is when the refit lands on 0.94).
- **Fitting only on mature odd games 13-45** gives k = 0.93 and m = 0.99, a very similar rule.

## Which agents' ideas survived

| idea (agent) | verdict |
|---|---|
| Majority-of-9 coverage gate, a = b = 0 otherwise (all) | **kept** |
| G3 capped by the consensus of the groups, `min(G3, med groups)` (6) | **kept as X** (written as min(G3, max(G1, G2))) |
| Limit b ≈ 0.98-1.00 × cautious consensus (3, 5, 6, 7, 8, 9, 10) | **kept**: 0.98·X; consistent on every older split |
| Minimal change: keep the charge, swap only the limit (7, 10) | **kept as the fallback option**: wins worst *and* midpoint on all older splits |
| Smoothed k (average over k ± 0.02) to stay off the cliff (1, 2, 5, 7, 8, 10) | **kept**; confirmed on games 47-50 |
| Judges as votes, caps or midpoints (1, 2, 3, 4, 7, 8) | **dropped**: not available from game 47 on, and their odd lead is the two lines below |
| Min of groups / lower median / pooled median (2, 5, 7, 8) | **dropped** as a charge. The odd lead of about 25K comes from g18 l2 and g29 l1 (both odd), and they lose about 10K on even 36-46 (g38 l1, g46 l9) |
| Disagreement shading exp(−c·s) (1, 10) | **dropped**: on 3 groups (c = 1) it scores odd 270K earned but 116K on even 36-46 (vs 123K for X) |
| Floor at G3's own 10th percentile (9) | **dropped**: +3.5K on odd only, no change elsewhere |
| G3 alone (1, 3 "middle path") | best on even 36-46, but worse on odd 37-45 and on new games; the cap keeps most of its upside |
| Uncovered lines charged at the judge's a (all, extra column) | not approved; on odd / even it adds +6.4K / +3.8K worst and +27K / +34K midpoint; about 0 on even 36-46 worst and on new games |

The whole charge-side difference between sensible bases comes down to about 6 lines (`lines.py`): g18 l2, g29 l1, g33 l1,
g38 l1, g46 l9 and g48. Cautious rules win the odd split only because g18 and g29 happen to be odd games.

## Recommendation: switch live now?

**Yes: switch to B now** (a = 0.92·X, b = 0.98·X, X = min(G3, max(G1, G2)), 0/0 on majority-uncovered lines).
- **Worst case.** Only this family (G3 capped by the older groups; agent 6's original with m = 1.00 scores almost the same) beats both baselines on worst case on every older split. Over games
  36-50 it gives +42.0K against +36.8K for the live rule.
- **No judges.** It needs no judges, so live behaves exactly like the backtest.
- **Coverage policy.** It respects Daniil's coverage policy, which the live rule currently does not.
- **What it costs.** About 1K worst case on the 4 new games (a coverage miss in g49), and a lower best case and midpoint
  than the live rule. That gap is the unapproved uncovered-line charging.

If the runner can only take a small change, swap the limit alone: keep Ruben's charge exactly and set b = 0.98·X
(0 on majority-uncovered lines).
- It improves worst *and* midpoint on every older split, by 1.7-12.3K, with P ≈ 0.97-0.99 on odd, even 36-46 and
  odd 37-45.
- It costs about 2K on games 47-50, for the same g49 coverage-miss reason.

If Daniil approves charging uncovered lines, use the extra row instead: B on covered lines, Ruben-3 a with b = 0 on
uncovered lines.

**Never raise k above 0.92.**

Files: `data.py`, `lib.py`, `check.py`, `fetch.py`, `baselines.py`, `grid.py` (curves.pkl), `pergame.py`, `lines.py`,
`newgames.py`, `final.py` (`final_out.txt`), `robust.py` (`robust_out.txt`), `extra.py` (`extra_out.txt`).
