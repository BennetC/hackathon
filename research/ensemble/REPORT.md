# Ensembles of per-line price sources vs formula.py

**Bottom line: no ensemble robustly beats formula.py.** The one consistent small gain comes from raising the charge to
the Fable judge's charge when it is higher: **a = max(formula a, J a), with b still from formula.py**. That gain is
small and comes from a handful of lines. Averaging rules (median or mean of the candidates), regime switching,
per-category picking and honest model selection all lose to the formula. On the b side nothing beats
**b = 1.04 × lowest fair**.

Scripts: `pre.py` (candidates per line plus replay), `ens.py` (rule families, walk-forward and hold-out),
`robust.py` (per-game, half-split and bootstrap checks). Raw output: `ens_out.txt`, `robust_out.txt`. Everything uses the
`fable_vs_opus.replay` net, worst..best (lo..hi). Selection uses the worst case.

## Candidates (per line, a and b)
| Name | Source |
|---|---|
| F | formula.py on the 6 sources, constants fitted on 1-29 (so it is in-sample on 6-29) |
| W | the same formula type, refitted walk-forward (fit on games < g); fit on 1-24 for the hold-out |
| D | v1 decider |
| J | Fable judge (v2 training) |
| A | Astra judge |
| O | old median rule (`rule_old_ab`) |
| N | `rule_new_ab` |
| R | teammate's combination: max of the D and J charges, average of their limits capped at 1.1a |

## Rule families tested (335 a-rules, 111 b-rules)
- median, mean, min and max over every subset of {F/W, D, J, A, O}, with zeros either included or excluded
- b from the most cautious candidate (min b), and median, mean and max of the b's
- regime switching: if the cv of the candidates' a's is below τ (0.05 to 0.5), use the mean, median or max; otherwise use the formula
- per category (labour, vehicle, ...), the candidate with the best worst case on past games
- honest selection: the best rule chosen on games < g only (nested walk-forward), or on 1-24 for the hold-out

## Net results (worst .. best, EUR)
| Rule | Walk-forward, games 6-29 | Hold-out, games 25-29 |
|---|---|---|
| **formula type W (honest walk-forward refit)** | **+48.4K .. +243.4K** | **+24.7K .. +80.1K** |
| formula.py constants F (in-sample on 6-29) | +54.8K .. +255.1K | +25.4K .. +80.8K |
| **a = max(W, J), b = W** | **+55.8K .. +252.9K** | **+26.2K .. +82.8K** |
| a = max(W, D, J), b = W | +52.7K .. +253.9K | +26.2K .. +82.8K |
| honest selection from the whole ensemble family | +42.6K .. +229.3K | +16.0K .. +23.5K |
| per-category best candidate (a and b) | +36.0K .. +169.2K | +24.0K .. +77.8K |
| a = median(W, D, J, A), b = min of the four | +35.0K .. +111.8K | +15.6K .. +20.4K |
| a = mean(W, D, J, A), b = min of the four | +33.2K .. +133.2K | +14.7K .. +32.9K |
| teammate's combination R | +38.6K .. +135.1K | +15.2K .. +22.8K |
| D / J / A / O alone | +15.8K / +6.8K / −24.7K / +14.3K (worst case) | about +14K / +14K / −9.5K / +14.8K (worst case) |
| a = min of the candidates ("most cautious" a) | −4.9K .. +42.7K | −0.0K .. +4.4K |

The W row reproduces the brief's walk-forward figure (+48.4K .. +243.4K), which validates the setup.

## Robustness of a = max(formula, J), a side only (b is unchanged)
| Check | vs W (honest refit) | vs F (formula.py constants, in-sample) | Hold-out 25-29 |
|---|---|---|---|
| Δ worst case | +7.4K | +2.0K | +1.5K |
| Δ best case | +9.5K | +12.5K | +2.7K |
| Games up / down (worst case) | 7 / 1 of 24 | 9 / 2 of 24 | 2 / 0 of 5 |
| Δ worst case, games 6-17 | +0.2K | +1.0K | – |
| Δ worst case, games 18-29 | +7.2K | +1.0K | – |
| Bootstrap P(Δ > 0) | 1.00, 5-95% [+1.0K, +15.5K] | 0.62, 5-95% [−13.1K, +14.7K] | 0.92 |
| Lines changed | 33 | 32 | 3 |

- Most of the gain comes from 2 lines: g21 l17 (+3.8K) and g27 l1 (+2.2K).
- Against the in-sample constants, one line loses 7.0K (g19 l2).
- Adding D (closer to the teammate's max(D, J)) is weaker: +4.2K worst case, bootstrap P = 0.76, and −3.2K on games 6-17.
- max(F, D) alone is negative against formula.py constants: −6.3K.

## Why the ensembles lose
- The formula's charges sit just under the market's fair value. Any averaging that pulls a toward D, J or A makes the
  charge cheaper, because those sources are 20-40% low. The formula already corrects for this with k.
- min(a) is the worst rule of all.
- max(a) helps only with J. J is the one candidate that is occasionally higher than the formula and still fair.
- On the b side, formula.py's lowest fair × 1.04 ranks 4th of 111 b-rules. The rules above it gain at most 0.05K
  (min(F, J, A) and similar), which is noise. Every median or mean of the judges' b's pays 1-35K more.
- Regime switching looks best in-sample (worst case +183.5K earned vs +177.6K for F), but it gives up about 80K of
  best case and loses when chosen walk-forward.

## Recommendation
- Keep formula.py.
- If you want an ensemble at all, use only **a = max(formula a, J a) when J is available; b = formula b**.
  - Expected gain: about +2K to +7K worst case over 24 games.
  - It comes from about 5 decisive lines and was selected after looking at the results.
  - Treat it as optional and unproven: it was positive in every split (walk-forward, hold-out and both halves), but small.
- Do not use median or mean ensembles, the teammate's combination R, min-of-candidates charges, per-category switching,
  or judge-based acceptance limits.
