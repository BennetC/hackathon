# Agent 10: disagreement-shaded consensus over the 9 researchers

Read-only. Nothing was submitted, no live state was touched and no models were called. Scripts are in this folder.
`lib.py` is a fast per-line copy of `fable_vs_opus.replay`, checked against it to 0 mismatches (`check.py`). The baselines reproduce the brief exactly: games 36-47 give +35.6K..+84.8K (2 groups) and +38.2K..+89.8K (3 groups) (`base.py`).
Fit: odd games 1-47 (24 games). Validation: even games 2-46 (23 games; the judges have no data for game 47).

## The rule (3 tuned numbers)
For each line, take the researchers who answered it (up to 9: groups 1, 2 and 3).
1. **Coverage.** The line counts as covered only if more than half of them say covered and related. Otherwise a = b = 0.
   *Reason:* this is the approved policy, and charging lines that only a minority calls covered was not approved.
2. **Centre.** V = the fair values from the researchers who call the line covered. M = median(V).
   *Reason:* every researcher gets one vote, and the median ignores a single outlier.
3. **Disagreement.** s = population standard deviation of ln V (0 if V has one value).
   *Reason:* when the researchers disagree, our estimate of the fair value t is less certain.
4. **Charge.** **a = 0.93 · M · exp(−1.1 · s)**
   *Reason:* charging above t loses the whole line, while charging below t costs only the gap. So we charge at a low quantile of our belief about t. The factor 0.93 covers the error when everyone agrees: the market's proven-fair level on the big agreed lines sits at about 0.93-0.97 · M. The exp(−1.1·s) term lowers the quantile further as the researchers disagree more.
5. **Acceptance limit.** **b = M · exp(−0.55 · s)**, i.e. the multiplier is 1 and the shading is λ/2.
   *Reason:* as insurer, the costs are much more even: accepting an inflated bill costs a, while rejecting a fair one costs an extra 0.5a. So we accept up to the centre and shade only half as much as the charge. A free fit on odd games put the multiplier at 1.00 and the shading at 0.6-0.7, which confirms this tie (`grid2.py`).

The judges are not used. Adding the judges' median a to the pool scored about 2K better on odd games (283.7K vs 280.8K earned, inside the noise), but it mixes a charge with fair values. The old Fable judge's a also did not help as a base. Using the judges for coverage scored +1.5K on odd (noise).

## Results (net worst..best, midpoint)
| split | **this rule** | Ruben 2 groups (live) | Ruben 3 groups | rule, charging minority-covered lines (extra, not approved) |
|---|---|---|---|---|
| odd (fit) | **+83.2K..+126.1K** (mid +104.6K) | +48.7K..+176.8K (+112.7K) | +46.8K..+201.0K (+123.9K) | +87.3K..+130.4K |
| even (validation) | **+53.3K..+106.3K** (mid +79.8K) | +47.2K..+198.0K (+122.6K) | +57.0K..+197.0K (+127.0K) | +52.0K..+106.3K |
| even 36-46 | **+18.6K..+37.0K** (mid +27.8K) | +24.7K..+62.1K (+43.4K) | +26.8K..+63.9K (+45.3K) | +18.4K..+37.6K |

Blocks, worst case. Odd: 1-12 +28.2K, 13-29 +21.1K, 30-47 +33.9K (Ruben 2 groups: +28.7K, +1.0K, +18.9K). Even: 1-12 +11.4K, 13-29 +12.6K, 30-46 +29.3K (Ruben 3 groups: +7.5K, +10.0K, +39.4K).

Per side, worst case (`sides.py`):
* **Acceptance side.** The rule pays less than both baselines on every split. On odd games it pays 197.6K against 211.2K (2 groups) and 207.2K (3 groups). On even games it pays 171.9K against 176.3K and 174.3K. On even 36-46 it pays 95.8K against 97.4K and 97.5K.
* **Charge side.** It wins on odd games: 280.8K earned against 259.9K and 254.0K. It is level or behind on even games: 225.2K against 223.4K and 231.2K. It is clearly behind on even 36-46: 114.5K against 122.1K and 124.2K.

## Robustness (change in worst-case net)
| change | odd | even | even 36-46 |
|---|---|---|---|
| K 0.93 −0.02 / +0.02 | −6.8K / −7.6K | −2.4K / −11.3K | +0.3K / −12.9K |
| K −0.05 / +0.05 | −18.4K / **−86.3K** | −12.4K / −46.1K | −5.1K / −49.9K |
| λ 1.1 ±0.05 | +1.7K / −2.1K | +1.9K / −1.1K | +1.2K / −0.5K |
| b multiplier 1.00 ±0.05 | −4.4K / −9.0K | −2.0K / +1.8K | −1.7K / +1.4K |
| b shading 0.55 ±0.05 (tie broken) | <0.4K | <0.6K | <0.7K |

* **The charge factor K sits next to a cliff at about 0.96.** A handful of big lines decide the earned total: 31/3 (41.6K), 45/3, 5/1, 42/1, 33/1 and 36/15. On these, market lo / M is between 0.93 and 0.97. On even game 36, line 15 sits exactly on the edge at k = 0.93.
* **How K and λ were chosen.** I took the best mean over a neighbourhood of k ±0.02 and λ ±0.1, not the single best point. The single best point (0.95, 1.15) is on the cliff edge.
* **Bootstrap, refitting on resampled odd games (300 times).** K: 5/50/95% = 0.88/0.93/0.95. λ: 0.5/0.85/1.25. Both halves of the odd games give the same answer on their own: λ ≈ 0.75-1.25 and k ≈ 0.93-0.95.
* **Bootstrap over games, gap to the baselines (worst case).**

  | comparison | gap | 5..95% interval | P(gap > 0) |
  |---|---|---|---|
  | vs 2 groups, even | +6.1K | −11.8K..+25.8K | 67% |
  | vs 3 groups, even | −3.7K | −21.2K..+15.5K | 39% |
  | vs 2 groups, even 36-46 | −6.1K | −8.8K..−3.7K | 0% |
  | vs 3 groups, even 36-46 | −8.1K | −20.7K..+2.1K | 11% |
  | vs both, odd (fit) | +35K | | about 90% |

## Recommendation
* **Do not replace the live charge rule with this one.** It wins clearly on the odd fit (+35K worst case) but does not hold up on validation. On even games it is a wash: +6K against 2 groups and −4K against 3 groups, neither significant. On the recent games 36-46 it loses 6-8K. Its best case is also about 90K lower, because it shades charges down.
* **What does hold up out of sample is the acceptance limit b = M · exp(−0.55·s).** It uses the median fair value of the researchers who call the line covered, shaded by half the log-spread. It pays less than both baselines in the worst case on every split: −4.4K and −2.4K on even games, −1.6K and −1.7K on even 36-46. It is flat to ±0.05 in its parameters.
* **What I would test next.** Keep Ruben 3 groups for a and switch b to this rule. I have not evaluated that combination on any split: I found that only the b side holds up after looking at the even results, so testing the mix on even games now would be tuning on the validation set.
* **If the team wants the most worst-case-robust rule regardless of the recent block,** use the full rule with K = 0.93 and λ = 1.1. Never raise K above 0.93: +0.02 costs 8-13K and +0.05 costs 50-86K.
