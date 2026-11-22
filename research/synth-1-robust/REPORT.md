# S1 — Robust version of the live formula (synthesis of all research reports)

Scope: make `formula.py` safer without breaking what works. Read-only; nothing submitted, no model calls.
Data: 250 lines, games 1-34. Games 1-29 come from `tx_cache.pkl` with the 6 pooled sources. Games 30-34 use
`opponents/tx_30_34.pkl` (already fetched read-only by the opponents agent) and the live v2 answers in
`backtest/v2/state.json`: 3 sources in games 30-33, 6 sources in game 34. The evaluator is the closed-form copy of
`fable_vs_opus.replay` (`ev.py`). On 366 probes over games 1-34 it has 0 mismatches. It reproduces the live formula's
in-sample result exactly (+83,871 / +298,508).

Metrics: **lo** is the replay worst case, the criterion for every ranking and fit. hi is the best case, which counts
unknown ("?") acceptances as paid, so it is inflated by up to about 130K.
- **WF**: fit on games < g, test on g = 6-29.
- **HO**: fit on 1-24, test on 25-29.
- **boot p5**: 5th percentile of 2000 game-bootstraps of the WF per-game results.
- **drift**: the fit uses the true estimates, the test uses estimates × 0.98 and × 1.02. The table shows the worse of the two.
- **gross stress**: every source writes its gross price even on lines it calls "not covered". v2 opus-2 and v1-opus-1
  already do this live. The fit uses normal data; the test uses the stressed data.
- **30-34**: walk-forward (fit on all games < g), fully out of sample.

Scripts: `prep.py`, `lib.py`, `run.py` → `results.txt`, `run2.py` → `results2.txt`, `families*.json`, `fixed.json`,
`diag*.py`.

## Change → effect (honest refits; Δ against the live-type refit R0)

| change (family, refit honestly) | WF 6-29 lo..hi | HO 25-29 lo..hi | boot p5 lo | drift ±2% worst (WF) | gross stress WF lo | 30-34 WF lo | 30-34 drift ±2% worst | 30-34 gross |
|---|---|---|---|---|---|---|---|---|
| **R0 live type** (3 cv tiers, b = m·raw min) | **+48.0K**..+242.6K | +24.7K..+80.1K | +14.7K | +43.0K | **−54.7K** | +20.8K | +4.9K | **−88.1K** |
| A2 uncovered guard (≥5/6 "no" → a=0, b=0) | +42.6K (−5.4) | +24.7K (0) | +8.7K | +37.8K | **+42.8K** | +20.8K | +4.9K | **+20.8K** |
| A3 guard, but keep a free charge 0.9×nz-median (b=0) | +48.1K (+0.1) | +24.7K | +15.6K | +43.1K | +48.2K | +20.9K | +5.1K | +20.9K |
| A guard + split lines priced from covered voters only | +41.7K (−6.3) | +20.8K (−3.9) | +7.2K | +37.1K | – | +20.8K | +4.9K | – |
| D' b coverage-gated (b=0 if any source says "no") | +47.5K (−0.5) | +24.7K | +14.2K | +42.5K | **+47.7K** | +20.8K | +4.9K | **+20.9K** |
| D b on min of covered voters' fair | +46.1K (−1.9) | +24.4K | +13.0K | +41.4K | – | +20.8K | +4.9K | – |
| B step back: k_agree = fitted − 0.02 | +45.0K (−3.0) | +23.9K (−0.8) | +12.3K | +42.2K | −57.7K | +18.9K | **+12.4K** | −90.0K |
| B' all k = fitted − 0.02 / B'' − 0.04 | +43.1K / +42.7K | +23.4K / +22.3K | +10.3K / +10.2K | +42.6K / +41.3K | – | +18.5K / +17.1K | +15.8K / +13.6K | – |
| C disagree tier removed (no guard) | +42.6K (−5.4) | +24.7K..+66.6K | +8.6K | +38.2K | – | +20.8K | +4.9K | – |
| C' disagree k capped at 1.10 | +48.3K (+0.3) | +24.7K..+77.5K | +15.1K | +43.3K | −55.0K | +20.8K | +4.9K | −88.1K |
| M m fixed 1.00 (instead of refit) | **+48.9K (+0.9)** | +24.7K | **+17.3K** | **+44.0K** | −52.6K | **+21.4K** | +8.7K | −85.8K |
| M m fixed 1.02 | +47.7K (−0.3) | +24.7K | +15.0K | +44.1K | – | +19.8K | +8.4K | – |
| E one global k, jitter-smoothed fit (charge-side agent) | +44.2K (−3.8) | +24.3K | +11.5K | +41.0K | – | +13.5K | +7.5K | – |
| E' 3 tiers with jitter-smoothed fit | +24.3K (−23.7) | +3.5K | −12.9K | +21.8K | – | +13.3K | +9.9K | – |
| **H1 = A2 + D' + C' + B + M1.00 (final)** | +41.1K (−6.9) | +23.9K (−0.8) | +9.4K | +38.5K | **+41.4K** | +19.6K (−1.2) | **+16.2K** | **+19.6K** |
| H5 = H1 without the step back | +44.1K | +24.7K | +11.6K | +39.3K | +44.3K | +21.4K | +8.7K | +21.4K |
| H3 = H1 with 2 tiers (disagree → some) | +37.4K | +23.9K | +4.8K | +35.2K | +37.8K | +19.6K | +16.2K | +19.6K |
| H4 / H7 = H1 with m refit / m 1.02 | +39.7K / +39.9K | +23.9K | +6.4K / +6.7K | +37.0K / +38.7K | ~+40K | +18.9K / +17.9K | +12.4K / +15.9K | – |
| H8 = H1 with all k − 0.02 | +39.3K | +23.4K | +7.8K | +38.5K | +39.8K | +19.2K | +19.1K | +19.2K |
| H6 = H1 + free charge on uncovered lines (A3) | +46.6K (−1.4) | +23.9K | +15.7K | +43.9K | +46.8K | +19.7K | +16.3K | +19.7K |

## Fixed constants (1-29 is in-sample for the live constants; 30-34 is out of sample)

| candidate | 1-29 lo (IS) | lo at estimate drift −4 / −2 / +2 / +4 % | gross stress 1-29 | 30-34 lo..hi | 30-34 drift −2 / +2 % | 30-34 gross |
|---|---|---|---|---|---|---|
| live `formula.py` .92/.84/1.16, b 1.04·min | **+83.9K** | +74.0 / +76.4 / **+60.2 / +46.1K** | **−24.1K** | +19.5K..+35.2K | +17.8 / **+5.4K** | **−91.3K** |
| robustness agent .90/.84/1.12, b 1.02 | +78.5K | +70.3 / +75.3 / +77.6 / +61.4K | −27.5K | +17.9K..+33.9K | +18.0 / +15.9K | −91.0K |
| **FINAL** guard + gated b, .90/.84/1.10, m 1.00 | +75.3K | +66.4 / +71.0 / **+72.1 / +58.0K** | **+75.6K** | **+19.6K..+35.4K** | +19.5 / **+16.2K** | **+19.6K** |
| FINAL with m 1.02 / 1.04 | +74.3K / +75.5K | ≈ same | ≈ same | +17.9K / +17.6K | +18.0/+15.9 · +16.6/+12.8 | – |
| FINAL with k_agree .92 / .88 | +79.2K / +73.7K | +2 %: +55.5K / +68.1K | – | +21.4K / +18.4K | +2 %: +8.7K / +14.3K | – |
| FINAL + free charge on uncovered | +80.8K | +71.6 / +76.3 / +77.5 / +63.6K | +81.1K | +19.7K..+115.4K | +19.7 / +16.3K | +19.7K |
| guard + gated, one global .87, m 1.00 | +66.6K | flat 66-73K | +67.3K | +17.2K | +20.2 / +14.7K | +17.2K |

FDN's real net: 6-29 +18.7K, 25-29 +4.6K, 30-34 **+42.8K**. Games 30-33 used the judge, game 34 the formula.

## What worked
1. **Uncovered guard plus coverage-gated b. The largest risk reduction by far.** Today b = 0 on uncovered lines only
   because some sources write fair = 0. If every source writes a gross price there, the live type loses about 100K
   walk-forward (−54.7K instead of +48K) and about 110K on games 30-34 (−88K/−91K instead of +20K). Either fix makes this
   stress case harmless: +41-48K WF, +20K on 30-34. The gated b alone costs 0.5K WF and 0 HO.
2. **Stepping k_agree back to 0.90 is insurance.** It costs −3.0K WF, −0.8K HO and −1.2K on 30-34. Under a +2 %
   estimate drift it recovers +7.5K on 30-34 (+3.0K even when g34 l1 is dropped; that line's proven-fair bound is FDN's
   own formula charge) and +16.6K in sample (+15K at +4 %; FINAL with k_agree .90 vs .92). At −2 % it costs about 1.5K. Agrees with the robustness
   agent's density argument.
3. **m fixed at 1.00** is weakly better than 1.04 or a refit on every honest column: WF +0.9K, boot p5 +2.6K, 30-34
   +0.6K..+2K, 30-34 drift +3.8K.
4. **Capping the disagree k at 1.10** costs nothing (WF +0.3K, p5 +0.4K). Once the guard is on, only 6 lines in 1-29
   fall in that tier (5 split lines and g24 l1). Any k_dis from 0.84 to 1.30 changes the result by at most 1.4K.

## What did not work
- **Removing the disagree tier.** −5.4K WF without the guard; −3.7K WF and −4.6K boot p5 with it. Cap it instead.
- **Pricing split lines from the covered voters only (as "covered").** −6.3K WF, −3.9K HO. One line (g21 l13) pulls the
  1-24 fit of k_agree to 0.82. Leave split lines exactly as live (median over all six fairs).
- **b from the covered voters' minimum.** −1.9K WF. The coverage-gated minimum (b = 0 on split lines) is better.
- **Jitter-smoothed / single global k (0.86-0.88).** Very drift-robust, but −3.8K WF, −7K on 30-34. With tiers,
  smoothing is unstable (−24K WF).
- **Bigger step-backs** (all k − 0.02 / − 0.04). They cost 1-5K more with no further gain under drift.
- **a = 0 on uncovered lines (honest guard) costs money historically.** −5.4K WF worst case (boot p5 −6K), all of it
  from games 10-22. It costs **0** on the 25-29 hold-out and on 30-34. It is a presentation/honesty choice, not a risk
  reduction: an issuer charge can never lose money.
- Not included: a = max(formula, Fable judge). It raises charges toward the cliff, adds about 2-7K, and was selected
  post hoc (ensemble report).

## Final recommended formula
```python
no  = share of sources with covered == False or related == False
if no >= 5/6:                       # uncovered guard (with 3 sources: all 3)
    a, b = 0, 0
else:                               # covered and split lines: fairs = all sources' fair_gross_total, as live
    cv = pstdev(fairs) / mean(fairs)
    k  = 0.90 if cv < 0.15 else (0.84 if cv < 0.40 else 1.10)
    a  = k * median(fairs)
    b  = 1.00 * min(fairs) if no == 0 else 0      # coverage-gated: never accept on a line any source calls uncovered
```
Against live `formula.py`:
- **Normal conditions:** −6.9K walk-forward over 24 games, of which −5.4K is the honest a = 0. Also −0.8K hold-out and
  −1.2K on 30-34.
- **Stress:** +96K under gross-fair stress (WF) and +108K on 30-34. Under +2 % drift: +11K on 30-34, +12K at +2 % and
  +12K at +4 % in sample.
- If the team values money over the honesty story, keep a free charge of 0.9 × median non-zero fair on guarded lines.
  b stays 0. That variant (H6) costs only −1.4K WF against live and keeps every stress benefit.

Caveats: 24 + 5 test games. Games 30-33 have only 3 sources. Game 34's bounds are partly set by FDN's own formula
charges. The largest single loss on 30-34 is a b-side tail: g33 l1, b = 1500-1560 ≥ proven inflated 1472, −8.9K.
No variant here fixes it.
