# Formula agent 4: one consensus price X from 4 opinions, a = 0.91·X, b = 0.97·X

Read-only. Nothing was submitted, no live runner or state.json was touched, no model calls. All scripts are in this folder.
The fast per-line replay in `data.py` matches `fable_vs_opus.replay` to the cent (`verify.py`). The baselines reproduce the
brief's numbers (games 36-47: Ruben 2 groups +35.6K..+84.8K, 3 groups +38.2K..+89.8K). Games 1-46 are scored because the
4 judges have no game 47. Odd = 1,3,…,45 (fit, 23 games). Even = 2,…,46 (validation, 23 games). Even 36-46 = 6 games.

## The rule (per line)

1. **Covered?** More than half of the available researchers (up to 9) say `covered and related`.
   *Reason:* the researchers almost always agree. Only about 18 of 398 lines are not unanimous, so the gate barely matters
   and a simple majority is the plain choice.
2. **Four opinions**, each a median, so one wild session can't move it:
   - G1, G2, G3 = median `fair_gross_total` over the members of that group who vote covered;
   - J = median of the judges' positive charges `a` (j-all9, j-g1, j-g2, j-g3).
   *Reason:* each group has its own prompt and its own bias. The judges are the only source trained on market feedback.
   They price cautiously, at about 0.85-0.94 × the market's proven-fair level, while researchers sit near 1.0 ×. So the
   two kinds of source make different errors.
3. **X = geometric mean of the available opinions** (G1·G2·G3·J)^(1/n). A missing group or missing judges just drops out.
   *Reason:* the errors are multiplicative (a line is "30% too high", not "€30 too high"). Each independent opinion gets
   an equal vote, so no single group or judge sets the price. Weighting the 9 fairs against the judges on a log scale
   peaked at a 50/50 mix (w = 0.5), and splitting by group was better still.
4. **a = 0.91 · X** if covered, else 0.
   *Reason:* overpricing loses the whole line, while underpricing costs only a few %. The fit sits about 0.05 below the
   cliff, where earnings collapse at k ≈ 0.96-0.98.
5. **b = 0.97 · X** if covered, else 0.
   *Reason:* X runs a few % above the market's fair level. Accepting up to just under our consensus pays fair bills and
   rejects most inflated ones. The paid-curve is flat from 0.95 to 1.02, so this value is not sensitive.

That makes 2 tuned numbers and no tiers, categories or per-game terms. I tested a spread tier (agree vs disagree) and
per-category multipliers. Both flip sign between odd and even games and lose on even games (overfit), so I rejected them.

## Results: net worst..best (midpoint), games 1-46, tuned on odd games only

| rule | odd (fit) | even (validation) | even 36-46 |
|---|---|---|---|
| **a=0.91X, b=0.97X** | **+85.9K..+139.8K (+112.8K)** | **+58.1K..+116.5K (+87.3K)** | **+19.4K..+41.7K (+30.5K)** |
| Ruben avg 2 groups (live) | +50.6K..+176.4K (+113.5K) | +47.2K..+198.0K (+122.6K) | +24.7K..+62.1K (+43.4K) |
| Ruben avg 3 groups | +47.9K..+197.6K (+122.7K) | +57.0K..+197.0K (+127.0K) | +26.8K..+63.9K (+45.3K) |
| *Like for like: Ruben 2 groups without the judge-a fallback on uncovered lines* | +45.7K..+129.4K (+87.5K) | +42.2K..+131.8K (+87.0K) | +23.4K..+45.8K (+34.6K) |
| *Ruben 3 groups without the fallback* | +43.5K..+151.1K (+97.3K) | +53.3K..+132.2K (+92.7K) | +26.7K..+48.9K (+37.8K) |
| *Extra column (not approved): rule + live fallback `a = old Fable judge a` on uncovered lines* | +90.9K..+186.8K (+138.8K) | +61.8K..+181.2K (+121.5K) | +19.4K..+56.6K (+38.0K) |
| ref: no judges, a=0.80·med9, b=0.96·med9 | +58.9K..+114.3K | +42.6K..+96.6K | +11.7K..+32.6K |

How to read the table:
- **Worst case (the primary score):** on even games the rule beats Ruben 2 groups by +10.9K and Ruben 3 groups by +1.1K.
- **Best case and midpoint:** the baselines look higher, but almost all of that gap comes from them charging *uncovered*
  lines at the old judge's `a`. The market's status on those lines is often unknown, so the best case books 1.5a.
  - Like for like (no uncovered charging): the rule wins on worst case and on midpoint in both odd and even games.
  - With the same fallback added (extra column): the rule's even midpoint is +121.5K, against +122.6K and +127.0K.
- **Weak spot, even games 36-46:** the rule's worst case is 5-7K below both baselines. The gap is on the charge side, in
  a few lines (game 38 line 3, game 42 line 1). In these recent games the k-curve peaks at 0.93-0.94 rather than 0.91.
  Six games are too few to retune on, and doing so would mean tuning on even games.

## Robustness (net worst; one value moved)

| | odd | even | even 36-46 |
|---|---|---|---|
| kA 0.86 / 0.89 / **0.91** / 0.93 / 0.96 | +69.9 / +77.6 / **+85.9** / +74.5 / +55.8K | +45.7 / +55.2 / **+58.1** / +53.0 / +31.9K | +12.1 / +19.2 / **+19.4** / +21.7 / +5.1K |
| kB 0.92 / 0.95 / **0.97** / 0.99 / 1.02 | +76.7 / +81.6 / **+85.9** / +85.9 / +85.3K | +56.6 / +58.7 / **+58.1** / +58.3 / +59.4K | +19.6 / +20.6 / **+19.4** / +19.5 / +20.1K |

- **kA has a cliff above it.** +0.05 costs about 26K on even games, while −0.05 costs about 12K. If in doubt, err low.
- **kB is flat.**
- **Bootstrap, refitting on resampled odd games (500 runs):** kA 5/50/95% = 0.84/0.91/0.95 and kB = 0.95/0.98/1.03.
  The even worst case with the refit values is +30.5K / +49.4K / +59.7K.
- **Paired bootstrap over even games, rule minus baseline (worst case):**
  - vs Ruben 2 groups: median +10.0K, 90% range −9.0K..+33.2K, P(>0) = 0.79;
  - vs Ruben 3 groups: median +0.5K, 90% range −17.9K..+20.5K, P(>0) = 0.52.
- **Per game:** the rule's worst case beats Ruben 2 groups in 9 of 23 even games, with 2 ties. It wins through fewer
  large losses (games 18, 29, 32, 33), not by winning most games. Full per-game table in `final.out`.

## Recommendation

On covered lines, use **a = 0.91·X and b = 0.97·X, with X = the geometric mean of (G1 median, G2 median, G3 median,
median judge a)**.
- **What it improves:** it is a clear worst-case gain over the live 2-group rule (+10.9K on even validation, +35K on odd
  fit), it is simpler (one price per line, 2 numbers), and it is explainable.
- **What it doesn't improve:** against the 3-group Ruben rule it is only a tie on even worst case, and it is slightly
  behind on recent games 36-46. So it is not a decisive upgrade over "Ruben 3 groups" for the live system.
- **Uncovered lines** are a separate decision for Daniil. Keeping the live system's old-judge fallback adds +5.0K (odd) / +3.7K
  (even) worst case and +47K / +65K best case (extra column).
- **Do not raise kA above about 0.93.**
