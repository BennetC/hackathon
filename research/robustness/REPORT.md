# Overfitting audit: live formula vs alternatives (research agent 8)

Data: `tx_cache.pkl` games 1-29 (201 lines; the cache has no games 30+), 6 pooled sources (v1 3x Opus + v2-train Fable + 2x Opus).
Evaluator: a closed-form copy of `fable_vs_opus.replay`, checked against it on 240 line×value probes with 0 mismatches. Values are net EUR: lo = worst case, hi = best case, mid = (lo+hi)/2.
Scripts: `prep.py`, `ev.py`, `audit.py` (all tables → `audit_out.md`), `extra.py` (→ `extra_out.txt`). Bootstrap uses 200 resamples of games, seed 7.
"WF" = walk-forward, fit on games < g and test on g, for games 6-29. "Family" = a formula's structure, with its multipliers re-fitted honestly.

## Ranking (honest numbers first)

| candidate | family (re-fit criterion) | WF 6-29 lo..hi | WF-bootstrap mid: median [p5] | WF-bootstrap lo p5 | LOGO 1-29 mid | hold-out fit 1-24 → test 25-29 | in-sample fixed values, all 1-29 lo / mid *(secondary)* | cliff: worst lo within ±0.04 of one k |
|---|---|---|---|---|---|---|---|---|
| **LIVE** 0.92/0.84/1.16, b 1.04·min | tier(median) / min (worst-case fit) | +47.9K..+243.4K | **+138.7K [+102.4K]** | **+18.1K** | +177.3K | +24.4K..+80.1K | +83.9K / +191.2K | **-34.6K** (k agree), -38.6K (all k) |
| **SAFER** 0.89/0.82/1.10, b 1.00·min | same family (smoothed worst-case fit) | +22.3K..+241.0K | +126.4K [+91.4K] | -10.7K | +170.6K | +3.9K..+86.0K | +75.3K / +178.7K | -4.0K (all k), -1.9K (k agree) |
| *(reference)* global k·median, b m·min | 2 parameters (worst-case fit) | +44.0K..+223.3K | +129.8K [+97.2K] | +13.5K | +176.9K | +20.9K..+63.0K | n/a | n/a |
| MEDIAN 0.92/0.94 | k·median / m·median | -27.8K..+204.6K | +85.7K [+62.8K] | -64.7K | +131.5K | -3.2K..+52.6K | -24.9K / +120.5K | -53.6K |
| MEAN 0.91/0.93 | k·mean / m·mean | -43.2K..+222.1K | +87.0K [+61.7K] | -82.5K | +99.9K | -23.5K..+72.2K | -23.9K / +125.4K | -49.0K |
| LOWEST 0.97/1.00 | k·min / m·min | +44.3K..+95.6K | +70.0K [+44.3K] | +12.2K | +100.6K | +23.9K..+30.4K | +73.5K / +102.6K | -32.6K |
| OLD a 0.8·F, b 1.0·F | k·median / m·median (fixed values) | fixed values, games 6-29: mid +53.3K | +51.6K [+18.6K] | **-120.1K** | n/a | -12.3K..+57.5K | -47.1K / +80.5K | -10.3K |

Nested WF: at each game, choose the family and fit criterion with an inner walk-forward on earlier games. Result: +28.5K..+265.8K, mid +147.2K, bootstrap median +139.0K [p5 +100.9K]. It picks the live family in all 24 games (worst-case fit 13 times, midpoint fit 8 times). Other families, fit by every criterion, are in `audit_out.md`.

Reading:
1. **The live structure is not overfit as a structure.** Every honest check puts it first, by +52K to +87K (WF-bootstrap median) over the median, mean, lowest and old families. Its p5 (+102K) is above every rival's median. In-sample optimism is small: fixed values on games 6-29 give mid +155.0K vs WF +145.6K (-6%), and in-sample +192K vs LOGO +177K (-8%). On the 25-29 hold-out, values fitted on 1-24 give +24.4K..+80.1K, the same as the in-sample live (+25.4K..+80.8K).
2. **What carries it:** the acceptance limit on the **lowest** fair estimate. Every family with b on the median or mean has a worst-case p5 between -65K and -120K. Fitted on the median, m runs to the grid floor (0.50): b = 0.94·median accepts inflated bills. Bootstrap of m on min: 1.01 [0.95..1.07]. It is flat: ±0.10 changes worst-case net by at most 2.8K.
3. **The tier split adds little out of sample.** A single k on the median (with b on min) reaches LOGO +176.9K vs +177.3K, and is 9K lower in WF. Nearly all the tier value is k_disagree (see 5).

## The cliff (the real overfitting)
- k_agree = 0.92 sits right under a market bound. Raising the agree multiplier to 0.94 or 0.96 loses the whole line on **5 lines**: g2-1, g4-2, g5-1, g11-5 and g25-3. Their proven-fair bound is at 0.93, 0.93, 0.95, 0.96 and 0.95 × median (-2.8K to -16.7K worst case each). The worst-case sum falls by 16.6K at +0.02 and by 34.6K at +0.04.
- **Walk-forward picks 0.92 from game 6 on and never moves.** That value comes from g4-2 (0.929) and g5-1 (0.933). For agree lines with a proven bound (n = 51), **no** bound/median ratio falls in (0.86, 0.92]; 4 fall in (0.92, 0.96]. So 0.92 is the upper edge of an empty gap in a sample of 51, which is selection bias.
- Smoothed density near 0.92 is about 1.2 lines per 0.01 per 29 games, at about 7.7K worst case per line. So the expected cost of a future line landing in (0.90, 0.92] (about 2.5 lines per 29 games, about -19K) is larger than the in-sample gain of 0.92 over 0.90 (+3.9K worst case, +4.6K mid).
- **Drift risk:** if our models' estimates move up 2% (new prompt, new source mix, Fable-only, more accurate models), the live formula loses 22K worst case in sample. The recommendation below loses 1.6K.
- In WF on games 6-29, shifting all fitted k by +0.02 still helps (+51.2K lo). No later line happened to fall in the gap, which is why WF does not punish 0.92. One sample of 24 games is weak evidence against the density argument.

## Recommended final values (same structure as `formula.py`)
| parameter | live | **recommended** | interval | evidence |
|---|---|---|---|---|
| k agree (cv < 0.15) | 0.92 | **0.90** | 0.88 – 0.92 | smoothed worst-case fit 0.90; bootstrap 0.92 [0.82..0.95]; cliff at ≥ 0.93 |
| k some (cv < 0.40) | 0.84 | **0.84** | 0.80 – 0.90 | worst-case fit 0.84; smoothed fit 0.81; bootstrap 0.92 [0.84..1.08]; ±0.06 changes worst case by ≤ 5.7K |
| k disagree | 1.16 | **1.12** | 1.00 – 1.25 | no effect on worst case (flat within 0.6K for ±0.10), so it is a midpoint-only bet; bootstrap [0.89..1.49]; midpoint fits run to the grid edge (1.50), which is an artifact of the optimistic "?" payoffs |
| m (b = m × lowest fair) | 1.04 | **1.02** | 0.97 – 1.07 | bootstrap 1.01 [0.95..1.07]; flat |

In sample, the recommendation (0.90/0.84/1.12, b 1.02) gives +78.5K / +183.8K (lo / mid). That is -5.4K / -7.4K vs live, about 3-4% of the midpoint. It costs the bootstrap median 6.8K and p5 lo 3.7K, against the live's in-sample numbers.

What it buys, worst-case net for all k shifted together:

| shift | -0.04 | -0.02 | +0.02 | +0.04 | +0.06 |
|---|---|---|---|---|---|
| recommendation | +69.6K | +73.9K | +76.9K | +62.3K | +44.2K |
| live | +73.3K | +77.1K | +61.6K | +45.2K | +46.2K |

The safer formula (0.89/0.82/1.10, b 1.00) is equally reasonable: about 3K more insurance, 5K less midpoint.

## Confidence
- **High:** the live structure (tier k on the median, b on the **lowest** fair) beats median, mean, lowest and the old rule on every honest metric and on downside. Dropping b-on-min is the single worst change.
- **High:** m ≈ 1.00-1.04 and k_disagree are robust or irrelevant to the worst case. Do not tune them further.
- **Medium:** lowering k_agree to 0.90 is better in expectation. The case rests on a density argument from 51 bounded lines and on drift risk; the walk-forward on 6-29 is neutral to slightly against it.
- **Low:** the tier split itself. LOGO is equal for one global k on the median. Keep it, since it costs nothing in worst case.
- Caveats: no games 30+ in the cache. The old rule here uses the pooled-6 median on every line, not the original v1 3-Opus median. "mid" includes optimistic outcomes for unknown ("?") bounds, so rank on worst-case (lo) fits.
