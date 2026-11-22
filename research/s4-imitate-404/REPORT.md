# Imitating team 404 with our own model numbers (games 1-35)

**Data.** Transactions: `live_eval/tx_cache.pkl` (g1-29), `research/opponents/tx_30_34.pkl` (g30-34), and g35 fetched read-only into
`tx_35.pkl`. Our features pool the v1 3x Opus sources with the v2 Fable + 2 Opus sources. That gives 6 sources for g1-29 and g34-35,
and only 3 for g30-33, because v1 has no answers there. Gemini sources are excluded.

**Method.**
- 404's charge `a` is recovered from any reviewer that paid it. A charge rejected by every reviewer is "hidden": it was inflated
  and its size is unknown.
- 404's `b` is bracketed as [largest charge it accepted, smallest known charge it rejected).
- My per-line replay (`lib.py`) matches `fable_vs_opus.replay` exactly on g5, g17 and g29.
- Every number below is walk-forward (fit on games < g, test on g, g >= 6) or hold-out (HO: fit g1-24, test g25-35), unless it is
  labelled in-sample. Net figures are worst..best case.

**Scripts.**
- `build.py`: builds the per-line dataset.
- `explore*.py`: describes 404's behaviour.
- `fit.py`, `run_a.py`, `run_b.py`, `final.py`: the imitation fits.
- `payoff.py`, `pergame.py`, `elements.py`, `toplines.py`, `ex31.py`: replayed payoffs.

## 1. 404's policy in plain words

**Charges.** 404 charges every line, about at the market's proven-fair level.
- On covered lines, the median a/lo is 0.97 (IQR 0.86-1.00). This is stable across games: 1.00, 0.98, 1.00 and 0.92 in g1-12,
  g13-24, g25-29 and g30-35.
- On 103 covered lines with a known lo:
  - 75 charges are proven fair;
  - 404 itself sets lo on 20 of them;
  - 44 charges are proven inflated (a >= hi).
- Measured against our median fair F, a/F = 0.98 on lines all our sources call covered. So "a ≈ 0.99 x fair" is true in the median.
- The spread is wide (IQR 0.76-1.35), and the ratio depends strongly on the line's value:

  | Value tier (our F) | 404 a / our F |
  |---|---|
  | < 50 EUR | 1.54 |
  | 50-200 EUR | 1.07 |
  | 200-1000 EUR | 0.82 |
  | >= 1000 EUR | 0.62 |

- The reason is that 404 is roughly flat against the market at every value, while our F is not. Our F/lo is 1.39 on lines of
  1000 EUR or more (too high). On lines under 50 EUR, 404 overcharges (a/lo up to 1.8).
- No category or agreement tier explains much once value is accounted for.

**Uncovered lines** (fewer than half our sources say covered; 128 lines):
- 404 charges all of them.
- 94 of those charges are hidden (rejected by everyone).
- The visible ones are small: median 57 EUR (IQR 45-146), about 1.4x our raw fair.
- It accepts nothing there (b ≈ 0 on 121 of 128 lines).

**Acceptance limit b on covered lines.**
- b is about 0.97 x our lowest fair, or about 0.85 x our median: the medians of the bracket are 0.94-1.00 x min fair.
- b is almost never 0 on covered lines (1 of 124).
- On lines of 1000 EUR or more, b is far below the market: 0.3-0.6 x lo. That is how 404 lost 31.9K in g31 (b <= 1440 on a line
  with t >= 2900). 404 also charged that line 0.
- b changed over time: low in g1-12 (0.62 x min fair), generous in g13-24 (1.2-1.4x), back to about 0.8x in g30-35.

## 2. Best imitation formulas and how accurate they are

Each formula is a power law fitted on log(x+1), with a coverage gate. The values below are in-sample on g1-35; the walk-forward
refits are close.

**Imitation A** (best balance):
- Charge, covered lines (pcov >= 0.5): a = 2.450·(mean_fair+1)^0.818 − 1.
- Charge, uncovered lines: a = 3.309·(mean_fair+1)^0.763 − 1.
- Acceptance: b = 2.363·(median_fair+1)^0.80 − 1 if pcov >= 0.5, else b = 0.

**Imitation B** (most accurate charge):
- a = 1.894·(max_fair+1)^0.832 − 1.
- b = 3.597·(min_fair+1)^0.74 − 1 if pcov >= 0.5, else b = 0.

In words, on a covered line where our fair estimate is F, Imitation A's charge is about:

| F | Charge a | a / F |
|---|---|---|
| 20 | 29 | 1.43x |
| 100 | 106 | 1.06x |
| 300 | 260 | 0.87x |
| 1000 | 697 | 0.70x |
| 3000 | 1713 | 0.57x |

The acceptance limit shrinks with F the same way, from 1.66x at F = 20 to 0.45x at F = 3000.

**Accuracy, walk-forward, covered lines.** "Within ±10%" for b means within 10% of 404's bracket.

| Formula | Charge: median abs error | Charge: within ±10% | b: inside 404's bracket | b: within ±10% |
|---|---|---|---|---|
| formula.py | x1.39 | 19% | 8% | 25% |
| Imitation A | x1.28 | 20% | 21% | 38% |
| Imitation B | x1.26 (HO x1.18) | 19% (HO 26%) | 29% | 38% |

Richer families did not imitate better walk-forward: per-category terms, the agreement tier (cv), spread, coverage share and
low/high all overfit. **Even the best formula misses 404's charge by about ±25% on a typical line.** Our numbers do not carry
404's information.

## 3. Replayed net for FDN (worst..best case)

| Strategy | Walk-forward g6-35 | g30-35 | HO g25-35 | g6-35 excl. g31 | g30-35 excl. g31 |
|---|---|---|---|---|---|
| **formula.py (live)** | **+74.3K..+290.3K** | **+19.5K..+35.2K** | +44.9K..+116.1K | +54.3K..+267.3K | −0.5K..+12.2K |
| Imitation A | +32.5K..+278.5K | +8.5K..+55.1K | +15.5K..+125.1K | +34.9K..+276.2K | +11.0K..+52.8K |
| Imitation B | +39.4K..+321.2K | +5.1K..+77.4K | +14.9K..+169.7K | +49.0K..+325.7K | +14.6K..+81.9K |
| 404's own (a, b) in FDN's seat | +57.7K..+126.9K | −3.0K..+26.6K | +0.8K..+39.4K | +85.9K..+154.4K | +25.3K..+54.1K |
| Actual net, 404 / FDN | +98.1K / +61.6K | +0.0K / +42.8K | | +129.9K / +35.0K | +31.9K / +16.2K |

formula.py's values were chosen on g1-29, so its g6-29 rows are in-sample. Its g30-35 rows are honest out-of-sample.

**Where 404's edge comes from** (g6-35 excl. g31, worst case):
- **Charges on covered lines: estimates, not reachable.**
  - 404's own charges earn 251.9K, formula.py's 208.5K and Imitation A's 203.8K.
  - So 404 is +43K ahead, and imitating its policy on our numbers recovers none of it (−4.7K).
  - The gap sits on about 10 large lines where our F was 30-80% off and 404 was close to t. These 10 lines account for +54K. Examples:
    - g33 line 1: ours 1700, t in [1220, 1472), 404 charged 1106;
    - g6 line 1: ours 1250, lo 744;
    - g21 line 4: ours 1125, t in [622, 680);
    - g17 line 3: ours 230, t >= 467.
- **Charges on uncovered lines: reachable, but tiny.**
  - 404 earns 8.4K there and formula.py 4.6K.
  - Grafting 404's rule onto formula.py ("charge at least 45-57 EUR, b = 0") adds only +0.1K to +0.7K worst case. It adds more in
    the best case.
  - formula.py's b is already about 0 on these lines, so setting b = 0 changes nothing.
- **Acceptance limit: 404's policy is worse than ours.**
  - formula.py's b pays 167K..182K over g6-35. 404's b in our seat pays 183K..205K.
  - The imitation b pays 193K..204K, so imitating 404's b costs about 22-26K.

**The one 404-like element with some recent signal** is compressing large lines (exponent about 0.8). It is why the imitations
beat formula.py on g30-35 excluding g31. That rests on single lines:
- g33: compressing gains about +15K;
- g31: compressing loses about −16K, because there our 3000 was right.

It does not hold up on g6-35 or the hold-out. I would not trust it without more data.

## 4. Recommendation

**Do not switch. Keep formula.py.**
- Every imitation formula is worse in the worst case on walk-forward g6-35 (by 35-42K) and on the hold-out (by about 30K).
- 404's lead over FDN came from two things:
  1. **Better estimates on a handful of big lines.** No formula on our numbers can reach these.
  2. **FDN's older under-charging rule** (a ≈ 0.73 x F). formula.py has already fixed this.
- 404's acceptance limit and its behaviour on uncovered lines are not better than formula.py's.
- To close the rest of the gap, improve the estimates on lines of 1000 EUR or more, where our F runs about 1.4x the market lo,
  rather than copying 404's a/b policy.
