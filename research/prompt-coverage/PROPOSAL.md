# Prompt angle: coverage and relatedness decisions ("evidence-bound policy auditor")

Data: 252 lines in games 1-35 (`tx_cache` 1-29, `opponents/tx_30_34.pkl`, `s4-imitate-404/tx_35.pkl`). Sources: 6 per line in
games 1-29 (v1 opus-1..3 + v2-train fable-1, opus-1, opus-2), 3-6 from live v2 in games 30-35. A source votes "no" if
`covered` or `related` is false. Market truth: COVERED = lo > 0; UNCOV_PROVEN = hi <= 0.25 x our fair (every real charge
proven inflated); UNCOV_LIKELY = no bound and no charge ever accepted. Scripts: `build.py`, `analyze.py`, `reductions*.py`,
`money.py` (per-line replay, same logic as `fable_vs_opus.replay`), `corr.py`; outputs in `*.out`. Read-only, no model calls.

## 1. Evidence

**Binary coverage calls are almost always right, and every error is on the strict side.**
| vote shape | market COVERED | UNCOV_PROVEN | UNCOV_LIKELY | unknown |
|---|---|---|---|---|
| all sources "yes" (120) | 99 | **0** | **0** | 21 |
| split (5) | **5** | 0 | 0 | 0 |
| all sources "no" (127) | **2** | 40 | 59 | 26 |
- Single votes: 28 of 564 votes on proven-covered lines say "no" (5%; by source fable-1 2/106, v1/opus-2 3/82, v2/opus-2 3/106,
  v1/opus-1 6/82, v1/opus-3 7/82, v2/opus-1 7/106). Votes saying "yes" on proven-uncovered lines: **0 of 213**.
  The sources agree with each other on 247/252 lines. Upgrades, pre-existing damage, gradual leakage, unaffected areas and
  elective extras were all excluded correctly (e.g. g20 l3/l5 gradual leakage, fairs 2.2-3.5K, market hi 150/200).
- The 7 wrong lines, by cause:
  - **optional cover missed**: g14 l1-l4 (glass breakage). The description says "the optional Glass Breakage Cover [was]
    selected". 3/6 said not covered anyway. The market paid on all 4 (l1 lo 64 vs our fair 25).
  - **false "duplicate / one charge per invoice"**: g21 l5, the second vehicle charge, 6/6 no, lo 76 (> our fair 55).
    g21 l12, transition pieces called a "duplicate of pos. 8", 6/6 no, lo 49.
  - **"cleanliness" exclusion over-applied**: g21 l13, final site cleaning, 4/6 no, lo 78.
  - The models did get the real "return visit" vehicle charges right: g21 l21 hi 13, g32 l7 hi 10.
- Money: small. FDN actually lost -1.4K on these 7 lines. The formula on all fairs makes +0.7K..+1.1K on them. Using only the
  covered voters or the non-zero fairs makes -0.1K..+2.4K.

**Coverage AMOUNT is the bigger policy-reading error: percentage reductions get applied that the market does not apply.**
On market-covered lines, compare answers whose description says they cut the price by a percentage or for depreciation
(50% surge rule, "halved", "current value", "rateably") with the other sources on the same 11 lines:
| | n | fair < lo (undercharged) | inside [lo,hi) | median fair / lo |
|---|---|---|---|---|
| applied a % / depreciation cut | 41 | **63%** | 20% | **0.83** |
| other sources, same lines | 25 | 56% | 36% | 0.97 |
| applied an absolute EUR cap / sub-limit (12 lines) | 24 | 38% | **54%** | 1.03 |
| other sources, same lines | 45 | 47% | 38% | 1.02 |
- g17 (surge, no surge protector; policy 2.3.3 halves the indemnity): 5/6 sources halved. The market paid near full price:
  TV lo 518 vs halved 295, AV receiver lo 467 vs 190-230, plug lo 28 vs 15.
  g21 l17 (table at "current value", 300): lo 524, the new price. Absolute caps, by contrast, matched the market:
  g31 l3 watch sub-limit 3,000 in [2,900, 3,110); g34 l4/l8 vehicle "max 70 net" = 83 vs lo 83/76.
- Money (replay, formula on the fairs): g17 l1-l4 + g21 l17 go from -2.2K..-0.3K to **+3.9K..+7.6K** if the cut is undone.
  FDN's actual net on all 12 flagged lines was **-5.9K**. Across all 12 lines the effect is mixed (pess +9.2K -> +6.4K,
  opt +18.8K -> +25.6K), because on g19 l2 the un-cut estimate goes above lo.
- What is left is not about coverage: 9 all-"yes" lines where hi <= 0.5 x our fair (g21 drying 0.3-0.5, g32 plaster/paint
  0.2-0.3, g8 green waste). The policies show no clause there; those are quantity and unit errors.
- The sources' errors are highly correlated: mean pairwise correlation of log(fair / market mid) = **0.88** (0.83-0.94,
  42 two-sided covered lines).
- **Uncovered lines have no consistent fair:** v1/opus-2/3 write 0, v2/opus-1 writes 5-10, fable-1/opus-2 write the full price.
  On 99 all-"no" uncovered lines, an explicit b = 0 is worth +0.3K pess versus the current formula. That guard is
  only safe while a 0-writer is in the pool.

## 2. System prompt (both models; most useful for Opus, the sessions with the most false "no" votes)

Use it as the system prompt (`--system-prompt`). Replace the first 6 lines of `build_prompt()` with: "Judge every line of the
invoice below. Return exactly one entry per invoice line, in invoice order." Keep the `<case>` block unchanged and the
schema the same (`opus_case.SCHEMA`), so the new answers can be pooled with the old ones.

```
You are a strict policy auditor at a German property insurer. Strict means evidence-bound in both directions: every decision
that lowers or removes a payment needs a clause you can cite, and anything the policy does not exclude is paid. You never
trust the invoice wording alone, and you still price every line.

Work in this order before answering:
1. Map the policy. List the insured perils and optional covers. Check the schedule AND the damage description for which
   optional covers were agreed; a statement in the description that a cover was selected counts. Write down every fixed
   EUR amount: sub-limits, caps, flat maxima per item, per visit or per day. Read the exclusions and conditions at the end.
2. Fix the insured event: what was damaged, by what cause, and which parts of the property were affected.
3. Audit each line against the policy, clause by clause.
   - related = the work is needed because of this event on an affected part: diagnosis and leak detection, access,
     protection, repair or replacement, drying, cleaning up after the work, disposal of damaged material, and travel or
     attendance for that work.
   - covered = related AND no clause excludes it. Mark it not covered only if you can name the excluding clause or show it
     is not caused by the event: pre-existing defects or wear, gradual damage where excluded, the upgrade part beyond the
     previous standard, unaffected areas or items, elective extras, or items the policy says are not indemnified.
   - A line is a duplicate only if it bills the same work, by the same trade, on the same visit as another line. Separate
     trades, materials versus labour, and the travel of a second firm are not duplicates. A return visit that only the
     contractor caused is not covered.
   - If the policy is silent or ambiguous, the line is covered.
4. Price each line: fair_gross_total = what a reputable German contractor invoices for this line today, quantity x unit
   price at normal full rates, incl. 19% VAT.
   - Apply a fixed EUR cap, sub-limit or flat maximum the policy states for this kind of item: fair = min(price, cap). Split
     a cap shared by several lines in proportion to their prices.
   - Do NOT reduce the line price for percentage cuts, halving rules, depreciation or current value, or deductibles. These
     are settled on the claim total, not on invoice lines. Mention them in the description instead.
   - Lines that are not covered or not related still get their full gross price in fair_gross_total, low and high. The
     coverage decision is carried only by the two flags.
5. low = a price you are confident the fair value is AT LEAST. It is exactly what we charge: 1 EUR above the true value loses
   the whole line, 1 EUR below loses 1 EUR. high = a price you are confident the fair value is below.

description = the invoice text, then " | " and the deciding clause numbers; for a line that is not covered or not related,
add the exclusion in at most six words.
```
(About 515 words.)

**Per-game feedback (sequential sessions, as in `v2_train.py`).** After game g is completed, send its normal
`feedback_line` rows plus one coverage row per line:
`line i: you said covered=<c>/related=<r>; market: proven paid as fair up to <lo>` (if lo > 0),
or `every charge >= <hi> was rejected` (hi <= 0.25 x their fair), or `no market information`.
End with: "Name the clause pattern you misread, if any, in at most 2 sentences." This uses only bounds of games < the one
being priced. **Leakage note:** the prompt rules come from outcomes in games 1-21: g14 (optional cover), g21 (duplicate
and cleaning rules, the current-value table) and g1/g4/g17/g19 (% cuts). The EUR-cap rule only keeps what the sources
already do. So **judge the effect only on games >= 22**. Games 1-21 are in-sample for this prompt.

**Pooling requirement.** This group writes the full price on uncovered lines. Before pooling, add the explicit guard from
`research/uncovered`: if a majority of all sources vote not covered/related, set b = 0. Otherwise `b = 1.04 x min fair`
stays 0 only while v1/opus-2/3 are in the pool.

## 3. Why the answers should differ, expected effect, risks

- **Different on purpose in two places only.** (a) Coverage: an exclusion needs a cited clause, and ambiguity counts as covered.
  That targets the 7 one-sided false "no" lines without touching the clear exclusions, which are all clause-backed.
  (b) Amount: keep EUR caps, drop % cuts and depreciation. That targets the 0.83 fair/lo bias on the reduction lines
  (g17-type cases are worth about +4-6K each). A neutral prompt cannot decorrelate either one, because all 6 current
  sources share the same instinct.
- **Expected effect:** small on binary coverage (on the order of 1-2K over 35 games, about 3% of lines). Larger whenever a
  policy has a % / depreciation clause (5 of 35 games had one). Little change in price correlation on ordinary lines (0.88
  stays), so pair this group with a price-level angle. Adding 3 independent coverage votes keeps a 9-source majority robust
  even if one session goes strict.
- **Risks.**
  - Overpricing: "full rates, no % cut" raises fairs. If the truth does apply a cut, the charge becomes inflated and the
    whole line is lost. The evidence is thin (11 lines, about 5 cases, 3 policies).
  - "Ambiguous = covered" could create false "yes" votes; today there are 0/213. This only matters through the b = 0
    majority guard, and 3 of 9 votes cannot flip it alone.
  - Uncovered lines priced at full price raise the pooled median a there. That is harmless because those charges are
    rejected, but it needs the explicit b guard (above).
  - Honesty story: the % rule is defensible as "deductions are applied to the claim total, not to invoice lines" and
    should be presented that way.

## 4. How to check after the runs (games >= 22 only, walk-forward)

1. **Coverage confusion vs market** (`analyze.py` with the new sources added to `build.py:sources()`):
   - false-"no" rate on lo > 0 lines: target below fable-1's 2%, against today's 2-7%;
   - false-"yes" on UNCOV_PROVEN: must stay about 0;
   - when the new group disagrees with the 6-source majority, how often the market sides with it.
2. **Amount bias:**
   - on lines where any source cites a %/depreciation clause: median fair/lo (target about 1.0) and the share below lo;
   - overall: share inside [lo,hi), share < lo, share >= hi, censored error by category, against each current source
     (`research/sources/accuracy.py` metrics).
3. **Decorrelation:** pairwise correlation of log(fair / mid) between the new sources and the current 6 (today 0.83-0.94),
   and Cohen's kappa on coverage votes.
4. **Money:** replay the live formula plus the b = 0 majority guard on 9 sources vs 6, pess/opt (`money.py` logic). Report
   it per game and only on games >= 22. Also report it on the subset of lines where the new group's coverage vote or %
   handling differs, since that is where this angle should earn its keep.
