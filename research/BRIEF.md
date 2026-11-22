# Research brief: QuantCo "Claim to Fame" — why FDN earns less than the top teams, and the best pricing formula

## Hard rules (read first)
- READ-ONLY research. Never submit anything to QuantCo (never call `PUT /api/games/*/submissions`, never call `put()`),
  never edit or restart the live runner (`v2_record.py`, `v2_forever.sh`, systemd service `c2f-v2-live`), never write to
  `backtest/live/state.json`, `backtest/v2/state.json`, `backtest/v2_train*/state.json`, `formula.py`, `live_opus.py`.
- Do not start Claude/Gemini/OpenAI model calls; this is data analysis on saved answers and market transactions.
- Write your own scripts and results ONLY under `~/dev/quantco-runner/research/<your-topic>/`. Final report:
  `~/dev/quantco-runner/research/<your-topic>/REPORT.md` (short: findings, numbers, recommended formula/values).
- Run Python with the project deps: `cd ~/dev/quantco-runner && uv run --with pyzipper --with pillow python -I research/<topic>/x.py`.
- The public leaderboard API (`https://c2f.public.quantco.cloud/leaderboard/api/...`) is read-only and fine to use, but
  prefer the local cache. Be gentle (no tight loops).
- Avoid overfitting: report every result walk-forward (fit on games < g, test on g) or with a hold-out (fit 1-24, test
  25-29+). In-sample numbers only as a secondary column, clearly labelled.

## The game (per invoice line)
We submit a charge `a` and an acceptance limit `b` (gross EUR). Each line has a secret fair value `t` (0 if not covered
or not related). Every team is matched against every other team in both roles:
- fair (a <= t) and accepted (a <= b): insurer pays a;   fair and rejected (a > b): insurer pays 1.5a
- inflated (a > t) and accepted: insurer pays min(a, c), c >= 4t;   inflated and rejected: nothing.
As issuer a charge never loses money. As insurer, rejecting a fair bill costs an extra 0.5a, accepting an inflated one
costs the whole amount. Score = cumulative net payoff (70%) + presentation (30%; honesty/method count).

## Data (all local)
- `live_eval/tx_cache.pkl`: pickle `{game: (bounds, transactions)}` for completed games (1-29+). `bounds[line] = (lo, hi)`
  market-inferred: lo = highest charge proven fair (wrongly rejected => paid 1.5x), hi = lowest charge proven inflated;
  `(0, inf)` = unknown. Transactions: list of `{issuer, reviewer, line_item_index, accepted, amount}` for ALL teams
  (amount = what the reviewer paid: a if accepted, 1.5a if wrongly rejected, 0 if rightly rejected). A team's charge on a
  line is recoverable from any reviewer that paid it (accepted amount, or amount/1.5).
- Model answers per game per source (lists of `{index, description, covered, related, low, fair_gross_total, high}`):
  - `backtest/live/state.json` -> `["answers"][game][opus-1|opus-2|opus-3]` (v1: 3 Opus sessions, games 0-33)
  - `backtest/v2_train_nogem/state.json` -> `["games"][game]["answers"][fable-1|opus-1|opus-2]` (v2 training, games 1-29),
    also `judge_ab` (Fable judge a/b) and `astra_ab` (GPT-6.2 Astra judge) per game.
  - v1 decider prices: `backtest/decider_all/results.json["decided"]` (games 1-11) + `backtest/live/state.json["decider"]["decisions"]` (12+).
  - live v2 (`backtest/v2/state.json["games"]`, games 23+): answers, judge_ab, formula_ab.
- Replay simulator: `fable_vs_opus.replay(g, ab, tx, teams, bounds)` with `ab = {line: (a, b)}` returns
  `net_lo/net_hi` (pessimistic/optimistic net for FDN if FDN had submitted ab, others unchanged), `issuer` (lo, hi)
  earned, `insurer_pays` (lo, hi), `actual` (FDN's real net). Teams list: all issuers/reviewers in the cache.
  Per line, net = earned(a) - paid(b) (separable: a only affects earned, b only affects paid).
- Helpers: `session_backtest.bounds`, `sb._sides(bound)`, `live_opus.category(desc)` (labour/vehicle/fee/disposal/diagnostic/parts).
- Leaderboard: `/leaderboard/api/matrix` (teams), `/transactions?game_id=G&team=T&page=..&page_size=100`, `/games?completed_only=true`.
- Research done earlier (useful context): `~/.t3-nightly/projects/quantco-c2f-pricing-research-2/` (findings/*.md,
  rule_league.md, ledger/ledger.csv), `live_eval/*.py` (rule grids, formula searches, overfit checks).

## What we already know
- Current live formula (`formula.py`), 6 pooled sources (1 Fable + 5 Opus): a = k x median fair with k = 0.92 (sources
  agree, cv < 0.15) / 0.84 (partly, cv < 0.40) / 1.16 (strongly disagree); b = 1.04 x lowest fair; every line.
- Walk-forward games 6-29: +48.4K..+243.4K; fully nested walk-forward +29.8K..+237.3K; current old rule +33.7K..+79.5K.
- Overfitting signs: charge multipliers sit at a cliff (k +0.02 => worst case -22K); "disagree" multiplier unstable
  (bootstrap 0.98..1.30); acceptance limit on the lowest fair is robust (~1.00).
- Our models' estimates have been 20-40% below the market's proven-fair charges on covered lines (labour, plumbing).
- Top teams (404, Asgardians, Humble Legends, ...) often net 5-20K per game; FDN's real cumulative result is far lower.
