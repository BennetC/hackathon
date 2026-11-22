# Prompt idea: a price memory from earlier games (leakage-free)

**Verdict: the data does not support this as the main angle for the third group.** As a hard or soft anchor it lost money
in every replay variant I tried. A restricted, price-only version (below) is the safest form if you still want it.
- In that form it adds a less correlated source: error correlation 0.53 with our median, vs 0.72-0.93 among the 6
  existing sources.
- Its expected payoff is about 0 (roughly ±1K over games 6-35).

Data and method:
- **Data:** `research/s4-imitate-404/lines.pkl`, i.e. games 1-35 with market bounds and the v1+v2 source answers. It has
  252 lines with transactions: 106 P lines (lo > 0) and 49 lines proven to be about 0.
- **Scripts:** `sim.py` (hard anchors), `sim2.py` (clamp, stability, coverage transfer), `sim3.py` (blend and
  error-ratio rules), `sim4.py` (repeats, pooling, correlation), `sim5.py` (closest source), `context_block.py` (block
  builder).
- **No look-ahead:** every reference comes only from games < g.
- **Replay:** `lib.net` per line, with formula.py applied to raw vs anchored fair values. Deltas are worst..best.
- **Matching:** token-Jaccard similarity of the line descriptions (+0.1 for the same category), with quantities scaled
  by h / m² / pcs.

## 1. Evidence

| Finding | Number |
|---|---|
| Lines with an informative earlier reference (sim >= 0.5 / >= 0.8) | 43% / 28% of all lines; 46% / 25% of P lines |
| Covered-only price block, rows per game (sim >= 0.5, max 3 per line) | median 1, max 10; 13 of 34 games get no row (the 60-row cap is never reached) |
| The market's t for the **same item** drifts between games | lo_t / lo_ref IQR 0.65-1.34 (sim >= 0.5) and 0.89-1.13 (exact repeats); ranges overlap in only 9 of 14 exact repeats |
| Example of drift: "Vehicle costs" | c14 13-16, c16 >= 60, c18 >= 68, c25 38-44, c27 >= 74, c32 37-41 |
| **Coverage flips** on near-identical repeats (sim >= 0.8) | 16 of 39. Example: the c16 facade lines were uncovered (hi 8-17), but the same invoice in c32 was covered (lo up to 314) |
| Our sources already learned the repeats | median \|log F/t\| 0.128 on the first occurrence, 0.055 on the repeat (session feedback + same-policy note). That is below the drift of t itself (0.075) |
| Our fair value is not biased low on P lines | median F/lo 1.02 (labour 1.02, parts 1.03, fee 1.09, vehicle 0.88). The "20-40% low" is the `low` field (0.64-0.80 x lo) |
| The 15 largest P lines where our sources were >= 30% off | 11 have no reference with sim >= 0.5. These are goods: TV, laptop, kitchen table, scaffolding, AV receiver. The anchors fixed **0** of the other 4. Example: the c15 speakers were anchored to the c1 bundle (781 vs lo 389), which makes the charge inflated |

Simulated rules, as replay delta vs formula.py on raw fair values, games 6-35:

| Rule | Delta (worst..best) | Error on bracketed lines (before -> after) |
|---|---|---|
| Hard anchor (sim >= 0.5): replace with the past lo, zero if the past line was uncovered, cap at the past hi | -36.9K..-57.6K | - |
| Clamp F into the reference's [lo, 0.97 hi), covered refs only, sim >= 0.5 / >= 1.0 | -15.8K..-13.1K / -2.7K..-6.0K | - |
| Same clamp, service lines only (labour, vehicle, fee, disposal, diagnostic) | -3.3K..-3.4K | - |
| Geometric blend toward the reference, w = 0.3, sim >= 0.8 (best variant) | -0.9K..-0.3K | 0.054 -> 0.057 |
| Transfer our past error ratio on the item, w = 0.3 to 1.0 | -4K..-26K | worse |
| Pick the source whose estimate is closest to the reference, sim >= 1.0 | -1.6K..-1.3K | 0.055 -> 0.051 |
| Pool: 6 sources + 3 anchored pseudo-sources | -1.2K..+0.3K (best) to -6.0K..-1.9K | - |

Why the anchor fails:
1. The sessions already carry the price memory through per-game feedback and the "SAME POLICY AS CASE X" block in
   `v2_train.policy_note`.
2. t is tied to each invoice's hidden price and changes by about 8-35% between games.
3. Coverage depends on the policy, not on the item.
4. Large errors happen on goods that never appeared before.

## 2. Proposed system prompt (restricted, price-only form; best suited to Opus 5.5)

Use the current `build_prompt` case section and `SCHEMA` unchanged. Insert the PRICE MEMORY block just before `<case>`.
Per-game feedback is the same as in `v2_train` (`sb.feedback_line` + `GOAL`).

> You are a German claims-pricing expert with a price memory. For every line of the invoice below, judge whether it is covered by THIS policy and related to THIS damage. Then estimate the fair GROSS line total in EUR (quantity x unit price, incl. 19% VAT) with a low/high range. Return one entry per invoice line, in invoice order. Uncovered or unrelated lines still get a price estimate.
>
> You may get a PRICE MEMORY block. It lists items from earlier cases whose fair value the market later proved:
> - "a-b" means a charge of a was paid as fair, and a charge of b was proven inflated.
> - ">=a" means a was paid as fair and nothing higher is known.
> - "our estimate then" is what we estimated at the time.
>
> Rules for using it:
> 1. It is evidence about PRICE LEVELS only. It says nothing about coverage. The same invoice line has been covered in one case and excluded in another because the policy differed. Decide coverage only from this policy and this description.
> 2. The fair value of the same item moves between cases, often by 10-30%, because each invoice has its own real price. Use the memory to check the order of magnitude of your estimate and to catch large mistakes. Do not copy a number from it.
> 3. Rescale by quantity: hours, m², pieces, days.
> 4. Do not transfer prices between different goods. A TV, laptop, piece of furniture or bundle in an earlier case says nothing about a different one. Labour rates, call-out or vehicle fees, disposal and small fittings transfer best.
> 5. If several rows disagree, the truth for this case can lie anywhere in their spread. Prefer what the current invoice and photo tell you.
> 6. If there is no row for a line, estimate it independently, as an experienced expert would.
>
> Read the whole policy, including the exclusions and conditions near the end.
>
> `low` is exactly what we charge. Charging even 1 EUR above the true fair value loses the whole line, while 1 EUR below loses only 1 EUR. So `low` must be a price you are confident the fair value is at least. `high` is a price you are confident the fair value is below. `fair_gross_total` is your best estimate in between.

Per-game context block (from `context_block.block(g, inv_lines)`):
- Rows come only from lines in games < g that the market proved covered (lo > 0).
- For each current line (matched against the pdftotext invoice lines), take the 3 most similar earlier lines with sim >= 0.5.
- Cap at 60 rows. In practice there are 0-10.

Example for case 32:

```
=== PRICE MEMORY (market results of earlier cases; price levels only, coverage NOT implied) ===
line | earlier case: description | market range for t (gross EUR) | our estimate then
L1 | c25: Filling valve (internal frost-burst fitting) | 51-54 | 52
L1 | c16: Filling valve (internal frost-burst fitting) | 48-55 | 45
L3 | c25: Senior installer hours (3 h) | >=279 | 295
L5 | c18: Vehicle costs | >=68 | 60
L5 | c14: Vehicle costs | 13-16 | 19
L17 | c18: Construction waste disposal | >=57 | 40
```

## 3. Why it would differ, expected effect, risks

- **Why it differs:** the reference makes this group's errors depend on the market's past rather than on the shared model
  prior. In my simulation the error correlation was 0.53, vs 0.87 (median) between the existing sources.
- **Expected effect:** small to none. The repeats are already learned in-session, and the lines that matter (large goods)
  have no precedent.
- **Risks, all measured above:**
  - The model carries coverage over from an earlier case. In the hard-anchor test, the zeroed lines went from +4.4K..+28.1K to -15.2K.
  - It copies a drifted price into an inflated charge. The clamp rule raised the inflated share on changed lines from 23%
    to 36%.
  - It over-anchors on a loosely similar bundle (the c15 speakers vs the c1 electronics bundle).
- **Better use of the third group's prompt budget:** large-goods valuation, i.e. replacement value, depreciation and
  "new for old". All 11 of the unmatched big misses are there.

## 4. How to check after the runs

1. On P lines, compare median |log(F/t)| (t = sqrt(lo·hi), or lo when hi = inf) for lines **with** vs **without** memory
   rows, against the existing 6 sources on the same lines. Success means a lower error on lines with rows and no worse
   error elsewhere.
2. Measure the share of `low` >= hi (proven inflated) on lines with rows. It must not rise compared with the current
   sources.
3. Check coverage on lines whose best earlier reference had the **opposite** market outcome (the 16 flip cases and new
   ones). Agreement with the market should match the current sources.
4. Compute the error correlation with each existing source. The target is < 0.7.
5. Replay walk-forward (games 6+ and hold-out 25+) with formula.py on 6 vs 9 pooled sources, and with the judge given
   all 9. Adopt only if the worst case improves by more than about 2K.
