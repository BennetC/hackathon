# Formula research over 9 researchers + 4 judges (read ~/dev/quantco-runner/research/BRIEF.md first: its Hard rules apply)

Hard rules (repeat): READ-ONLY. Never submit (no PUT, no put()), never edit/restart the live runner (v2_record.py,
v2_forever.sh, service c2f-v2-live), never write any state.json, no Claude/Gemini/OpenAI model calls. Write ONLY under
~/dev/quantco-runner/research/formula9/<your-topic>/. Run: cd ~/dev/quantco-runner && uv run --with pyzipper --with pillow --with numpy python -I research/formula9/<topic>/x.py

## Goal
Find the best mathematical rule that turns, per invoice line, the answers of 9 researchers and 4 judges into the charge a
and acceptance limit b we submit. Primary score: replayed net payoff, WORST case (net_lo); also report best case and midpoint.

You work INDEPENDENTLY: design your own formula from your own analysis. Do not read other folders under research/formula9/.
The formula must MAKE SENSE: every term needs a reason you can state in one sentence (which source to trust when, why a
multiplier sits where it does). No unexplained black boxes, no per-game hacks, few parameters.

Evaluation protocol (Daniil): tune all exact values (multipliers, weights, thresholds) on ODD-numbered games only;
validate on EVEN-numbered games only, never tuned on. Report odd (fit) and even (validation) separately, plus even games
36-46 as a recent sub-block. Choose your final rule by its odd-game result and its simplicity, then report its even-game
result once. Compare with both baselines on the same odd/even split.

## Data per game g (lines are 1-based; answers are lists of {index, description, covered, related, low, fair_gross_total, high})
- Group 1 (3 Opus, oldest sessions): backtest/live/state.json ["answers"][g][opus-1|2|3] (games <= 33); for g >= 30 also
  backtest/v2/state.json ["games"][g]["answers"][v1-opus-1|2|3] (prefer this when present).
- Group 2 (Fable + 2 Opus): backtest/v2_train_nogem/state.json ["games"][g]["answers"][fable-1|opus-1|opus-2] for g <= 29;
  backtest/v2/state.json ["games"][g]["answers"][fable-1|opus-1|opus-2] for g >= 30.
- Group 3 (NEW: 2 Fable + 1 Opus, bottom-up prompt + market price book; low/high are 10th/90th percentiles, fair = median):
  backtest/v3_train/state.json ["games"][g]["answers"][fable-a|fable-b|opus-c] for g = 1..47 (sessions learn over time;
  weak in games 1-12). Live from game 49: backtest/v2/state.json ["games"][g]["v3_answers"].
- 4 Opus judges (trained on cases 1..46 in order, each with its own market feedback; a/b per line):
  backtest/v3_judges/state.json ["games"][g]["judge_ab"][j-all9|j-g1|j-g2|j-g3] = {line: [a, b]}.
  j-all9 reads all 9 (labels A-C = group 2, D-F = group 1, G-I = group 3); j-gN reads only group N.
- Old Fable judge (reads groups 1+2): v2_train_nogem ["judge_ab"] (g <= 29), backtest/v2/state.json ["judge_ab"] (g >= 30).
- Market: live_eval/tx_cache.pkl (1-29), research/opponents/tx_30_34.pkl, research/s4-imitate-404/tx_35.pkl,
  live_eval/tx_36plus.pkl (36-47): pickle {g: (bounds, transactions)}; bounds[line] = (lo, hi).
- Replay: fable_vs_opus.replay(g, ab, tx, teams, bounds) -> net_lo/net_hi; per line net = earned(a) - paid(b), so a and b
  can be searched separately per line (precompute per-line curves; see live_eval/formula_search2.py, overfit.py).
- Baselines (live_eval/ruben3_test.py reproduces them): Ruben avg 2 groups = what we submit now (per group: a = 0.93 x median
  fair, b = 0.96 (g1) / 0.91 (g2) x median fair if majority covered, else 0/0; a = mean of positive group charges, else the
  judge's a; b = mean of group limits, 0 if any is 0). Games 36-47: 2 groups +35.6K..+84.8K, 3 groups +38.2K..+89.8K,
  group 3 alone +44.0K..+95.7K.

## Known facts
Our old 6 sources' fair runs about 1.02-1.04 x the market's proven-fair level on average but misses both ways by line
type; group 3 is much more accurate from game 13 on (fair inside the market range 77 vs 28 lines on games 13-35).
Overpricing loses the whole line (inflated & rejected -> 0); underpricing costs little. Charge multipliers sit near a
cliff. Uncovered lines: Daniil has NOT approved charging lines most sources call uncovered (report such variants only as
an extra column).

## Deliverable
research/formula9/<topic>/REPORT.md (short): the rule in exact maths with the reason for each term, results on odd games
(fit) and even games (validation, plus even 36-46), worst/best, vs both baselines on the same split, robustness
(each tuned value +-0.02/0.05; bootstrap over games), and a clear recommendation. Final message: the rule + key numbers.
Use your own topic folder name: research/formula9/agent-<N>/ (N given in your task).
