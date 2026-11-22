# Prompt proposal: market-rate calibration ("German trade invoice estimator")

Data: `research/s4-imitate-404/lines.pkl` (games 1-35, bounds + all sources), read-only. Scripts `a1.py`-`a7.py` here.
"Covered lines" = market lo > 0 and at least half our sources call the line covered (n = 103). F = median fair of the
sources that call it covered. Everything below is descriptive (nothing fitted), so walk-forward does not apply. The only
fitted number is the censored MLE in 1b, labelled as such.

## 1. Evidence

**a. The premise "our sources price 20-40% below market" is only true for `low`, not for `fair`.**

| | median /lo | share below lo (certainly too low) | share >= hi (certainly inflated, two-sided lines) |
|---|---|---|---|
| `low` (median of sources) | 0.77 | 77-87% per source | - |
| `fair` F | **1.02** (IQR 0.79-1.25) | 47% | 29/58 = **50%** |

On the 21 lines where the market only has an upper bound and we say covered, F >= hi on **21/21** (median F/hi 1.54).
The level of F is about right. The problem is spread: the log-sd of t/F is 0.74, about x2 on a typical line.

**b. A uniform upward shift ("price like Munich") makes it worse.** Multiplying F by m (covered lines):

| m | certainly too low | certainly inflated | EUR on lines not inflated |
|---|---|---|---|
| 0.9 | 65% | 21% | 21.2K |
| **1.0** | 47% | 28% | **22.9K** (peak) |
| 1.1 | 33% | 38% | 19.8K |
| 1.2 | 26% | 43% | 19.6K |

The EUR lost to overpricing is already about 4x the EUR lost to underpricing. Overpricing costs 11.1K: the full F on
50 lines where F >= hi. Underpricing costs at least 2.7K: lo - F on 48 lines.
The censored MLE says t/F = x1.30 overall, but that number is driven by lines with only a lower bound, and its sd is
0.74. In-sample: x1.17 labour, x1.19 parts, x2.6 vehicle (n = 10), x1.68 for F 50-150, x0.92 for F >= 1000.

**c. The bias has a sign that depends on the kind of line, so the levers are structural, not a level shift.**

| Line type (regex on description) | n | med F/lo | F < lo | F >= hi | EUR lost low / inflated |
|---|---|---|---|---|---|
| call-out / vehicle | 21 | **0.92** | 10 | 9 | 427 / 528 |
| specialist flat rates (leak detection, drying, measurement) | 15 | 1.09 | 5 | 5 | 292 / 1020 |
| hourly labour | 19 | 1.02 | 7 | 8 | 173 / 1718 |
| goods replacement (TV, laptop, bike, furniture) | 23 | 1.08 (late games 1.24) | 8 | 8 | 892 / **4444** |
| itemised materials / repair | 20 | 1.09 | 8 | 12 | 431 / **2941** |

The concrete patterns behind the big misses:
- **Frugal on specialist services (too low).** For these lines the market only gives a lower bound:
  - leak-detection call-out: market >= 229, ours 95;
  - electro-acoustic pinpointing: >= 449, ours 270;
  - indoor leak detection incl. technician: >= 707, ours 560;
  - spalled plaster removal: >= 314, ours 160;
  - drying: >= 233, ours 120;
  - vehicle costs: >= 60, ours 18;
  - disposal of insulation: >= 136, ours 50.
- **Generous on goods (too high).** The market prices current street prices of a standard model:
  - TV: market [517, 616), ours 950;
  - laptop: [1220, 1472), ours 1700;
  - bike frame: [142, 349), ours 500;
  - scaffolding: [510, 694), ours 1000.
- **Double counting on itemised invoices.** When labour has its own line, the market's material line is materials only.
  - g32: base plaster [35, 41), ours 200; plastered substrate [25, 37), ours 150; paint [41, 81), ours 300 (painter hours
    are a separate line).
  - g21: dryer hire [20, 65), ours 220; room drying [20, 148), ours 310.
  - g14: glass fitting [23, 26), ours 65.
- **Bulk hours priced at the premium rate (too high).**
  - g21: 14 technician hours, market [622, 680), which is 44-49 EUR/h gross. Ours 1125, which is 80 EUR/h.
- **Policy cuts applied inside the line price (too low).**
  - g17: our sources applied a "50% cut" on 4 lines; all 4 are below lo (F about 0.5 x t).
  - g21.17: the table was billed at 440 net; market t = 524-527, exactly 440 x 1.19. Ours 340.

**d. Implied market rates (gross). Mid-market German, not premium Munich.**
- Senior installer, 3 h: lo 274 / 279 / 288 in three games, so >= 91-96 EUR/h (about 78-81 net). This is a normal German
  plumbing/heating (SHK) rate.
- Measurement technician: >= 96 EUR/h.
- Painter: 52-56 EUR/h.
- Service technician (14 h): 44-49 EUR/h.
- Locksmith skilled worker hour: 35-42; apprentice hour: below 18 on the bike/locksmith invoices.
- Vehicle costs: 13 to 83+ per attendance.
- Filling valve: 48-55. Connection hose: 25-33. Sundries: under 4-11.
- Leak-detection / assessment flat rates: 449-707+.

So real German rates fit the technical trades, but simple trades, apprentices and sundries sit at or below the low end.

**e. The six sources share the same errors.** Pairwise correlation of log(F/lo) across the 6 sources, on 81 common
lines: median **0.92** (min 0.88). Fable vs Opus: 0.88-0.94.
- All sources are low on call-outs (0.88-0.97).
- Fable and v2 Opus run high on hours (1.09-1.11).
- No source differs in kind.

## 2. System prompt (both Fable and Opus; about 480 words)

This replaces the first paragraph of `build_prompt()`. The `<case>` block, image note and schema stay unchanged.

```
You are a German master tradesperson and cost estimator (Kalkulator). Every day you write and check repair invoices for
a typical, reputable mid-market firm in a large German city. You are NOT a claims adjuster: you do not look for reasons
to cut. You reconstruct what an honest firm actually bills for each invoice line, at normal market prices. You also
spot when a line would be overpriced.

For each invoice line (index = position on the invoice, starting at 1):
1. Read exactly what is billed: the quantity and unit on the invoice (hours, pcs, m2, days, flat rate) and the trade.
   Honour the quantity. A flat rate is one complete job.
2. Build the price bottom-up. Add hours x hourly rate, call-out, materials at wholesale list price plus the usual 15-25%
   contractor markup, equipment hire per day, and disposal per load. Then add 19% VAT. Report the GROSS line total.
3. Price only what this line contains. If labour is billed on its own line, a material line is materials only. An
   equipment-hire line is the hire only. Never double count work that appears on another line.
4. Price the line, not the claim. Do not apply percentage cuts, co-payments, deductibles, depreciation or
   negligence reductions inside the price. Apply only an explicit maximum amount for that item ("limited to EUR X",
   "equivalent standard model"). Put coverage questions into `covered`/`related` only.

Typical German net rates (before VAT, 2025/26). Pick inside the band from the trade and the job:
- Hourly: master/senior technical trade (plumbing, heating, electrical, leak detection) 70-95 EUR. Journeyman or
  service technician 45-75. Painter, plasterer, carpenter 45-60. Simple trades, workshop and bike work 30-50. Helper or
  apprentice 15-35. For long jobs (8+ hours) use the lower half: firms bill bulk hours at their base rate.
- Call-out / vehicle per attendance: 10-35 for a nearby simple trade, 35-75 for a plumbing, leak-detection or drying
  firm. Emergency or out-of-hours is higher.
- Specialist services are not cheap: leak detection (thermal, acoustic, tracer gas) 250-600 per job, moisture
  measurement 80-200, technical drying of a room over 1-3 weeks 200-800 incl. units, damage assessment flat rate
  350-550.
- Equipment hire: dryer/dehumidifier 5-25 per day. Scaffolding 8-15 per m2 facade incl. the standard hire period.
- Disposal: a small single item or a few bags 20-60, a car-boot to van load of mixed waste 60-200.
- Small parts: fittings, valves, hoses 15-50. Sundries and cleaning material 3-15. Materials for a small patch repair
  (plaster, primer, paint) 20-80.
- Goods (TVs, laptops, bikes, furniture): the current German street price of an equivalent standard model (typical
  online-retailer price). Not the original premium model, not the manufacturer's list price, not a used price.

Calibrate both ways. Real firms bill specialist services, call-outs and disposal at full rates, so do not shave them.
Real market prices for goods, bulk hours and itemised materials are lower than a generous guess, so do not pad them.

Output per line: `fair_gross_total` = what the honest firm's invoice shows for this line. `low` = a price you are
confident the honest invoice is at least: the cheapest honest competitor, not a frugal guess. `high` = the top of the
normal market range, not a rip-off. Uncovered or unrelated lines still get their market price. Return exactly one
entry per invoice line, in invoice order.
```

**Feedback after each case, for `v2_train.py`-style sessions (leakage-free: only the case just finished).**
- Use `feedback_line` as today, but judge `fair_gross_total` instead of `low`.
- When the description has an explicit quantity (`(\d+(\.\d+)?) ?(h|hrs|hours)`, `x(\d+)`, `(\d+) pcs`), append the
  implied unit price. Example: `line 3 (Senior installer hours, 3 h): proven fair >= 288 -> >= 96 EUR/h gross`.
- Replace `GOAL` with:

  > Your fair_gross_total should match what an honest German firm bills: below the proven-fair charge means you were
  > too frugal for that kind of line, at or above the lowest rejected charge means you padded it. Update your
  > per-trade rates, not a global level.

The bands in the prompt are general German market knowledge, not fitted to game bounds.
- **Leakage caveat:** I wrote them after seeing the g1-35 bounds. Two choices lean on what this analysis found: the low
  end of the simple-trade and apprentice bands, and "standard model". So backtests on g1-35 are optimistic. **The clean
  test is games 36+.**

## 3. Why it should differ, expected effect, risks

**Decorrelation.** The current prompt asks for one holistic number from an adjuster's view. This prompt forces a
quantity x rate + markup + VAT build-up, explicit itemisation, and no policy cuts inside lines. Its errors should then
come from rate choice and quantity reading, not from "gut feel" pricing. That is the mechanism that drives the 0.92
error correlation.

**Expected direction by line type (from section 1c):**
- Up: call-outs, specialist flat rates, disposal, and lines with a policy cut. The cut lines are where F < lo
  concentrates.
- Down: goods replacement, itemised materials, bulk hours. These carry 9.1K of the 11.1K inflated EUR.
- Net level about unchanged.
- Target: certainly-inflated share at or below today's 28%; certainly-too-low share 47% -> about 35%.

**Risks.**
1. **Overpricing loses whole lines.** Each +10% uniform shift moves about 10 pp of covered lines into "certainly
   inflated" (1b). The prompt has to stay two-sided ("do not pad").
2. **Real rates exceed this market for simple trades.** On the 21 upper-bound-only lines (locksmith and bike hours,
   apprentice, vehicle, sundries), F is already >= hi on 21/21. If the model reaches for "Munich" rates there, it gets
   worse.
3. **"No cuts inside lines" is supported by only 5 lines (g17, g21.17).** g31.3 shows caps do apply, which is why the
   prompt keeps explicit EUR caps. If the market applies percentage cuts in other games, those lines become inflated.
   Watch lines where the policy has a percentage reduction.
4. **Fable runs about 5-10% higher on hours than Opus already.** If the new group runs high overall, weight the Opus
   member or let the judge see it.

## 4. How to check after the runs

Measure on g36+ first (clean), then g1-35 (optimistic). Compare the new 3 sources with the current 6.
1. **Accuracy vs bounds, per source and per line type:**
   - share F < lo;
   - share F >= hi on two-sided lines, and on upper-bound-only covered lines;
   - interval-censored log-sd of t/F (`a3.py`). Target below 0.74.
2. **Guardrail:** the share of covered lines with F >= hi must not exceed the current pool's (28%) by more than 5 pp,
   and EUR on inflated lines must not rise.
3. **Decorrelation:** pairwise correlation of log(F/lo) between new and old sources on common lines (`a7.py`). It must
   be clearly below 0.92 (target < 0.8), or adding the group adds little information.
4. **Money:** walk-forward replay of `formula.py` with k refit on games < g:
   - median of 6 vs median of 9;
   - median of 6 vs a new-group-only median.
   Report worst..best and the number of games better/worse. Also check the ~10 large lines from s4-imitate-404
   (g6.1, g17.3, g21.4, g33.1, ...). Does the new group land inside [lo, hi) more often there?
5. **Per line type:** F/lo for call-outs should move from about 0.92 up to about 1.0. Goods and itemised materials
   should move down. If both move up together, the prompt is acting as a level shift and should be toned down.
