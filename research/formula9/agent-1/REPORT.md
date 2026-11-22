# Formula agent 1: per-line rule from 9 researchers + 4 judges

Read-only analysis. Nothing was submitted, no model calls, and no state files were written. Scripts are in this folder.
The evaluator in `core.py` is a line-separable copy of `fable_vs_opus.replay`. It matches replay to the cent (`verify.py`)
and reproduces the brief's baselines exactly: for games 36-47, Ruben-2 gives +35.6K..+84.8K, Ruben-3 +38.2K..+89.8K and
group 3 alone +44.0K..+95.7K. Data covers games 1-46 (the judges end at 46). Odd games = fit (23 games); even games =
validation (23 games); "even 36-46" = games 36, 38, 40, 42, 44, 46.

## Recommended rule ("M4-disc")

For each invoice line:

1. **Coverage gate.** Count the researchers who say covered **and** related, out of all available researchers (up to 9).
   If that is not more than half, set a = b = 0.
   *Reason:* we do not charge lines that most sources call uncovered (Daniil's constraint).
2. **Four estimates.** E = { median fair of G1, median fair of G2, median fair of G3, a of judge j-all9 }. Missing or zero
   values are dropped. G1 is absent in games 30-33 and 44.
   *Reason:* each research group is one independent vote. The all-9 judge has seen all 9 answers plus its own market
   feedback, so it is a fourth vote.
3. **M = median(E).**
   *Reason:* one wrong group (too high or too low) cannot move the price.
4. **σ = population SD of ln(E).**
   *Reason:* this is how much the four votes disagree, on a relative scale.
5. **a = 0.92 · M · exp(−0.25 · σ)**
   *Reason for 0.92:* overpricing loses the whole line, while underpricing costs only a little, so we charge somewhat
   below the consensus.
   *Reason for the discount:* the less the votes agree, the less sure the fair value is, so we step further down. For
   example, σ = 0.4 gives −10%, and agreeing lines are left almost unchanged.
6. **b = 0.98 · M**
   *Reason:* accept bills up to just below the consensus. The b-curve is flat (±0.05 moves the result by at most 7K), and
   the whole b-side is worth only about 20K over rejecting everything.

There are three tuned values: k = 0.92, c = 0.25 and m = 0.98. They were chosen on odd games with a smoothed objective,
the mean worst case over k−0.03..k+0.03. This is because the charge sits next to a cliff: on big round-price lines,
competitors charge about 0.95×, so the market's proven-fair level `lo` sits there.

## Results (net payoff, worst / midpoint / best, in K)

| rule | odd (fit) | odd 13+ | **even (validation)** | even 13+ | **even 36-46** |
|---|---|---|---|---|---|
| **M4-disc** | **+85.7** / +114.8 / +143.8 | +56.8 / +82.0 / +107.1 | **+56.0** / +86.8 / +117.6 | +44.5 / +63.0 / +81.4 | **+20.3** / +31.8 / +43.4 |
| Ruben avg 2 groups (live) | +50.6 / +113.5 / +176.4 | +21.9 / +66.9 / +112.0 | +47.2 / +122.6 / +198.0 | +39.5 / +95.3 / +151.1 | +24.7 / +43.4 / +62.1 |
| Ruben avg 3 groups | +47.9 / +122.7 / +197.6 | +31.9 / +86.5 / +141.0 | +57.0 / +127.0 / +197.0 | +49.4 / +101.2 / +153.0 | +26.8 / +45.3 / +63.9 |
| group 3 alone (Ruben) | +54.5 / +122.2 / +189.9 | +40.5 / +87.6 / +134.7 | +51.4 / +116.7 / +181.9 | +41.5 / +92.3 / +143.2 | +32.0 / +51.6 / +71.2 |
| extra column: M4-disc + j-all9 a on majority-uncovered lines (not approved) | +89.5 / +118.7 / +147.9 | +60.7 / +85.9 / +111.2 | +56.0 / +86.8 / +117.6 | +44.5 / +63.0 / +81.4 | +20.3 / +31.8 / +43.4 |

**Bootstrap over games** (5000 resamples of the per-game worst-case difference, rule minus baseline):

| split | vs Ruben-2 | vs Ruben-3 | vs group 3 alone |
|---|---|---|---|
| odd | +35.1K (90% CI −5.0..+83.1), P(better) = 0.91 | +37.8K, P = 0.94 | +31.2K, P = 0.89 |
| even | +8.8K (90% CI −8.8..+29.6), P = 0.77 | −1.0K (90% CI −17.8..+17.0), P = 0.44 | +4.6K, P = 0.58 |
| even 36-46 | −4.4K (90% CI −7.6..−0.5), P = 0.04 | −6.5K, P = 0.08 | −11.7K, P = 0.10 |

**Robustness** (worst case, odd/even, in K; base values are +85.7/+56.0):

| changed value | odd / even |
|---|---|
| k −0.05 | +72.1 / +46.6 |
| k −0.02 | +81.3 / +56.5 |
| k +0.02 | +94.5 / +42.8 |
| k +0.05 | **+47.1 / −9.1** (the cliff) |
| m ±0.02 | +85.9..+84.4 / +55.3..+55.7 |
| m ±0.05 | +78.8..+82.2 / +53.6..+55.9 |
| c −0.25 | +75.2 / +56.0 |
| c +0.25 | +81.3 / +50.8 |

Refitting on 30 bootstrap resamples of the odd games gives:

- k between 0.83 and 0.95 (median 0.93)
- c between 0.25 and 0.5
- m between 0.96 and 1.02
- even-game worst case of those refits: +35..+59K (median +55.9K)

## What I learned (odd-game analysis)

- **The charge side is everything.** Across sensible b-rules the b-side varies by only about 5K (−182..−190K on odd
  games; rejecting everything gives −207K). Across a-rules the charge side varies by about 40K.
- **Disagreement matters more than which source you pick.** Adding the σ-discount to the median-of-4 raised the odd
  result from +70.9K (no discount; best k = 0.85) to +85.7K, because it lets agreeing lines be charged at 0.92.
- **Alternatives tried on odd games** (robust objective, in K):
  - geometric mean with G3 counted twice: +86.4
  - median-of-4 + disc (chosen; simplest near the top): +83.7
  - median of all 9 fairs + 4 judge a's: +81.7
  - median of the 3 groups: +73..78
  - median(G3, judge): +75
  - G3 alone: +48
  - Two coverage gates were tested, majority of the 9 researchers and majority of the groups; both gave identical
    results.
- **Remaining loss is mostly underpricing.** Against a per-line oracle the rule leaves about 197K: 139K from
  underpricing and 57K from overpricing. The underpricing comes from lines where the market's proven-fair level is
  1.3-3.8× our consensus (often G3 was the high vote, but not reliably). The overpricing comes from unanimous lines where
  the market paid only about 0.6×. I found no simple, stable predictor for either.
- **Most of the baselines' higher best case is not real money.** Ruben charges a line if any single group's majority
  says covered (plus the judge fallback). 39K (odd) and 47K (even) of its best-case lead come from lines where no
  reviewer accepted any charge and nothing was ever proven fair.

## Honest verdict / recommendation

- **Fit.** On odd games M4-disc beats both baselines by +35..38K worst case. Most of that comes from two games: 29
  (+20.6K vs Ruben-2) and 33 (+17.7K).
- **Validation.** On even games it is +8.8K vs Ruben-2 and level with Ruben-3 (−1.0K). Neither difference is
  significant.
- **Recent block.** On even 36-46 it is **worse**: −4.4K vs Ruben-2, −6.5K vs Ruben-3 and −11.7K vs group 3 alone.
- **Best case and midpoint.** These are lower than the baselines, because the rule is more conservative.
- **Recommendation.** M4-disc is the best rule I can justify from odd-game fitting, and it is clean: one consensus value
  for both a and b, and three parameters. But the validation evidence does **not** support replacing the live rule. Do
  not switch on this evidence alone.
- **Disclosure.** While comparing families I also looked at even-game numbers for G3 alone at k = 0.92 (even +57.8K,
  even 36-46 +32.5K), so that figure is not a clean hold-out. It hints that a G3-led rule may suit the mature group 3
  better. That should be re-tested on games 47+ before anyone acts on it.
- **If anything is adopted,** keep k ≤ 0.92. The cliff starts about 0.03 above the optimum (k = 0.97 → even −9.1K).
