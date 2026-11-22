# Synthesis S2: market-anchored improvements. Result: none beat formula.py

**Final recommendation: keep `formula.py` and make the uncovered guard explicit:**
```
if >= 5/6 of sources say not covered/related:  a = 0, b = 0
else:  a = k x median fair (k = 0.92 if cv < 0.15, 0.84 if cv < 0.40, else 1.16);   b = 1.04 x lowest fair
```
None of the market-anchored variants I built beat this worst case walk-forward, on the hold-out, or on the fresh games 30-34.
The one positive add-on is not market-based: `a = max(a, Fable-judge a)`. It is listed at the end as optional.

Scripts are in this folder:
- `build.py`: builds `lines.pkl`, 250 lines from games 1-34. Games 30-34 come from the transactions in
  `research/opponents/tx_30_34.pkl`. Games 30-33 have only 3 v2 sources; game 34 has all 6.
- `core.py`: closed-form replay. It reproduces formula.py on games 6-29 exactly: +54.8K..+255.1K.
- `match.py`: description matcher.
- `wf.py`, `run2.py`, `br.py`, `run3.py`, `judge3034.py`: the tests. Their outputs are in `*.out`.

Every number is net EUR, worst case..best case (replay pessimistic..optimistic). Selection always uses the worst case.

## Baselines
| rule | WF 6-29 | hold-out 25-29 | games 30-34 (out of sample) |
|---|---|---|---|
| formula.py, no guard (constants in-sample on 6-29) | +54.8..+255.1K | +25.4..+80.8K | +19.5..+35.2K |
| **formula.py + guard** | **+50.2..+110.2K** | **+25.4..+32.0K** | **+19.5..+35.2K** |
| same family, k/m refit walk-forward (honest) | +39.2..+113.0K | +24.7..+31.2K | +20.8..+36.5K |

The guard costs 4.6K worst case on games 6-29. All of that is the "free option" income from games 10-22.
It costs 0 on 25-34, because the market has rejected those charges since game 23.

## What I tested (Δ worst case vs formula.py + guard)
1. **Anchor a line to the market bounds of earlier lines with a matching description.**
   - Cases do repeat. For example, g16, g25 and g32 are the same plumbing invoice, and g20 and g34 the same assessment fee.
   - I raised a to θ x the matched proven-fair lo (θ 0.8-1.0) and/or capped it at φ x the matched proven-inflated hi.
     I did this in absolute EUR or as a ratio to our median, with Jaccard thresholds 0.5, 0.75 and 1.0.
     That is a 1,080-point grid, which also includes the b variants of item 4.
   - Best in-sample (games 2-29): +3.1K. Walk-forward selection on 6-29: **−1.5K**. Hold-out: **+0.0K**. Games 30-34: **−0.9K**.
   - Ratio anchoring is worse: down to −12.9K on games 30-34.
   - Why it fails:
     - Only about 31 of about 130 covered lines have a usable match.
     - Generic items vary too much between cases. "Vehicle costs" has t anywhere from 13 to 83 EUR. Thermal camera hi
       went 57 → 28 → 20 in the three plumbing repeats.
     - On exact repeats, our median already lands near t, so the anchor adds little.
2. **Structural per-line best response.**
   - I fitted log(t/med) ~ N(μ, s0² + (c·cv)²) by interval-censored maximum likelihood on earlier games' bounds.
   - I fitted the acceptance curve A(x) = P(other team's b ≥ x·med) from earlier reviewer brackets.
     Fitted values: 0.58 at 0.8, 0.48 at 0.9, 0.40 at 1.0, 0.29 at 1.2.
   - Then a* = argmax of expected income.
   - Results: WF **−7.7..+138.5K**, hold-out −17.5..+48.4K, games 30-34 −40.2..+43.2K.
   - It charges 0.99-1.55 x med, because rejected fair bills pay 1.5x and that makes high charges look good in
     expectation. But charges above the market's highest proven-fair charge cannot be proven fair, so the worst case
     collapses. The expected-value best response is not the worst-case best response.
3. **Per-category k, shrunk to the global fit** (category lines up-weighted by λ = 0, 1, 3, 10; refit walk-forward).
   - WF +38.5..+41.3K (vs +39.2K for the global refit). Hold-out +25.0..25.4K. Games 30-34 +17.9..19.5K.
   - No gain at any λ.
4. **b from other teams' fair and inflated charges on similar lines.**
   - Per-category m (shrunk): WF +49.0..+49.5K, hold-out +24.5..25.2K, games 30-34 +16.7..+20.8K. This is noise around
     the fixed 1.04 x min.
   - Clipping b to the matched lines' lo/hi: −0.1..+0.2K (6-29) and −0.4K (30-34).
   - This agrees with the acceptance-side and best-response reports: P(fair | charge) crosses 2/3 at about
     1.0 x min fair, so min fair already is the market-aware threshold.

## Out-of-sample evidence from games 30-34 on the live constants (the useful new result)
| shift on all k | −0.08 | −0.04 | −0.02 | 0 | +0.02 | +0.04 | +0.08 |
|---|---|---|---|---|---|---|---|
| games 30-34, worst case | +13.4K | +15.8K | +17.3K | **+19.5K** | +8.6K | +5.9K | −33.9K |
| hold-out 25-29, worst case | +21.4K | +23.0K | +24.1K | **+25.4K** | +26.8K | +23.3K | +25.5K |

- **The cliff is confirmed on fresh games.** +0.02 costs 10.9K in 5 games; −0.02 costs 2.2K.
  The cliff lives in the **worst case**; the best case barely moves (+35.2K → +33.4K at +0.02).
  So do not raise k to "charge closer to fair like 404". If anything, shade down (robustness report: 0.90).
- k_disagree is irrelevant on 25-34; nothing moved between 0.84 and 1.16.
- m: 0.96 / 1.00 / 1.04 / 1.08 gives +22.0 / +21.4 / +19.5 / +14.3K on games 30-34. That is flat to slightly favouring
  1.00, which is consistent with the acceptance-side optional m = 0.96-1.00.

## Why the "undercharge leak" is not recoverable with pre-game market data
- The fdn-gap leak (charging 0.5-0.97 x lo) is measured against lo, which is only known **after** the game.
- Before the game, the best predictor of t is still our 6-source median. The market's per-item history is too case-specific
  (the same item has a different t in the next case), and category-level ratios are noise.
- Raising a toward t only pays if we know t better. Every attempt to do that from history moves some charges above lo, and
  the worst case punishes that hard.
- The remaining lever is better per-line estimates (more independent sources, or the Fable judge on disagreeing lines),
  not market anchoring.

## Optional add-on (not market-based): a = max(formula a, Fable-judge a), b unchanged
- Results: 6-29 **+1.5K** (+51.7 vs +50.2K worst case), hold-out **+1.5K**, games 30-34 **+2.2K**. 10 games up, 2 down.
- It is positive in all three windows, including fresh games the ensemble agent did not have.
- But it is lumpy: 8 decisive lines, and one of them loses 7.0K (g19 l2).
- Use it only if the judge runs anyway; it is not needed.
