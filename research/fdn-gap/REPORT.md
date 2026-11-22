# Why FDN earns less than the top teams — leak decomposition (games 1-29)

Scripts: `decomp.py` (per-line decomposition -> `rows.json`), `analyze.py` (-> `tables.md`), `leak2.py` (-> `tables2.md`).
Read-only; no submissions, no model calls. Formula = `formula.py` on the 6 pooled sources (v1 opus-1..3 + v2 fable-1, opus-1, opus-2),
replayed with `fable_vs_opus.replay` logic (my per-line sums reproduce `replay` exactly: net_lo 83,872 / net_hi 298,509).
**The formula numbers are IN-SAMPLE** (formula was fitted on 1-29); "pess" = replay lower bound, "opt" = upper bound.
Top 3 by real cumulative net in the tx cache (1-29): 404 (+120.2K), TRINNERS4WINNERS (+39.0K), Kiebler (+30.3K).

Leak definitions (market-proven oracle, conservative):
- *issuer leak* = income if we had charged a = lo (highest charge proven fair) minus actual income (lines with lo > 0 only).
- *penalty leak* = the extra 0.5a paid on fair bills we rejected. *inflated leak* = amount paid on accepted inflated bills
  (formula pess also counts hidden all-rejected charges at our b).

## 1. The bridge (EUR, games 1-29)
| | net | issuer income | of which 1.5x wins | acc. inflated (lax insurers) | insurer paid | paid fair | 1.5x penalties paid | paid inflated | issuer leak | pen leak | infl leak |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FDN actual | 18,369 | 175,632 | 94,472 | 25,139 | 157,265 | 57,851 | 71,154 | 27,958 | 155,694 | 23,718 | 27,958 |
| Formula pess | 83,871 | 227,498 | 126,107 | 32,585 | 143,627 | 73,560 | 47,429 | 22,123 | 109,328 | 15,916 | 22,123 |
| Formula opt | 298,508 | 428,793 | 158,530 | 52,293 | — | | 47,429 | 9,101 | 70,328 | 15,810 | 9,101 |
| 404 | 120,170 | 256,988 | 162,999 | 31,830 | 136,818 | 46,337 | 81,518 | 8,768 | 81,351 | 27,173 | 8,768 |
| TRINNERS4WINNERS | 38,976 | 197,045 | 105,517 | 38,515 | 158,069 | 40,360 | 97,044 | 20,529 | 136,145 | 32,348 | 20,529 |
| Kiebler | 30,306 | 200,130 | 111,575 | 33,080 | 169,824 | 63,911 | 60,583 | 45,028 | 138,851 | 20,194 | 45,028 |

**FDN vs 404 gap = 101.8K = 81.4K issuer side (68.5K of it fewer 1.5x wins) + 20.4K insurer side (19.2K more inflated bills accepted;
404 actually pays 10.4K MORE penalties — it is a strict insurer and still wins).** 80% of the gap is *charging too low*.
404's recipe: charges at 0.8-1.0 x lo on 45 of 82 covered lines, never below 0.5 lo, never 0; rejects aggressively.

Formula pess vs 404: -36.3K (issuer -29.5K, insurer +6.8K of which 13.0K is hidden-charge worst case).
The formula's optimistic +298K is mostly an artifact: 175K "accepted-unknown" income comes from 43 lines where every team
charged 0 (t probably 0, all charges rejected); the replay can't tell whether reviewers would accept. Trust the pess number.

## 2. Ranked leaks (EUR, in-sample; "worth" = gap to the market-proven oracle, an upper bound on what a fix recovers)
| # | leak | FDN actual | formula (pess) | status | evidence | fix |
|---|---|---|---|---|---|---|
| 1 | **Deep undercharge on covered lines, a < 0.5 lo** | 69.6K (16 lines) | 17.6K (9) | mostly FIXED (-52K) | g5 L1 vehicle a=24 vs lo 1,166 (17.2K); g29 L1 a=496 vs lo 1,532 (16.5K); g17 L3, g21 L2/L17 | formula's median x k already; remaining 9 lines are model estimates < 0.5 lo (see #3) |
| 2 | **Moderate undercharge, a in 0.5-0.97 lo** | 49.9K (37) | **52.7K (42)** | REMAINS — biggest live leak | k = 0.84/0.92 applied to estimates that are already 20-40% low; labour 23.0K, parts 64.8K (all buckets) | raise a on covered labour/parts toward lo — but k is at a cliff; needs a better anchor (past market lo for same policy/category), not a global k bump |
| 3 | **Model estimate < 0.7 lo (estimate error)** | net -6.4K, leak 38.4K+6.8K pen | net **-4.0K**, leak 34.5K + 7.3K pen (18 lines) | REMAINS | on these lines the formula undercharges AND sets b below the fair bills (b=1.04 x min fair) -> pays 1.5x; 404 nets +18.8K on the same lines | estimate quality (labour rates, plumbing/parts); a pure multiplier can't fix it |
| 4 | **No charge on market-covered lines** | 26.2K (12 lines: g1 L1 11.3K, g19 L1 3.7K, g11 L5 3.6K, g24, g14) | 0 | FIXED | FDN submitted 0 where models/decider said uncovered | formula charges every line |
| 5 | **Accepted inflated bills** | 28.0K | 9.1K known + 13.0K hidden worst | mostly FIXED | FDN: g24 L1 5.6K, g1 L1 5.7K, g21 L4 2.6K. Formula: 30 lines with b >= hi (models over market) -> 12.8K, g21 L4 b=988 vs hi 680 (4.5K) | cap b at past market hi for same policy/line where known; b on "med >= hi" lines |
| 6 | **1.5x penalties (rejecting fair bills)**, extra 0.5a | 23.7K | 15.9K (15.1K on 47 lines with b < lo) | partly FIXED (-7.8K) | b = 1.04 x min fair sits below lo whenever one source is low | trade-off with #5; 404 accepts 27.2K of this leak and is still best -> do NOT raise b globally |
| 7 | **Charge in (lo, hi), never tested** | 0 | 25.4K pess / -10.6K opt (10 lines) | uncertainty, not a leak | formula's a above every fair charge seen | none needed; mid-range leak ~7.4K |
| 8 | **Overcharge a >= hi (rejected, 0 earned)** | 8.2K (13) | 9.1K (15) | REMAINS (small) | g24 L1 FDN a=996 vs hi 349; formula g21 L4 a=1,035 vs hi 680 | the "disagree" k = 1.16 tier on high medians; 404 loses 18.9K here too |

By game, the FDN leak concentrates in g21 (38.0K), g29 (22.8K), g5 (20.3K), g1 (18.0K), g24 (13.2K), g17 (13.6K), g20 (12.1K), g27 (11.5K):
these 8 games = 150K of FDN's 207K total leak; the formula cuts g29 22.8->5.3K, g5 20.3->2.1K, g1 18.0->3.7K, g24 13.2->4.3K but
leaves g21 at 40.1K (27.3K undercharge on 22 lines, b>=hi on L4) and g17 at 14.4K.
Top 25 FDN leak lines = 159.5K of 207.4K; the formula still leaks 98.3K on those same 25 lines.

## 3. By category / coverage / value (FDN actual -> formula pess, net)
- parts/repair (114 lines): 6.8K -> 45.9K (404: 81.2K) — largest remaining gap (64.8K undercharge leak).
- labour (25): 10.7K -> 18.1K (404 16.5K); vehicle (24): -10.5K -> 9.5K (fixed, was g5 L1); fee (11): 9.0K -> 6.4K (formula worse: g7 fee).
- market-covered lines (82) carry ~all the leak: FDN 15.7K, formula 74.9K, 404 112.7K. Uncovered/unknown lines: ~0 for everyone.
- Value >= 400 EUR (26 lines): FDN 18.5K, formula 66.2K, 404 75.2K; 80-400 EUR (70 lines): FDN 1.9K, formula 13.9K, 404 31.1K -> mid-value parts lines are where 404 still beats the formula by 17K.

## 4. Bottom line
- FDN's real shortfall is ~80% issuer-side: charging far below proven-fair levels (or 0) forfeits both the accepted amount and the 1.5x
  wins from strict insurers. The formula already fixes the catastrophic cases (#1, #4, most of #5): +65.5K in-sample (pess).
- Remaining recoverable (formula pess, upper bounds): moderate undercharge 52.7K, estimate-error lines 34.5K+7.3K (overlap with #2),
  b < lo penalties 15.1K, b >= hi inflated 12.8K, overcharge 9.1K. Realistic next fix: a market-anchored charge for repeated
  policies/categories (covered parts/labour) rather than a higher global k (cliff risk documented in BRIEF). Not walk-forward tested here.
