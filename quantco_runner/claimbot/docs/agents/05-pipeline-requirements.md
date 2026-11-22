# 05 Pipeline requirements

## Round timeline (budget 60 s; aim to finish < 40 s)

| t (s) | Step |
|---|---|
| −60 … 0 | Scheduler knows the next `start_time` from `/api/games/list` (polled every few minutes, not hammered). Case zip pre-located, model clients warmed. |
| 0 – 2 | `GET /key` (short retry on 403 right after start). |
| 2 – 4 | `7z x` into a fresh temp dir. Read text, extract PDF text, locate `photo*`. |
| 4 – 8 | Parse invoice lines. **Immediately PUT a fallback submission** for all lines (see below). |
| 8 – 40 | Full analysis: coverage + price estimates. Run LLM calls in parallel per line or batch, with hard timeouts. |
| ≤ 50 | PUT the final submission. Verify the response echoes every index. |

## Fallback ladder (never miss a round)

1. Full model output.
2. Heuristic only (e.g. price table, no LLM): rough `t` per line; the strategy turns it into `(a, b)`.
3. If line parsing fails: submit indices `1..N_guess` with `a = 0` and a moderate `b`. Note that `b = 0` is the default **and** the most expensive choice when bills are fair.
4. Every stage has its own timeout. A crash at any step must still produce a PUT.

## Reliability

- Run as a long-lived process on one machine, with a second person/machine as a hot standby only if submissions are idempotent (they are: last write wins). Agree on who is primary.
- Machine must not sleep; keep laptop/power/network in mind for the overnight run.
- Clock sync (NTP). Use UTC everywhere.
- Retries with backoff on network errors. Don't overload the API.
- Cache parsed policies by hash (see 03).

## Logging / evidence (feeds the 30 % pitch)

Per round, persist (git-ignored, e.g. `runs/<game_id>/`): timestamps per stage, parsed lines,
per-line `p_excl`, `t` median/spread, chosen `a`/`b`, API responses, model + token usage,
and leaderboard delta afterwards. These logs support "evidence", "reliability" and
"honesty" in the write-up.

## Judging reminders

- Resourcefulness: prefer small or cheap models and caching over huge prompts. Report token cost per round.
- Method & uncertainty: be able to explain `t` estimation and how `a` and `b` are chosen.
- Honesty: track what actually happened vs the plan.

## Environment

`pixi.toml` from the starter kit: python 3.14, requests, openai, p7zip. An `OPENAI_KEY` is
expected by the organisers' kit; any LLM provider is allowed. Secrets go in `.env` (git-ignored).
