# Lines our sources call not covered, or split (research agent 6)

Data: 201 invoice lines in games 1-29 (tx_cache), 6 sources per line (v1 opus-1..3 + v2 fable-1, opus-1, opus-2).
A source votes "no" if `covered` or `related` is false. Votes come in only three shapes: **6/6 yes: 95 lines,
6/6 no: 101 lines, split (3 or 4 of 6 no): 5 lines**. No line has 1, 2 or 5 "no" votes.
Scripts: `build.py` (dataset), `analyze.py` (all numbers below, output in `results.txt`), `formula_check.py`.
Money: "pess" counts only acceptances the market proves (a <= the reviewer's highest accepted charge on that line).
"opt" also counts acceptances it cannot rule out. In games 23+ nearly every charge was hidden (rejected by all), so
"opt" is far too generous there. Treat pess as the realistic number.

## Recommended policy
| votes | charge a | limit b |
|---|---|---|
| 6/6 (or >= 5/6) not covered/related | **0** (honest); if the team wants the free option, 0.9 x median non-zero fair | **0** |
| split (1-4 of 6 say no) | treat as covered: the normal covered formula on the non-zero fairs | normal covered rule (1.04 x lowest non-zero fair) |

Make this an explicit guard. Today the live `formula.py` only gets b = 0 on such lines by accident: b = 1.04 x min(fair),
which is 0 only because some source writes fair = 0. In the training answers, v2 sources give a non-zero fair on 280 of
309 "not covered" answers. If all 6 sources give one, b > 0 and the 1.5x lesson below applies.
The formula also charges a = k x median fair > 0 on all 101 of these lines, so the "free option" is already on in practice.

## (3) Were our coverage votes right? (market bounds lo/hi)
- **6/6 not covered (101 lines):** t > 0 proven on **2 (2%)**, both in game 21: l5, a second travel charge with
  lo = 76.5; and l12, a "duplicate" of pos. 8 with lo = 49.4. t <= 0.2 x fair proven: 28. t < 0.23-0.75 x fair: 28.
  No bound: 43 lines where every charge was rejected by every team, which fits t = 0. Net: the votes are about 98% right.
- **Split (5 lines: game 14 l1-l4, game 21 l13):** **t > 0 proven on 5/5.** The "no" voters were wrong every time. These
  lines are covered, sometimes at a discount (game 14 glazing: lo = 0.36-0.64 x fair; l1 lo = 64 > fair 25).
- The reverse error is absent too: 0 of the 95 lines voted 6/6 covered have t <= 0.2 x fair proven.

## (1) Money from charging on 6/6 lines (FDN as issuer, others unchanged)
| a = | games 1-29, in-sample pess (opt) | games 25-29 |
|---|---|---|
| 0.92 x median fair (best) | 5,473 (141K) | **0** |
| 0.5 x fair | 4,189 | 0 |
| 0.25 x fair | 2,399 | 0 |
| 1.0 x high | 984 | 0 |
| flat 10 EUR | 960 | 10 |
- **Walk-forward** (pick best on games < g): **+4,529** pess. **Hold-out** (fit 1-24 -> 0.92 x fair, test 25-29): **0** pess.
- Over time: the money came almost entirely from games 10-22 (games 21-22 alone: 3.2K at 1.0 x fair).
  Since game 23 the market sets b = 0 on these lines. All 12 teams together earned **1,074 EUR** on 28 such lines in
  games 23-29 (Kiebler 600, Lumenauts 400, FDN 74), all from one line (game 28 l1, an AC unit, 404 accepted).
- **Who paid** (share of known positive charges they accepted on 6/6 lines, games 1-16 / 17-22 / 23-29):
  vietgang 77% / 44% / 0%; Lumenauts 13% / 39% / 0%; Humble Legends 10% / 22% / 0%; CHOOMS 16% / 16% / 0%;
  chineseModels 0% / 25% / 0%; alpha 0% / 11% / 0%. Asgardians, Kiebler, 404 and GemischtesHack were close to 0% in every period.
  At a = 0.5 x fair, the money we would have earned came from vietgang 1.0K, Lumenauts 0.8K, CHOOMS 0.6K,
  Humble Legends 0.6K, alpha 0.4K, TRINNERS 0.3K. Everyone else paid < 0.25K.

## (2) Acceptance limit on 6/6 lines (insurer cost, lower is better)
| b = | cost games 1-29 pess..opt | games 25-29 |
|---|---|---|
| **0** | **860** (two certain 1.5x penalties, game 21 l5 521 + l12 339) | 0 |
| flat 5 / 10 / 20 | 873..3,783 / 1,091..6,911 / 1,694..13,334 | 0..815 / 0..1,630 / 0..3,260 |
| 0.25 x min fair | 2,432..26,142 | 1,000..15,666 |
| 1.04 x min fair (the covered rule) | 9,837..108,472 | 1,000..62,008 |
- **Walk-forward picks b = 0 in 21/21 games.** The 1.5x penalty risk (2% of lines, 860 EUR in total) is far smaller
  than what any positive limit pays out to inflated charges. **b = 0 is right; no multiple helps.**
- Split lines: b = 0 costs 1,305 vs 1,266..1,405 for the covered rule (about equal). But charging them as covered
  (a = 0.92 x median non-zero fair) earns **+1,078..2,551** vs 0. Treating split lines as covered is worth about +1.1K over 5 lines (small sample).
- FDN's actual result on these lines: 6/6 lines net **-1,752** (earned 74, paid 1,825: accepted others' charges in early
  games, plus the game 21 penalties). Split lines net **-556**. The policy above would have made about -860 and +1.1K.

## (4) What other teams do on 6/6 lines (whole tournament)
| team (total net) | lines charged >0 | median visible charge / fair | accepts | net on these lines |
|---|---|---|---|---|
| 404 (+120K) | 101/101 | 0.83 | 2% | +3,790 |
| TRINNERS (+39K) | 101/101 | 0.20 | 3% | +512 |
| Kiebler (+30K) | 101/101 | 0.55 | 0% | +5,318 |
| Humble Legends (+28K) | 101/101 | 0.82 | 15% | -2,563 |
| alpha (+22K) | 2/101 | 1.06 | 5% | -2,104 |
| FDN (+18K) | 1/101 | - | 2% | -1,752 |
| Asgardians (-26K) | 87/101 | 0.57 | 0% | +4,352 |
| vietgang (-150K) | 46/101 | 0.99 | 61% | -8,836 |
The top 3 charge on every uncovered line (about 0.2-0.8 x the covered price) and almost never accept: the free option
plus b = 0. But the gap is only ~4-7K over 29 games, out of a 100K gap between 404 and FDN. Uncovered lines do not explain why FDN earns less.

## Honesty / presentation (30% of score)
Charging a price on a line our own analysis calls "not covered" means knowingly sending an inflated bill. That is hard
to defend in a presentation that is scored on honesty and method. **EUR at stake:** in-sample at most 5.5K over 29
games (about 190/game), walk-forward 4.5K. In games 23-29 it is about 0 (pess 0 on the hold-out; the whole market
took 1.1K). Recommendation: **charge 0 and accept 0 on lines all sources call uncovered**, and say so in the method story.
The expected cost is about 0-100 EUR/game now. Keep the profitable, honest part instead: split votes count as covered
(+1.1K in sample), and b = 0 as an explicit rule (it avoided 9-108K of exposure in the replay).
If the team still wants the option value, 0.9 x median non-zero fair is the best level, framed as "the insurer decides
coverage". But the data says it now earns about nothing.
