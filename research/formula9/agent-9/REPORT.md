# Formula agent 9: "lower of two independent groups, floored at group 3's own 10th percentile"

Read-only research. No submissions, no model calls, no state.json writes. Scripts: `lib.py` (loader plus exact per-line
replay; matches `fable_vs_opus.replay` to the euro on 12 random games, see `check.py`), `final.py` (fit, validation,
robustness, bootstrap, variants; output in `final_out.txt`), `explore*.py`, `variants2.py`, `decomp.py`, `kcheck.py`.

## The rule (per invoice line)

Notation:
- m3 = median `fair_gross_total` of the group 3 answers that say covered and related.
- m12 = median of the same over groups 1 and 2 pooled (the old prompt family, up to 6 sources).
- l3 = median `low` (10th percentile) over the group 3 answers that say covered.

```
covered  =  more than half of all available researchers (up to 9) say covered AND related
X        =  min( m3 , max( m12 , l3 ) )          (if one family is missing, X = the other one's median)
a        =  0.92 · X        if covered, else 0
b        =  0.98 · X        if covered, else 0
```

Judges are not used. There are 2 tuned numbers, K = 0.92 and M = 0.98. Both were fit on odd games only.

Why each term is there:
- **covered = majority of all 9.** Daniil has not approved charging lines that most sources call uncovered. Rejecting them (b = 0) is the matching insurer stance, because t is most likely 0 there.
- **min(m3, m12).** Group 3 and the old groups are two independent estimates of t. Overpricing loses the whole line, while underpricing costs only the gap. So when the two disagree, follow the lower one.
- **max(m12, l3).** Group 3 also reports its own 10th percentile. If the old groups sit below even that, they are most likely pricing a different scope, not being cautious. So the old groups may pull us down only as far as group 3's own lower bound.
- **a = 0.92·X.** Charge just under the cautious estimate. 0.92 is the cliff edge for a charge to be proven fair by the market. It was the best K in every block separately: 1-12 (0.94), 13-35 (0.92) and 36-47 (0.93).
- **b = 0.98·X.** Accept up to about our central cautious estimate. A fair bill wrongly rejected costs 1.5a, and an inflated bill accepted costs its whole amount. The curve is flat between 0.96 and 1.03, so the exact value barely matters.
- **The same base X for a and b.** We charge 8% under our estimate of t and accept bills up to it, so a < b on every line. The rule never prices a line one way as handyman and another way as insurer.

## Results (replayed net payoff; worst..best, midpoint in parentheses)

| rule | odd games (fit) | even games (validation) | even 36-46 | all 36-47 |
|---|---|---|---|---|
| **agent 9 rule (K 0.92, M 0.98)** | **+98.5K..+149.9K (+124.2K)** | **+60.5K..+117.2K (+88.8K)** | +22.8K..+45.2K (+34.0K) | +36.3K..+67.9K |
| Ruben avg 2 groups (live now) | +48.7K..+176.8K (+112.7K) | +47.2K..+198.0K (+122.6K) | +24.7K..+62.1K (+43.4K) | +35.6K..+84.8K |
| Ruben avg 3 groups | +46.8K..+201.0K (+123.9K) | +57.0K..+197.0K (+127.0K) | +26.8K..+63.9K (+45.3K) | +38.2K..+89.8K |
| group 3 alone (0.93/0.91) | +55.4K..+193.3K (+124.3K) | +51.4K..+181.9K (+116.7K) | +32.0K..+71.2K (+51.6K) | +44.0K..+95.7K |

Both baselines reproduce the brief's figures exactly on 36-47.

- **Worst case (primary).** The rule doubles the odd-game worst case of both baselines (+98.5K vs +48.7K and +46.8K). On even games it beats both: +60.5K vs +47.2K for 2 groups and +57.0K for 3 groups.
- **Bootstrap over even games (2000 resamples).** Against Ruben 2 groups the gain has median +12.5K, 90% interval −5.8K..+34.9K, and is positive in 86% of resamples. Against Ruben 3 groups the median is +3.2K (−11.2K..+18.7K), positive in 65%.
- **Weak spot: the recent even block 36-46.** The worst case there is +22.8K, which is below Ruben 2 groups (+24.7K), Ruben 3 groups (+26.8K) and group 3 alone (+32.0K). From game 36 on, group 3 alone is the better charge base. The old groups then pull X down on lines group 3 prices right: in 36-47, m3 earns about 11K more as issuer than X. In 13-35 it is the other way round, and X earns about 26K more than m3.
- **Best case and midpoint.** Both are much lower than the baselines, on even games +88.8K vs +122.6K midpoint. The rule gives up the "maybe fair" upside to secure lines that are proven fair. That is the price of optimising the worst case.
- **Per even game (worst case).** The rule is at or above Ruben 2 groups in 11 of 23 even games and 13 of 24 odd games. Its edge comes from a few large wins: games 18, 32 and 34.

## Robustness (worst case; K and M moved one at a time)

| setting | odd | even | even 36-46 |
|---|---|---|---|
| K 0.92, M 0.98 (fit) | +98.5K | +60.5K | +22.8K |
| K 0.87 / 0.90 / 0.91 | +76.8K / +87.5K / +91.4K | +49.0K / +58.9K / +58.0K | +18.5K / +24.0K / +21.5K |
| K 0.93 / 0.94 / 0.97 | +78.9K / +82.1K / −19.6K | +52.5K / +37.2K / +4.6K | +23.8K / +6.6K / −25.2K |
| M 0.93 / 0.96 / 1.00 / 1.03 | +90.5K / +97.4K / +97.9K / +93.9K | +57.7K / +59.7K / +60.9K / +62.0K | +21.5K / +22.1K / +23.5K / +24.0K |

- **K sits on a cliff.** Raising it by 0.02 costs 16K (odd) and 23K (even); raising it by 0.05 turns the result negative. Lowering it by 0.02 costs only 1.6K to 11K.
- **M is flat.**
- **Bootstrap refit (500 resamples of the odd games).** K has quantiles 0.84 / 0.92 / 0.92 / 0.94 / 0.95 (q05 / q25 / q50 / q75 / q95), and M has 0.96 / 0.98 / 0.98 / 0.99 / 1.00. The even-game worst case after refitting has median +60.5K, but its q05 is +35.1K, in resamples where K landed on 0.94-0.95.

## Variants checked (each fit on odd games only)

| variant | odd worst | even worst | e36-46 worst | why not chosen |
|---|---|---|---|---|
| plain min(m3, m12), no l3 floor | +89.6K | +59.0K | +21.3K | the floor is free, with no extra parameter, and better everywhere |
| median group 3 only | +61.6K | +32.9K | +16.3K | early games are weak, and the fit lands on the cliff |
| median of groups 1+2 only | +66.4K | +47.8K | +18.4K | |
| median of all 9 | +62.1K | +46.5K | +14.0K | |
| min(m1, m2, m3) | +86.0K | +38.2K | +1.4K | too low on recent games |
| old-judge or new-judge charge as a third cap | +71K..+75K | +21K..+24K | −12K..−2K | the judges' a is already shaded down; capping by it double-discounts |
| median(m3, m12, old judge a/0.92) | +98.8K | +68.1K | +23.9K | same odd fit, but needs the old judge (missing on some lines) and an ad-hoc /0.92 |
| use m3 when group 3 sessions agree within 10% | +87.4K | +53.0K | +27.9K | worse odd fit; helps only the recent block |
| gate on group 3 majority | +100.6K | +60.5K | +22.8K | charges some lines most of the 9 call uncovered (not approved) |
| EXTRA, not approved: charge if any source says covered | +102.6K | +59.1K | +22.4K | extra column only |

## Recommendation

- **Adopt the rule if the worst-case total is the goal.** It roughly doubles the odd-game worst case and beats both baselines on even-game validation (+60.5K vs +47.2K and +57.0K). It uses only researcher answers, has 2 parameters, and every term has a one-line reason.
- **Use K = 0.90 live, not 0.92.** The fitted 0.92 sits one notch below a cliff, and the bootstrap K reaches 0.95. K 0.90 gives up about 11K on odd games and 1.6K on even games, but is +1.2K better on even 36-46. It buys a 0.04-0.07 safety margin against a drift in source calibration.
- **Caveat: the most recent block.** On even 36-46 the rule is below all baselines in worst case, and well below them in best case and midpoint. Group 3 has become the best single source, and the old groups now mostly cost money through the min. If later games keep this pattern, the next step is to drop m12 from the min, or to keep it only where group 3 sessions disagree. That should be decided on new games, not by re-tuning on these.
