# Opponents: what the top teams charge and accept (games 1-34)

Data: `live_eval/tx_cache.pkl` (g1-29) plus g30-34 fetched read-only from the public leaderboard (`tx_30_34.pkl`).
Net per team rebuilt from the transactions matches the leaderboard totals to within 0.1K (404 120.3K, Kiebler 82.0K,
TRINNERS 74.9K, FDN 61.2K). Notation: `lo`/`hi` = market bounds (lo <= t < hi); **P lines** = lo > 0 (106 lines);
**Z lines** = our sources say not covered (median fair = 0) and lo = 0 (123 lines). `F` = median of our sources' fair
value, counting 0 when a source says "not covered or not related" (6 sources g1-29, 3 sources g30-34). `Flow` = lowest
positive source fair. A team's charge comes from any reviewer that paid it. "Hidden" = rejected by every reviewer, so the
charge is unknown but inflated. A team's b is bracketed between the largest charge it accepted and the smallest known
charge it rejected. Scripts: `build.py` (reconstruction), `an1-5.py`. These are descriptive statistics over all games,
with nothing fitted, so the walk-forward rule does not apply. The "rules" in section 4 describe what teams did. They are
not tested strategies.

**Correction to the task list:** Asgardians (-62.5K), Humble Legends (-2.3K), GemischtesHack (+5.2K) and chineseModels
(+7.1K) are not top earners. The top 3 by total are **404, Kiebler Software Solutions and TRINNERS4WINNERS**. FDN is 4th.

## 1. Key findings

1. **404's whole lead comes from charging closer to t.** On P lines, 404's median charge is 0.95 x lo (IQR 0.86-1.00).
   FDN's is 0.74 x lo (IQR 0.44-0.98). Against our own estimate: 404 a ~ 0.99 x F, FDN a ~ 0.73 x F. Our F is not biased
   low over g1-34 (median F/lo = 1.02). FDN lowers an estimate that is already about right.
2. **Why a charge near t pays: 63% of 404's income is 1.5x penalties.** Most teams' b sits below t (every team rejects a
   proven-fair charge on 51-69% of P lines). So a fair charge just under t is usually rejected and paid 1.5x.
   - 404 wins 534 penalty payments (15.7 per game, 19.4% of the bills it issues).
   - FDN wins 360 (10.6 per game, 13.1%).
   - 404 sets the market's lo (it is the highest charge proven fair) on 20 of 106 P lines, more than any other team.
     FDN sets it on 7.
3. **Breakdown of the 59K gap between 404 and FDN (34 games):**
   - As issuer, 404 earns +44.1K more:
     - +33.4K from penalties on P lines;
     - +4.0K from accepted bills on P lines;
     - +6.1K from charging uncovered lines;
     - +0.7K from other lines.
   - As insurer, 404 pays 15.0K less. It accepts 66.7K less on P lines, but pays 52.0K more in penalties because its b is
     low. This is despite game 31, where its b <= 1440 on a line with t >= 2900 cost about 35K.
4. **Uncovered lines.** 404, Kiebler, TRINNERS and Humble Legends charge 100% of Z lines (medians 57 / 37 / 17 / 45 EUR)
   and accept almost none of them (b = 0). FDN charged 11% of Z lines. Income on Z lines: 404 7.1K, Kiebler 8.1K,
   FDN 1.0K. Most of these bills are hidden (rejected by everyone, so no loss). The income comes from the few teams with
   b > 0 there: Asgardians paid 22.3K on Z lines and vietgang paid 29% of the time.
5. **Our charges are not noisier than 404's.** On P lines where 404 did not set lo itself, the spread of its log(a/lo)
   (IQR/1.35) is 0.32, the same as our F's 0.31. Kiebler, TRINNERS and FDN are at 0.46-0.51. The only real difference is
   the level: 404 charges 0.93 x t on those lines, FDN 0.77 x t. We would not need a better estimator, only to shade it
   less.
6. **Over time:**
   - 404 is stable: a/lo 1.00, 0.95, 0.95, 0.92 across g1-9, g10-19, g20-29, g30-34.
   - Kiebler is the riser. Its a/lo went 0.67 (g10-19), then 0.82, then 0.94. Its rate of rejecting fair bills fell from
     77% to 48% to 33%. Its net went from -0.9K to +4.2K to +10.3K per game.
   - FDN in g30-34 has the same shape as Kiebler: a/lo 0.95 and fair-reject 33%, giving +8.6K per game (+4.1K excluding
     game 31).
   - Excluding game 31, per game in g30-34: 404 +8.0K, Kiebler +6.8K, GemischtesHack +4.9K, FDN +4.1K, TRINNERS +3.5K.
7. **Acceptance is the weaker lever, and its tail is dangerous.** Every team's b sits at about 0.83-0.94 x F
   (0.95-1.05 x Flow). The top teams do not have a much better b than ours. The big swings come from single large lines:
   - g31: 404 -31.9K and Humble Legends -28.8K, each from rejecting 2900 EUR fair bills;
   - g29: Asgardians -18.8K;
   - g21: GemischtesHack -15.8K.
   Kiebler's b is generous (it rejects fair bills on only 51% of P lines, the lowest of any team). It paid the least in
   penalties (70.2K) but the most for accepted bills (138K). Its net as insurer is about the same as 404's.

## 2. Per-team table (games 1-34)

The columns are:
- **Net/game**: net per game in g1-29, then g30-34 excluding game 31.
- **Earned / of which 1.5x**: issuer income, and the part of it that came from 1.5x penalties.
- **Paid (acc / pen)**: insurer payments, split into accepted bills and penalties.
- **1.5x wins/g**: penalty payments won per game.
- **a/lo, a/F, a/Flow**: median charge on P lines, divided by lo, by our median fair F and by our lowest fair Flow.
- **Z charge**: share of uncovered lines charged, and the median charge there.
- **rej fair %**: share of P lines where the team rejected a proven-fair charge.
- **acc infl %**: share of lines with a known hi where the team accepted a charge at or above hi.
- **b/F**: median bracket for b.

| Team | Net total | Net/game (g1-29 / g30-34 ex31) | Earned (of which 1.5x) | Paid (acc / pen) | 1.5x wins/g | a/lo (IQR) | a/F | a/Flow | Z charge | rej fair % | acc infl % | b/F |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 404 | **+120.3K** | +4.1K / +8.0K | 322.4K (202.3K, 63%) | 202.1K (71.9 / 130.3) | 15.7 | 0.95 (0.86-1.00) | 0.99 | 1.17 | 100%, 57 EUR | 58 | 24 | 0.84-0.89 |
| Kiebler | +82.0K | +1.0K / +6.8K | 302.3K (182.5K, 60%) | 220.3K (150.1 / 70.2) | 11.7 | 0.85 (0.55-1.00) | 0.89 | 0.97 | 100%, 37 EUR | 51 | 34 | 0.92-0.94 |
| TRINNERS4WINNERS | +74.9K | +1.3K / +3.5K | 292.7K (168.7K, 58%) | 217.9K (94.0 / 123.9) | 10.9 | 0.93 (0.63-1.20) | 0.96 | 1.11 | 100%, 17 EUR | 66 | 30 | 0.83-0.90 |
| **FDN** | +61.2K | +0.6K / +4.1K | 278.3K (168.9K, 61%) | 217.1K (138.8 / 78.3) | 10.6 | **0.74** (0.44-0.98) | **0.73** | 0.90 | **11%**, 30 EUR | 58 | 30 | 0.88-1.02 |
| alpha | +8.6K | +0.8K / -5.0K | 246.1K (114.7K) | 237.5K (130.4 / 107.1) | 8.0 | 0.72 (0.50-1.26) | 0.81 | 0.95 | 2% | 57 | 39 | 0.90-1.00 |
| chineseModels | +7.1K | +0.1K / +0.5K | 245.7K (116.9K) | 238.6K (103.6 / 135.0) | 9.8 | 0.92 (0.67-1.16) | 1.00 | 1.14 | 98%, 45 EUR | 58 | 37 | 0.90-0.98 |
| GemischtesHack | +5.2K | -0.9K / +4.9K | 229.2K (116.1K) | 223.9K (86.0 / 137.9) | 9.7 | 0.86 (0.38-1.00) | 0.87 | 0.94 | 89%, 35 EUR | 67 | 23 | 0.72-0.91 |
| Humble Legends | -2.3K | +1.0K / -0.3K | 238.1K (134.6K) | 240.4K (121.6 / 118.9) | 10.7 | 1.00 (0.71-1.28) | 1.03 | 1.15 | 100%, 45 EUR | 56 | 37 | 0.89-0.96 |
| CHOOMS | -16.3K | -0.6K / +3.3K | 234.5K (134.3K) | 250.8K (136.2 / 114.6) | 10.9 | 0.96 (0.65-1.35) | 0.95 | 1.08 | 90%, 48 EUR | 53 | 38 | 0.85-0.92 |
| Lumenauts | -49.0K | -1.4K / -0.1K | 199.2K (76.1K) | 248.2K (78.0 / 170.2) | 6.6 | 0.67 (0.47-1.00) | 0.77 | 0.87 | 79%, 41 EUR | 69 | 38 | 0.68-0.80 |
| Asgardians | -62.5K | -0.9K / -13.8K | 207.4K (116.4K) | 269.8K (146.8 / 123.0) | 7.9 | 0.65 (0.10-0.94) | 0.95 | 1.03 | 76%, 31 EUR | 58 | 43 | 0.88-0.91 |
| vietgang | -229.3K | -5.2K / -11.8K | 31.5K (6.4K) | 260.7K (32.3 / 228.4) | 1.2 | 0.00 (mostly hidden) | 0.60 | 0.68 | 37% | 91 | 32 | 0.00-0.55 |

### How these columns changed over time

| Team | a/lo by period (g1-9, g10-19, g20-29, g30-34) | rej fair % by period |
|---|---|---|
| 404 | 1.00, 0.95, 0.95, 0.92 | 64, 62, 48, 71 |
| Kiebler | 0.90, 0.67, 0.82, 0.94 | 43, 77, 48, 33 |
| TRINNERS4WINNERS | 0.82, 1.00, 0.99, 0.90 | 71, 69, 62, 67 |
| FDN | 0.78, 0.54, 0.64, 0.95 | 57, 77, 60, 33 |

Two more changes over time:
- In g1-9, 404 and TRINNERS often set b near 0 on covered lines (their b_lo/F was 0.26 and 0.07). From g10 on, both
  moved to about 0.75-1.0 x F.
- In g32, 404 charged a flat 300 EUR on 7 lines, which looks like a fallback or a bug. It still netted +11.1K that
  game.

## 3. In plain terms: what the top teams do differently from FDN

- **They charge our own fair estimate, not 0.73 times it.** 404 and TRINNERS charge about 1.0 x F, Kiebler about
  0.9 x F. Since about 60% of P-line charges near t are rejected and paid 1.5x, each euro of shading costs about 1.3 EUR.
  This accounts for 37K of the 44K issuer gap with 404.
- **They bill every line, including the ones they think are uncovered.** Flat charges of 20-60 EUR with b = 0. This costs
  nothing and has earned 6-8K each. FDN earned 1.0K.
- **They do not win by accepting better.** b is about 0.85-0.95 x F everywhere. Kiebler accepts generously (fewest
  penalties paid), while 404 and TRINNERS accept tightly (fewest inflated bills accepted, at 9.5K and 24.7K). Both
  approaches end with similar insurer cost. The real risk is a single large line with b far below t (404 in g31).

## 4. Pricing rules inferred for the top 3

These describe observed behaviour, written relative to our estimates. F = median source fair, Flow = lowest positive
source fair, lo = market-proven fair (known only afterwards). Numbers are medians over g1-34 with IQR in brackets.

**404**
- Covered line: `a = 0.99 x F` (IQR 0.76-1.40 x F) = `1.17 x Flow`. Relative to the hidden t this is about
  `a = 0.95 x t` (IQR 0.86-1.00). 74% of its P-line charges are proven fair and 26% are at or above hi.
- Uncovered line: `a = 57 EUR` flat, `b = 0` (it accepts a charge on 3% of Z lines).
- Acceptance: `b = 0.87 x F` (bracket 0.84-0.89 x F, about 0.9 x lo). It rejects a fair bill on 58% of P lines and
  accepts an inflated one on 24%.

**Kiebler Software Solutions** (as of g20-34, when it rose)
- Covered line: `a = 0.89 x F = 0.97 x Flow`. It has risen to about `0.94 x t` in g30-34.
- Uncovered line: `a = 37 EUR` flat, `b = 0` (never accepted a charge on a Z line).
- Acceptance: `b = 0.93 x F = 1.0-1.05 x Flow`, the most generous. Fair-reject rate is 33% in g30-34, and it paid the
  fewest penalties (70.2K).

**TRINNERS4WINNERS**
- Covered line: `a = 0.96 x F` (IQR 0.78-1.42) = `1.11 x Flow`, about `0.93 x t`. Its charges are the noisiest of the
  top three: 40% are at or above hi.
- Uncovered line: `a = 17 EUR` flat, `b = 0`.
- Acceptance: `b = 0.87 x F` (bracket 0.83-0.90) = `0.96-1.03 x Flow`.

**FDN for comparison (all games):** a = 0.73 x F (0.90 x Flow); 0 on 89% of uncovered lines; b about 0.88-1.02 x F.

Implications for our formula:
- Our live rule's k = 0.84-0.92 x F is already close to Kiebler and 404 on covered lines.
- The cheapest additions are a flat 30-50 EUR charge on lines we judge uncovered (keeping b = 0), and a guard against
  b far below F on large lines.
- None of this has been run through the replay walk-forward. Do that before adopting it.
