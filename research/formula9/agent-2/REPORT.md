# Formula research, agent 2: one pooled price per line

Read-only. Nothing was submitted, no model calls were made, and no state was written. Scripts are in this folder:
`lib.py` (loaders plus an exact per-line replay, which matches `fable_vs_opus.replay` to 1e-10 and reproduces the baseline
numbers in the brief), `final.py` (the rule, splits, robustness and bootstrap), and `final_out.txt` (the full output).

## The rule

For each invoice line:

- **Voices** = the fair_gross_total of every researcher (up to 9, all 3 groups) who says the line is *covered and related*,
  plus the positive charge `a` of each of the 4 new judges (j-all9, j-g1, j-g2, j-g3).
- **Gate:** the line is priced only if more than half of the researchers who answered it say it is covered and related.
  Otherwise a = 0 and b = 0.
- **P** = median(voices)
- **a = 0.91 · P**, **b = 0.99 · P**

The reason for each term:

- **Pooled median.** One wild source, or a whole group that misreads a line type, cannot move the price; the price is
  what most voices agree on.
- **Judges as voices.** The judges have seen the market's lo/hi feedback on every earlier case, so they carry calibration
  to real market price levels that the researchers lack.
- **Majority gate.** It follows Daniil's rule: we do not bill lines that most researchers call uncovered, and as insurer
  we reject every bill on those lines.
- **0.91 on the charge.** An overcharge loses the whole line, while an undercharge costs only the gap, so we bill about 9%
  under the consensus price. The value was chosen with a smoothed objective (the average over K ± 0.04) so that it sits
  on the plateau, not at the cliff edge.
- **0.99 on the limit.** We accept any bill up to our own consensus price. The paid curve is flat between 0.95 and 1.01.

That is 2 parameters and one gate. There are no tiers and no per-category values. A spread-dependent shading term
(a = K·P·e^(−c·spread), with 4 different spread measures) and spread terms on b added nothing on odd games, so I dropped
them.

## Results (net payoff, EUR; worst = net_lo is the primary score)

| rule | odd games (fit): worst / best / mid | even games (validation): worst / best / mid | even 36–46: worst / best / mid |
|---|---|---|---|
| **NEW a=.91P, b=.99P** | **+83.0K** / +140.0K / +111.5K | **+52.1K** / +107.6K / +79.8K | **+14.8K** / +35.9K / +25.4K |
| Baseline: Ruben avg 2 groups (live now) | +48.7K / +176.8K / +112.7K | +47.2K / +198.0K / +122.6K | +24.7K / +62.1K / +43.4K |
| Baseline: Ruben avg 3 groups | +46.8K / +201.0K / +123.9K | +57.0K / +197.0K / +127.0K | +26.8K / +63.9K / +45.3K |
| (ref.) group 3 alone | +55.4K / +193.3K / +124.3K | +51.4K / +181.9K / +116.7K | +32.0K / +71.2K / +51.6K |
| extra, NOT approved: also charge minority-covered lines at 0.91P (b = 0) | +86.9K / +144.3K | +52.5K / +108.4K | +15.1K / +36.5K |

There are 24 odd games (1–47) and 23 even games (2–46). Game 47 has no new-judge data, so it uses the researchers only.

## Robustness

**Each tuned value shifted, one at a time (worst-case net):**

| shift | odd | even | even 36–46 |
|---|---|---|---|
| K = 0.86 | +72.5K | +40.4K | +7.9K |
| K = 0.89 | +76.9K | +51.0K | +14.2K |
| **K = 0.91** | **+83.0K** | **+52.1K** | **+14.8K** |
| K = 0.93 | +93.0K | +54.7K | +17.4K |
| K = 0.96 | +46.3K | **+7.6K** | **−17.7K** |
| M = 0.94 / 0.97 / 1.01 / 1.04 (odd) | +77.1K / +82.0K / +82.4K / +77.4K | +50.9K … +54.3K | +14.7K … +15.9K |

- **The charge cliff is real and lumpy.** The drop between 0.94 and 0.96 on odd games comes mostly from 3 lines
  (game 45 line 3, game 5 line 1, game 43 line 9). On those, the market's proven-fair level is about 0.95 × P.
- **K above about 0.94 is dangerous. K below 0.91 costs a little.** The acceptance limit M is flat and safe.

**Bootstrap refit on resampled odd games (300 resamples):** K has median 0.91 and 5–95% range [0.83, 0.92]. M has median
0.99 and range [0.98, 1.06].

**Bootstrap over games (2,000 resamples):** chance that NEW's worst case beats the baseline, with the median difference.

| | vs 2 groups | vs 3 groups |
|---|---|---|
| odd (fit) | P = 0.91, +33.7K | P = 0.94, +34.7K |
| even (validation) | P = 0.65, +4.9K (5–95% [−14K, +28K]) | P = 0.38, −4.2K (5–95% [−29K, +17K]) |
| even 36–46 | P = 0.00, −9.6K | P = 0.08, −11.5K |

## What I found

1. **Odd games point clearly to the pooled median, but the gain does not carry over.** It wins on all odd games and also
   on odd games 13 and later only (+58.6K vs +35.5K for group 3 alone). On even games it is between the two baselines.
   - Split by line type, the even games show the whole picture. On lines most researchers call covered, NEW earns
     +227.2K vs +227.5K for 3 groups, and pays 174.9K vs 174.1K: a tie.
   - The 3-group baseline's remaining +3.7K comes from billing lines most researchers call uncovered (through the
     judge fallback), which is not approved.
   - So the +34K odd-game gain is mostly the lumpy cliff lines, even with the smoothed objective.
2. **The worst-case gain is real on the insurer side, but the best case falls.** The rule rejects more, so net_lo
   improves and net_hi falls a lot (−90K vs baseline on even games). The midpoint is clearly worse than both baselines on
   every split.
3. **In the recent block (even 36–46) the rule loses about 10K to both baselines.** Most of the deficit is one game: game 38
   (−1.2K vs +9.2K for 3 groups). There NEW earns 8.7K less and pays 1.9K more. On recent odd games (31–47), however, the rule beats 3 groups: +40.0K vs +25.5K. At the scale
   of a few games this is noise in either direction.
4. **Every tuning gain is smaller than the game-to-game noise.** The 5–95% bootstrap ranges are ±25–30K, so nothing here
   proves a new rule better than the 3-group baseline.

**Contamination note:** one early exploration script printed even-game numbers for single bases (group 3 × 0.92 looked
best there). I did not use them: the rule was picked on odd games only, and its even result is reported once, above.

## Recommendation

- **Do not switch the live formula on this evidence.** The pooled-median rule is simple and principled. It is the best
  rule on odd games (worst case +83.0K vs +48.7K / +46.8K), but it only ties the baselines on even validation
  (+52.1K vs +47.2K / +57.0K) and loses on even 36–46 (+14.8K vs +24.7K / +26.8K). Its best case and midpoint are much
  worse.
- **If a change is made anyway**, the usable lessons are robust:
  - (a) Never put the charge multiplier above about 0.93 × consensus. 0.96 collapses on every split.
  - (b) The acceptance limit is safe anywhere between 0.95 and 1.01 × consensus.
  - (c) The pooled median of 9 researchers plus 4 judges is a sensible single price if one is wanted, with a = 0.91P and
    b = 0.99P.
