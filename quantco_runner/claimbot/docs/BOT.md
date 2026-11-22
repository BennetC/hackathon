# claimbot: running the bot

`claimbot` plays every game on its own. It waits for each `start_time`, fetches the key,
decrypts the case, prices every line, and submits within the 60 s window. It also has a
debug mode for running any single game by hand with full timestamps and an offline backtest
command.

## Code layout

```
claimbot/
├── cli.py                  claimbot listen | debug <game> | games | backtest
├── config.py               settings from .env (default strategy: "council")
├── models.py               shared types: Case, LineItem, LinePrice (index, a, b)
├── api/                    QuantCo API client (games, key, submissions)
├── preprocessing/          preparing the data
│   ├── archive.py          find the zip for a game, check the key, decrypt safely
│   ├── case.py             build a Case: policy, damage report, invoice text, lines, photos
│   ├── invoice.py          PDF text extraction (pdftotext -layout / pypdf) + line parsing
│   └── images.py           downscale / encode photos (standard + 5 MB / 1568 px JPEG-88)
├── runner/                 running games
│   ├── listener.py         follows the schedule, wakes up for every game
│   └── pipeline.py         one game: key -> decrypt -> parse -> fallback -> strategy -> submit -> bench
├── llm/                    provider-neutral LLM transport layer
│   ├── __init__.py         make_llm() + lazy backend exports
│   ├── base.py             LLMBackend ABC, LLMRequest, LLMError, VALUATION_SCHEMA, PRICING_SCHEMA
│   ├── antigravity_backend.py  AntigravityBackend (zero-tools ACP, warm sessions, inline images)
│   ├── cli_backends.py     ClaudeCodeBackend (claude -p), CodexBackend (codex exec)
│   └── anthropic_backend.py    AnthropicBackend (Anthropic Messages API)
├── strategies/             turn a Case into a StrategyResult
│   ├── __init__.py         REGISTRY + load_strategy() ("council" or "module:Class")
│   ├── base.py             Strategy ABC, StrategyResult, LineValuation, PublishFn
│   └── council.py          Council(Strategy) — registered empty skeleton ("council")
├── logs/                   logging setup (console + per-run DEBUG log)
└── evaluation/             exact payoff rules, offline backtest runner, FDN Bench uploader (`bench.py`)
tests/                      offline unit tests (no fake backend in production code)
```

## Setup

Python ≥ 3.11. No 7-Zip needed: archives are decrypted with `pyzipper`.

```sh
git clone <repo> && cd fdn-start-hack-2026
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"   # or: uv venv && uv pip install -e ".[dev]"
cp .env.example .env            # then set TEAM_API_KEY (never commit .env)
mkdir -p data/cases && cp /path/to/Cases/case_*.zip data/cases/
.venv/bin/pytest -q             # offline tests
```

## Commands

| Command | What it does |
|---|---|
| `claimbot games` | Prints the schedule with each game's status and marks the next one. |
| `claimbot listen` | Runs forever and plays every game. |
| `claimbot listen --dry-run` | Same, but never submits. |
| `claimbot debug <id>` | Runs the full pipeline once for one game, with DEBUG logs and a timeline. |
| `claimbot backtest` | Replays finished games offline (dry run, never submits) and compares against our team's actual results. |

Global flags (before the command): `-v` for DEBUG on the console, `--strategy name|module:Class`,
`--env-file path`, `--bench-name <name>`, `--no-bench`.

### Debug mode

```sh
claimbot debug 0                          # test game 0: real key, real submit (stores nothing)
claimbot debug 12 --dry-run               # replay a past game without submitting
claimbot debug 12 --dry-run --no-deadline # let a slow strategy finish
claimbot debug 13 --wait                  # wait for a future game's start, then play it live
claimbot debug 5 --key <k> --zip some.zip --dry-run   # fully offline replay
```

- The key endpoint keeps working after a game ends, so past games can be replayed. Submitting to an ended game is refused (`403`), so use `--dry-run`.
- For past games, the 60 s deadline is *simulated* from the moment the key arrives, so you see realistic timing. `--no-deadline` turns it off.
- At the end it prints a timeline (UTC timestamp, seconds since start, ok/FAIL per stage) and the paths to the run's files.

### Backtest mode

```sh
claimbot --strategy council backtest --games 1-7 --parallel 4
```

Replays finished games in dry-run mode and writes `results.md` and `results.json`.

## What one run does (`claimbot/runner/pipeline.py`)

```
key              GET /api/games/{id}/key   (waits for start_time, retries 403 for KEY_RETRY_S)
locate_zip       data/cases/case_NNN.zip; if the key doesn't open it, try the key on every zip
decrypt          → runs/game_NNN/<stamp>/case/   (member names flattened; untrusted input)
parse            policy.txt, description.txt, invoices.pdf → line items, photo*
submit_fallback  immediately: FALLBACK_CHARGE / FALLBACK_LIMIT for every line
strategy         strategy.price(case, deadline, publish=...) in a thread,
                 hard timeout = window − SUBMIT_MARGIN_S
submit_final     strategy quotes merged over the fallback (or last published interim quotes);
                 checks every index was stored
upload_bench     (optional, strictly after submit_final) POST final quotes + valuations + latency
                 to FDN Bench `/api/runs` (skipped for game 0 or when `--no-bench` / disabled)
```

The pipeline never raises. A failure at any stage is logged, recorded, and whatever could
be submitted has been submitted. Each stage is timestamped relative to both the run start
and the official game start (`T+…s`).

### Output per run: `runs/game_NNN/<utc-stamp>/`

- `run.log`: every log line at DEBUG level, with UTC millisecond timestamps.
- `report.json`: stage timeline, errors, parsed case summary (lines, photos, description), fallback and final quotes, and every submission request and response.
- `strategy_trace.json`: written whenever the strategy returns non-empty `trace` or `valuations` (or sets `strategy.last_trace`).
- `case/`: the decrypted files, kept so the run can be reproduced. (`runs/` is git-ignored.)

## LLM backends (`claimbot/llm/`)

All LLM providers subclass `LLMBackend` (`claimbot/llm/base.py`), share the same constructor
`(model=None, effort=None)`, and share the same `complete_json(LLMRequest) -> dict` /
`ask(...) -> dict` contract. Switching models or providers is a one-line swap:

```python
from claimbot.llm import (
    AntigravityBackend,
    AnthropicBackend,
    ClaudeCodeBackend,
    CodexBackend,
    VALUATION_SCHEMA,
    PRICING_SCHEMA,
    make_llm,
)

llm = AntigravityBackend(model="gemini-4-neon-low")
# or swap to any other backend with the exact same interface:
llm = CodexBackend(model="gpt-6-luna", effort="high")
llm = ClaudeCodeBackend(model="opus", effort="high")
llm = AnthropicBackend(model="claude-opus-5-5", effort="high")
# or by provider name:
llm = make_llm("antigravity", model="gemini-4-neon-low")
```

| Backend | Default model / effort | Runs via | Needs |
|---|---|---|---|
| `AntigravityBackend` | `gemini-4-neon-low` / `low` | Local `antigravity acp` (warm JSON-RPC workers, native inline base64 images, 4-layer zero-tools isolation) | Antigravity login (`~/.config/antigravity`) |
| `AnthropicBackend` | `claude-opus-5-5` / `high` | Anthropic Messages API (prompt caching, structured output) | `ANTHROPIC_API_KEY` |
| `ClaudeCodeBackend` | `opus` / `high` | `claude -p` (isolated temp dir, `--tools ""`, text only) | Claude CLI login |
| `CodexBackend` | `gpt-6-luna` / `high` | `codex exec` (read-only sandbox, supports images) | ChatGPT / Codex CLI login |

### What a backend returns

- A backend is a **pure LLM transport** — it does **not** compute `(a, b)` or own strategy logic.
- `complete_json(req)` / `ask(...)` returns the **parsed Python `dict`** matching `req.schema` (defaulting to `VALUATION_SCHEMA`).
- Two canonical shared schemas live in `claimbot/llm/base.py`:
  - `VALUATION_SCHEMA`: `{"lines": [{"index", "description", "covered", "related", "fair_gross_total", "low", "high"}]}`
  - `PRICING_SCHEMA`: `{"lines": [{"index", "a", "b", "reason"}]}`
- Token usage is tracked thread-safely on the backend instance and drained with `llm.take_usage()` (not mixed into the returned JSON payload).
- Backends support `close()` and context-manager usage (`with AntigravityBackend(...) as llm:`) to clean up persistent worker processes.

### Antigravity ACP specifics

- `find_antigravity_bin()` skips `/usr/bin/antigravity` (the Electron desktop app) and resolves `CLAIMBOT_ANTIGRAVITY_BIN` → `agy` on `PATH` → latest `~/.t3/tools/antigravity-acp/*/versions/*/antigravity`.
- Every ACP worker enforces 4-layer zero-tools isolation: isolated `--gemini-dir` with empty `mcp_config.json`, custom `claimbot-notools` agent (`tools: []`, `commandExecutionPolicy: off`), explicit `permissions.deny` rules, and RPC rejection of any `session/request_permission`.
- Inline images follow the 5 MB base64 threshold → raw preserved, else RGB `thumbnail((1568, 1568))` JPEG quality 88 (`claimbot/preprocessing/images.py:prepare_daniil_image`).
- Empirical Game 1 latency (41 KB policy + 1.1 MB photo): `gemini-4-neon-low` finishes in ~20–24 s (single turn, zero tools); `gemini-4-neon-medium` (> 70 s) and `gemini-4-neon-high` (> 90 s) exceed a 40 s live estimator budget.

## Strategies (`claimbot/strategies/`)

All strategies subclass `Strategy` (`claimbot/strategies/base.py`) and return a `StrategyResult`:

```python
from claimbot.models import Case, LinePrice
from claimbot.strategies.base import LineValuation, PublishFn, Strategy, StrategyResult

class MyStrategy(Strategy):
    name = "my_strategy"

    def price(
        self,
        case: Case,
        deadline_ts: float,
        publish: PublishFn | None = None,
    ) -> StrategyResult:
        # Check remaining time with self.remaining_s(deadline_ts)
        # Optionally call publish(interim_quotes_or_result) mid-run
        return StrategyResult(
            quotes=[LinePrice(index=line.index, a=..., b=...) for line in case.lines],
            valuations=[LineValuation(index=line.index, covered=..., related=..., low=..., fair=..., high=..., reason=...) for line in case.lines],
            trace={"timings_s": ...},
        )
```

### What `StrategyResult` contains and what `pipeline.py` does with it

1. **`quotes: list[LinePrice]`** — gross EUR whole-line totals (`a` = charge price, `b` = acceptance limit).
   - `pipeline.py` sanitizes every quote (non-finite or negative → `0.0`, rounded to cents) and drops any index not present in `case.lines`.
   - Quotes are **merged over the fallback quotes** (or over the latest interim quotes sent via `publish(...)`). Any line omitted by the strategy keeps its fallback/interim quote.
   - The merged list is submitted via `PUT /api/games/{id}/submissions` and verified against QuantCo's echoed line indexes.
2. **`valuations: list[LineValuation]`** — optional per-line underlying estimates (`covered`, `related`, `low`, `fair`, `high`, `reason`) for offline auditing and FDN Bench pricing sweeps.
3. **`trace: dict`** — optional JSON-serialisable diagnostics (timings, token usage, raw model outputs). Together with `valuations`, it is saved to `runs/game_NNN/<ts>/strategy_trace.json`.
4. **Interim `publish(quotes_or_result)` callback** — calling `publish(...)` mid-run submits an interim PUT immediately and saves those quotes as the safety net if `price()` later times out.
5. **Lifecycle hooks** — `Strategy` also provides `remaining_s(deadline_ts)`, `on_game_settled(game_id, transactions)`, `close()`, and context-manager support (`with strategy:`).

### Registered strategy: `Council` (`CLAIMBOT_STRATEGY=council`)

`claimbot/strategies/council.py` defines `Council(Strategy)` (`name = "council"`), currently registered as an **empty placeholder skeleton** that returns `StrategyResult()` (causing the pipeline to keep fallback quotes until implemented). Previous experimental strategies (`baseline`, `panel`, `live_neon`) were removed to rebuild `Council` cleanly on top of `LLMBackend` and `Strategy`.

Custom strategies can also be loaded by import path: `CLAIMBOT_STRATEGY=mypkg.mymodule:MyStrategy` (or `--strategy`).

## Running it for the tournament

Run **one** `claimbot listen` on one machine that stays awake and online, with the clock
synced (NTP). Several listeners are harmless (last write wins) but waste calls and confuse
logs. Coordinate with the team before going live so only one team member submits.

## Configuration (`.env`, see `.env.example`)

| Variable | Default | Meaning |
|---|---|---|
| `TEAM_API_KEY` | (required) | Team key |
| `CLAIMBOT_BASE_URL` | `https://c2f.public.quantco.cloud` | API base |
| `CLAIMBOT_CASES_DIR` | `data/cases` | Encrypted case zips |
| `CLAIMBOT_RUNS_DIR` | `runs` | Run logs and reports |
| `CLAIMBOT_CASE_FILE_TEMPLATE` | `case_{game_id:03d}.zip` | Zip file for game N |
| `CLAIMBOT_STRATEGY` | `council` | Registered strategy name (`council`) or `module:Class` |
| `CLAIMBOT_ANTIGRAVITY_BIN` | (auto-detected) | Optional explicit path to the `antigravity` / `agy` CLI/ACP binary |
| `CLAIMBOT_GAME_WINDOW_S` | `60` | Submission window |
| `CLAIMBOT_SUBMIT_MARGIN_S` | `8` | Strategy must finish this long before the window closes |
| `CLAIMBOT_KEY_RETRY_S` | `15` | Keep retrying `403` on the key for this long after start |
| `CLAIMBOT_KEY_EARLY_S` | `0.5` | First key poll this long before `start_time` |
| `CLAIMBOT_KEY_POLL_S` | `1.0` | Seconds between key poll retries on `403` |
| `CLAIMBOT_WAKE_LEAD_S` | `10` | Listener wake lead time before `start_time` |
| `CLAIMBOT_SCHEDULE_REFRESH_S` | `120` | How often the listener re-reads the schedule |
| `CLAIMBOT_HTTP_TIMEOUT_S` | `8` | Per-request HTTP timeout |
| `CLAIMBOT_FALLBACK_CHARGE` / `_LIMIT` | `0` / `200` | `(a, b)` used before the strategy answers (placeholder values) |
| `CLAIMBOT_FALLBACK_LINE_COUNT` | `0` | If parsing finds no lines, submit indexes 1..N blind (`0` = off) |
| `CLAIMBOT_BENCH_URL` | `https://bench.159-195-78-137.sslip.io` | FDN Bench base URL |
| `CLAIMBOT_BENCH_TOKEN` | (empty) | Bearer token for FDN Bench (also accepts `BENCH_TOKEN`); setting it auto-enables upload |
| `CLAIMBOT_BENCH_AUTHOR` | `fdn` | Author label sent with FDN Bench uploads |
| `CLAIMBOT_BENCH_STRATEGY_NAME` | (strategy `.name`) | Optional strategy name override in FDN Bench (also `--bench-name`) |
| `CLAIMBOT_BENCH_UPLOAD` | `true` if token set | Explicitly enable/disable post-submit FDN Bench upload (`--no-bench` disables per run) |

## Current status & open work

- `Council` (`claimbot/strategies/council.py`) is currently an empty skeleton returning `StrategyResult()`. Until it is implemented, every run falls back to `CLAIMBOT_FALLBACK_CHARGE` / `CLAIMBOT_FALLBACK_LIMIT`.
- Historical benchmark baselines and transport notes from the earlier Daniil `live_opus.py` mirror on Gemini 4 Neon are preserved in [`docs/DANIIL_NEON_MIRROR.md`](DANIIL_NEON_MIRROR.md).
