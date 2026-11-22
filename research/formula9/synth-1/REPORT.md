# Synthesis 1: the best rule built from the 10 formula agents

This was read-only work: nothing was submitted, no live runner or state.json was touched, and no model calls were made.
Market data for games 47-50 was fetched read-only into `tx_47_50.pkl` (`fetch.py`).

The evaluator (`core.py`) is a per-line copy of `fable_vs_opus.replay`:
- It matches replay to the cent on games 5, 20, 33, 41 and 47-50 (`verify.py`).
- It reproduces the baselines for games 36-47: Ruben 2 groups +35.6K..+84.8K, Ruben 3 groups +38.2K..+89.8K.

Splits:
- **Odd 1-45** is the fit set (all exact values were chosen here).
- **Even 2-46** is the validation set. It is **not blind any more**: the 10 agents reported even numbers, and choosing among their ideas uses that information.
- **Even 36-46** is the recent block.
- **New 47-50** are brand-new games, never seen by any agent. Game 48 has no group 3 and no old-judge answer; games 49-50 use the live `v3_answers`.

## Key constraint found: the 4 new judges do not exist live

The judges j-all9 / j-g1..3 exist only for games ≤ 46, so any rule that leans on them would run without them in live play.
What is live-available: G1, G2, G3 (live from game 49) and the old Fable judge (`judge_ab`, still produced live).
The recommended rule therefore uses only these. Judge-based rules from agents 1, 2, 3, 4, 7 and 8 are shown for reference only.

A useful finding: the old judge works as a replacement 4th vote. On odd games, the lower-median of {G1, G2, G3, old-judge a} as a charge base earns 274.4K. That beats the same base with the new judges' midpoint (agent 7: 271.2K) and the pooled median with judges (agent 2: 271.6K).

## Recommended rule ("REC": live charge with a consensus cap, and a new limit)

For each line, using sources that are missing or ≤ 0 drop out:

```
Gi  = median fair_gross_total of the members of group i who say covered & related,
      used only if that group's majority says covered                       (i = 1, 2, 3)
oa, ob = old Fable judge's (a, b) for the line
X   = lowmed{ G1, G2, G3, oa }            lowmed = 2nd-lowest of 4, middle of 3, lower of 2, the value of 1
Y   = lowmed{ G1, G2, G3, sqrt(oa*ob) }
covered = more than half of all available researchers (up to 9) say covered & related

a_live = today's Ruben-2 charge (per group with covered majority: 0.93 × median fair; mean over groups;
         old judge's a when no group covers)
a = min(a_live, 0.95 · X)   if covered and X exists, else a_live
b = 0.97 · Y                if covered and Y exists, else 0
```

Why each term is there:
- **lowmed of four opinions.**
  - Overpricing loses the whole line, so the price sits below the consensus.
  - The single lowest opinion is often a misread line, so it is skipped (agent 7's idea).
  - On the charge side, the 4th voice is the old judge's charge, which it sets cautiously on purpose. Alone it can never pull the price down; together with one low group it can.
  - On the limit side, the 4th voice is the judge's implied fair value √(a·b), because a limit should sit at a fair estimate, not at a cautious charge.
- **a = min(live charge, 0.95·X), a cap rather than a new charge.**
  - Every plain k·X charge has a cliff one notch above its optimum. For example, lowmed·k: k 0.93 → 0.94 costs 16K on even games and 18K on even 36-46.
  - The live charge (0.93 × mean of group medians) is already safe on agreeing lines, so the cap acts only where the consensus says the live charge overshoots. Examples: game 29 line 1 (live 1860, market lo 1532), game 33 line 1 (1581 vs 1220), game 18 line 2 (976 vs 966).
  - That makes the multiplier flat: c anywhere from 0.93 to 0.97 is within ±2K.
- **b = 0.97·Y.** As insurer the loss is soft and near-symmetric (rejecting a fair bill costs +0.5a; accepting an inflated one costs a), so b sits just under a fair estimate. The curve is flat from 0.95 to 1.00.
- **Uncovered lines.**
  - The charge on uncovered lines is unchanged from live: live still charges them at the old judge's a, which Daniil has not approved.
  - `REC strict` removes that charge (a = 0 when not covered). Its worst case is nearly the same, but its best case and midpoint are much lower. That is a policy choice for Daniil, separate from this rule.

Tuned values: c = 0.95 (best mean worst case over c ± 0.02 on odd games) and m = 0.97 (odd optimum). Nothing else was tuned.

## Results: net worst / best / mid (K)

| rule | odd 1-45 (fit) | even 2-46 (val) | even 36-46 | new 47-50 | all 36-50 |
|---|---|---|---|---|---|
| Ruben 2 groups (**live**) | +50.6 / 176.4 / 113.5 | +47.2 / 198.0 / 122.6 | +24.7 / 62.1 / 43.4 | −0.8 / 8.8 / 4.0 | +36.8 / 93.2 / 65.0 |
| Ruben 3 groups | +47.9 / 197.6 / 122.7 | +57.0 / 197.0 / 127.0 | +26.8 / 63.9 / 45.3 | −3.5 / 14.1 / 5.3 | +35.8 / 100.4 / 68.1 |
| **MIN-2**: live charge, b = 0.97·Y | +64.4 / 190.1 / 127.3 | +49.8 / 200.5 / 125.2 | +25.1 / 62.6 / 43.8 | +0.4 / 10.1 / 5.2 | +41.9 / 98.1 / 70.0 |
| MIN-3: Ruben-3 charge, b = 0.97·Y | +57.8 / 207.1 / 132.5 | +57.6 / 198.0 / 127.8 | +27.2 / 64.4 / 45.8 | −2.5 / 15.3 / 6.4 | +40.9 / 105.3 / 73.1 |
| **REC** (cap + new limit) | **+96.8** / 189.3 / **143.0** | **+63.6** / 188.5 / 126.1 | +23.0 / 59.9 / 41.5 | +0.1 / 8.4 / 4.2 | +38.6 / 92.6 / 65.6 |
| REC strict (no uncovered-line charge) | +91.8 / 142.2 / 117.0 | +59.8 / 123.5 / 91.7 | +22.8 / 44.7 / 33.8 | +0.0 / 8.2 / 4.1 | +34.4 / 72.3 / 53.4 |
| REC-3 (cap applied to the Ruben-3 charge) | +99.0 / 192.6 / 145.8 | +62.6 / 186.4 / 124.5 | +19.1 / 57.9 / 38.5 | −3.1 / 11.1 / 4.0 | +30.5 / 92.9 / 61.7 |
| pure cautious: a = 0.92·X, b = 0.97·Y | +88.6 / 136.9 / 112.8 | +57.8 / 113.7 / 85.8 | +19.2 / 40.8 / 30.0 | +1.6 / 19.9 / 10.8 | +32.6 / 79.4 / 56.0 |
| ref: agent 7 with judges (0.90 / 0.98 · lowmed4) | +81.1 / 132.4 / 106.8 | +54.3 / 112.7 / 83.5 | +19.9 / 39.5 / 29.7 | +0.5 / 18.4 / 9.5 | +29.1 / 76.7 / 52.9 |

**Paired bootstrap over games, worst case** (5000 resamples): difference [5%, 95%] and P(> 0).

| | odd | even | even 36-46 | new 47-50 |
|---|---|---|---|---|
| MIN-2 vs live | +13.8 [+5.3, +23.5] 1.00 | +2.6 [−3.7, +10.8] 0.67 | +0.4 [−2.2, +2.7] 0.62 | +1.2 [−0.8, +3.2] 0.81 |
| MIN-3 vs Ruben 3 | +9.9 [+4.0, +16.6] 1.00 | +0.6 [−2.3, +3.5] 0.65 | +0.4 [−1.8, +2.5] 0.65 | +1.0 [−0.9, +3.1] 0.81 |
| REC vs live | +46.1 [+4.0, +96.4] 0.98 | +16.5 [−2.5, +38.6] 0.92 | −1.7 [−4.7, +1.4] 0.19 | +0.9 [−5.2, +8.1] 0.57 |
| REC vs Ruben 3 | +48.9 [+10.6, +93.7] 0.99 | +6.7 [−11.8, +25.9] 0.73 | −3.7 [−15.9, +6.7] 0.32 | +3.6 [−3.7, +11.2] 0.76 |
| REC vs MIN-2, games 1-35 / 36-50 | +49.2 [+8.2, +97.9] 0.99 | | −3.3 [−9.7, +3.7] 0.21 (36-50) | |

Midpoint, REC minus live: +29.5 (odd), +3.5 (even), −1.9 (even 36-46), +0.2 (new). So REC raises the worst case without giving up midpoint. This is unlike every "pure cautious" rule from the 10 agents, which lose 30-40K of midpoint on even games.

## Robustness (worst case, K: odd / even / even 36-46 / new)

**Cap multiplier c** (with m = 0.97). Refit bootstrap on resampled odd games: c 5/25/50/75/95% = 0.95/0.95/0.95/0.99/1.00.

| c | odd | even | even 36-46 | new |
|---|---|---|---|---|
| 0.90 | 81.9 | 58.5 | 20.7 | −0.3 |
| 0.93 | 95.6 | 61.7 | 20.5 | −0.3 |
| **0.95** | **96.8** | **63.6** | **23.0** | **+0.1** |
| 0.97 | 98.6 | 65.6 | 23.6 | −1.4 |
| 1.00 | 84.4 | 69.4 | 24.4 | −1.9 |

There is no cliff: the live charge underneath already sits at 0.93 × consensus.

**Limit multiplier m** (with c = 0.95). Refit bootstrap: m = 0.95/0.96/0.97/0.98/0.99.

| m | odd | even | even 36-46 | new |
|---|---|---|---|---|
| 0.92 | 89.9 | 60.7 | 21.0 | +1.2 |
| 0.95 | 95.8 | 62.4 | 22.1 | −1.1 |
| **0.97** | **96.8** | **63.6** | **23.0** | **+0.1** |
| 0.99 | 96.3 | 63.4 | 22.1 | −1.5 |
| 1.02 | 94.1 | 61.6 | 22.4 | −3.9 |

The limit alone, b = m·Y on top of the live charge, scores at least as well as the live limit on odd and even games for every m from 0.95 to 1.02, and within ±1K of it on even 36-46 (`robust.out`).

**Where the cap acts.** It binds on 24 lines with |effect| ≥ 0.5K (`final.out`).
- Big wins: g29 l1 +20.7K, g33 l1 +16.6K, g18 l2 +7.8K, g32 l15 +5.6K, g12 l1 +4.6K, g38 l3 +4.1K, g47 l15 +2.9K.
- Losses: g1 l1 −3.6K, g38 l1 −3.2K, g12 l2 −2.4K, g48 l2 −1.8K (no G3 in game 48).
- The cap is insurance: on games 36-50 its premium was about 0.2K per game. Earlier it paid +49K, from lines where the old groups' mean overshot the market by 20-30%. The live charge still depends only on the old groups, so that risk has not gone away.

## Which idea from which agent survived

| idea | agent(s) | fate |
|---|---|---|
| Coverage gate = majority of all researchers | all | **kept** (on b, and on where the cap applies) |
| Lower-median of 4 opinions; skip the single lowest | 7 | **kept**: the base for both X and Y |
| Judges' implied fair √(a·b) as the 4th vote for the limit | 7 | **kept**, with the old live judge instead of the 4 new ones (which don't exist live) |
| A cautious source as a vote (the judge's charge is deliberately low) | 3, 4, 8 | **kept** as the 4th vote in X (old judge's a) |
| b ≈ 0.97-1.00 × a cautious consensus | 1-10 | **kept**: 0.97·Y. It beats the live and Ruben-3 limits on odd and even games, and roughly ties them on even 36-46 and new games |
| Keep the live charge and change only the limit | 6, 7, 10 suggested it | **kept** as MIN-2, the zero-regret step |
| "Never charge above the consensus when it is lower" | 6 (G3 cap) | **kept as a cap on the live charge** (not as a new charge), which removes the cliff |
| Charge multiplier ≤ 0.95 / cliff at 0.94-0.96 | all | respected: the cap uses 0.95 on a *lower* base, and the live 0.93 stays underneath |
| min of groups, min(G3, median), min(m3, max(m12, l3)), median of 3 families, GM, pooled median | 5, 6, 9, 8, 3/4, 2 | tested as charge bases and as caps. Each was within ±8K of X on odd games, worse on new games or needing judges, so dropped |
| Disagreement shading exp(−λs) on a or b | 1, 10 | tested. Limit M·e^(−0.55s): 183.1K paid on odd vs 182.2K for Y (a tie), so dropped for simplicity |
| Group 3 alone is strongest on 36-46 | 1, 3, 8, 9 | true on 36-46 (charge 125.9K vs 122.1K live), **false on new 47-50** (73.8K vs 76.2K live). Not adopted |
| Charge uncovered lines at the old judge's a | live rule | left exactly as live does it. The strict variant is reported. Policy is Daniil's call |

## Honest caveats

- **The odd-game gain is lumpy.** +37K of REC's +46K odd lead comes from two lines (g29 l1, g33 l1).
- **Even games are not a clean hold-out.** The cap form was built after reading agents' reports that contain even numbers. Only games 47-50 are truly new, and there everything is within ±4K: four games, too few to tell.
- **REC is slightly behind live on the recent block.** It trails live on even 36-46 (−1.7K) and the limit-only MIN-2 on 36-50 (−3.3K). If the future looks exactly like games 36-50, MIN-2 is the better rule.
- **Ruben-3-based variants are not better.** MIN-3 and REC-3 are better on even games but worse on 47-50. G3 is live only from game 49, so 2-group-based rules are the safer pick now.

## Recommendation

1. **Switch the limit now: b = 0.97 · lowmed{G1, G2, G3, √(oa·ob)}, and 0 on lines most researchers call uncovered** (MIN-2).
   - It is better than live on odd (+13.8K, P = 1.00), even (+2.6K), even 36-46 (+0.4K) and new games (+1.2K).
   - It raises the best case too, needs no new sources, and is flat in m.
   - There is no split where it loses.
2. **Also switch the charge cap now: a = min(live charge, 0.95 · lowmed{G1, G2, G3, oa}) on covered lines.** Together this is REC.
   - It adds +32K worst case on odd games and +14K on even games over MIN-2, with no loss of midpoint overall.
   - It costs about 0.2K per game in the recent block.
   - c is flat from 0.93 to 0.97.
   - It is worst-case insurance against the rare 15-20K overshoot lines, and the worst case is the primary score.
   - If the team prefers to act only on effects confirmed in recent games, do step 1 alone and re-check the cap after about 10 new games.
3. Do **not** adopt any pure cautious charge (k·X with k ≥ 0.93), any group-3-only charge, or any rule that needs the 4 new judges.

Scripts in this folder:

| script | role |
|---|---|
| `core.py` | data loader and replay |
| `bases.py` | all bases from the agents |
| `search.py` | side-separated grid (`search.out`) |
| `hybrid.py` | caps (`hybrid.out`) |
| `combos.py` | charge × limit grid (`combos.out`) |
| `robust.py` | curves (`robust.out`) |
| `final.py` | finalists, bootstrap, refit, cap lines (`final.out`) |
| `cap_vs_min.py` | REC vs MIN-2 (`cap_vs_min.out`) |
