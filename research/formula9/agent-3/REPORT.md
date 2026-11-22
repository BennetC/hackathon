# Formula agent 3: one consensus price for both a and b

Read-only analysis. No submissions, no model calls, no state.json touched. Scripts are in this folder:
`data.py` (loader plus a per-line evaluator; `check.py` shows it matches `fable_vs_opus.replay` to the cent),
`final.py` (the rule and the fit), `evaluate.py` (all the numbers below, saved in `evaluate.out`).

## The rule

For each line, take three price estimates:
- **F2**: the median `fair_gross_total` of group 2 (Fable + 2 Opus);
- **F3**: the median `fair_gross_total` of group 3 (2 Fable + 1 Opus, bottom-up with the price book);
- **J**: the charge a given by the Opus judge `j-all9`, which reads all 9 researchers.

Then:

```
X = geometric mean of the available positive values among {F2, F3, J}
if more than half of all researchers (groups 1-3) say covered and related, and X exists:
    a = 0.93 * X
    b = 1.00 * X
else:
    a = 0,  b = 0
```

Why each term is there:
- **Three sources, equal weight.** Group 3 and group 2 are the two most accurate researcher groups. The judge has already weighed all 9 researchers against its own market feedback. Group 1 is dropped because it is the least accurate source on its own (its best charge earns 210K vs 265K for group 3 on odd games) and adding it changes nothing (odd worst case 78.7K with it, 80.5K without). Fitting the weights instead of using equal ones gives a broad plateau around 1/3 each, so equal weights cost nothing and add no parameters.
- **Geometric mean.** Prices range from about 10 to 3,000 EUR and the errors are proportional, so an average on the ratio scale is the right one. It also limits how far one outlier can drag the price. On odd games the arithmetic mean needed k = 0.86 and did worse.
- **A source that says uncovered (a value of 0) gives no price.** It is left out of the mean instead of pulling it to 0.
- **Coverage = majority of all researchers.** I tried stricter versions (group-3 majority, ≥ 2/3, judge > 0); they change the result by less than 1.5K, so I kept the simplest. Lines most researchers call uncovered are not charged (not approved).
- **a = 0.93 X.** The market's proven-fair level sits about 3-7% below our consensus on the big lines, and charging above that level can lose the whole line (the cliff). 0.93 maximises the odd-game worst case averaged over k ± 0.02, which is the one fitted parameter. The bootstrap of that fit has its median at 0.93 (quartiles 0.89-0.94).
- **b = 1.00 X: accept any bill up to our own fair estimate.** This needs no fitting: the odd-game optimum is 0.99 and the curve is flat from 0.97 to 1.04 (bootstrap 5-95%: 0.98-1.02). Using the same X for both sides is also what works best for b: GM(g2, g3, j-all9) is the best b base on odd games and on even games.
- **b = 0 on uncovered lines.** Accepting any share u of X there only adds cost (odd worst case: u = 0.2 costs 11K, u = 1 costs 57K).

So the rule has one fitted number (k) and one fixed by reasoning (m = 1).

## Results (replayed net, worst..best (mid); same simulator and teams list as `ruben3_test.py`)

| rule | odd games (fit) | even games (validation) | even 36-46 |
|---|---|---|---|
| **this rule, 0.93 / 1.00** | **+80.5K..+152.6K (+116.5K)** | **+64.3K..+125.0K (+94.7K)** | +24.2K..+47.1K (+35.6K) |
| baseline: Ruben avg 2 groups (live) | +48.7K..+176.8K (+112.7K) | +47.2K..+198.0K (+122.6K) | +24.7K..+62.1K (+43.4K) |
| baseline: Ruben avg 3 groups | +46.8K..+201.0K (+123.9K) | +57.0K..+197.0K (+127.0K) | +26.8K..+63.9K (+45.3K) |
| baseline: group 3 alone (0.93 / 0.91) | +55.4K..+193.3K (+124.3K) | +51.4K..+181.9K (+116.7K) | +32.0K..+71.2K (+51.6K) |
| *extra column: this rule + old judge's a on uncovered lines* | +85.5K..+199.7K | +68.0K..+189.8K | +24.2K..+62.0K |
| *baselines without their uncovered-line charge: 2 groups / 3 groups / g3* | +43.7K / +40.4K / +49.0K worst | +43.4K / +53.3K / +47.7K worst | +24.6K / +26.7K / +31.9K worst |

Baselines reproduced exactly (games 36-47: 2 groups +35.6K..+84.8K, 3 groups +38.2K..+89.8K, g3 +44.0K..+95.7K).
Important for reading the best case: when a group calls a line uncovered, the baselines fall back to the old judge's a. That is a charge on uncovered lines, and it supplies most of their best-case lead. The extra column adds the same fallback to this rule; against the matching strict baselines, the rule leads on midpoint too (even games: +94.7K vs +82-93K).

## Robustness

Worst case for each k/m change (odd | even | even 36-46):

| k / m | odd | even | even 36-46 |
|---|---|---|---|
| k 0.88 | +82.6K | +55.0K | +20.8K |
| k 0.91 | +89.2K | +62.3K | +22.6K |
| k 0.92 | +77.1K | +61.5K | +22.2K |
| **k 0.93** | **+80.5K** | **+64.3K** | **+24.2K** |
| k 0.94 | +88.0K | +64.9K | +24.8K |
| k 0.95 | +91.5K | **+39.9K** | **+7.7K** |
| k 0.98 | −32.0K | −1.5K | −20.4K |
| m 0.95 / 0.98 / 1.02 / 1.05 | +74.3 / +80.9 / +78.8 / +73.0K | +61.1 / +63.6 / +64.8 / +65.8K | +22.4 / +23.5 / +24.2 / +24.9K |

- **m is robust.** The rule beats every baseline at any m from 0.95 to 1.05.
- **k has a cliff at 0.95** on even games (−24K) and **at 0.97-0.98** on odd games (−70K). A few big lines decide it (for example g45 line 3, g29 line 1, g36 line 15: there our consensus sits 3-5% above the market's proven-fair level). Never round k up. If in doubt, go down: 0.91 loses only about 2K on even games.

Bootstrap over games (2000 resamples), this rule minus each baseline, worst case:

| split | vs 2 groups | vs 3 groups | vs g3 alone |
|---|---|---|---|
| odd | +29.7K, P(>0) = 0.94 | +31.2K, P = 0.94 | +23.8K, P = 0.80 |
| even (validation) | **+16.3K, P = 0.92** | +6.4K, P = 0.75 | +12.0K, P = 0.76 |
| even 36-46 | −0.7K, P = 0.43 | −2.5K, P = 0.21 | **−7.5K, P = 0.16** |

Midpoint: the rule loses to the as-is baselines on even games (P(>0) ≤ 0.16), because of the uncovered-line charge described above.

## Honest caveat: the recent block

On even games 36-46 the rule ties the live 2-group rule (−0.7K) but **loses to group 3 alone by 7.5K in the worst case**, mainly in g46 (−8.9K vs −2.1K) and g38 (+6.4K vs +10.3K).

The cause is the a side. The judge's charge is deliberately low: 59-73% of judge charges sit below the market's proven-fair level. In games 13-35 that caution pays (+18K worst case on even games 13-35). Once group 3 matured (36+), it gives up about 4-8K per 6 games on the a side. The b side with the judge stays better in every block.

The alternative that does fix it (a = 0.93·F3, b = X) is in the recommendation below. What I tried that did not fix it:
- the judge's midpoint √(a·b) or its b as the judge's price: worse everywhere;
- weighting sources by tracked accuracy: group 2 and group 3 are equally far from the market range in 36-47 (0.263 vs 0.255 mean log error), so the weights would barely move.

## Recommendation

Adopt **X = GM(group-2 median fair, group-3 median fair, j-all9 charge); a = 0.93·X, b = X; both 0 when most researchers say uncovered.**

It is the best worst-case rule on odd games (+80.5K vs +46.8-55.4K) and it validates on even games (+64.3K vs +47.2-57.0K). It has one fitted number, and m is robust.

Two conditions:
1. **Never raise k above 0.93**; 0.91-0.92 is the safe side.
2. **Watch the recent block.** On even games 36-46, group 3 alone is ahead of this rule by 7.5K worst case. On odd games 37-47, though, the two tie (+12.2K vs +12.0K worst case), so the lead is not consistent.

A middle path keeps the robust b side and drops the judge from the charge: **a = 0.93·F3, b = X.** I checked it after the fact (no new fitting), so treat it as an option, not a validated choice:

| | odd 37-47 | even 36-46 | all odd | all even |
|---|---|---|---|---|
| middle path (worst case) | +16.1K | +32.5K | +65.5K | +55.5K |
| this rule | +12.2K | +24.2K | +80.5K | +64.3K |
| group 3 alone | +12.0K | +32.0K | +55.4K | +51.4K |

The middle path is the best on both recent blocks but gives up about 15K (odd) and 9K (even) over all games. If the live future looks like games 36+, it is the better pick.
