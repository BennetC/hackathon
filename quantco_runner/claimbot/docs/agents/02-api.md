# 02 API

Base URL: `https://c2f.public.quantco.cloud` (the starter script has a trailing `/` and then
joins `/api/...`, which gives `//api`. It works, but normalise it.)
Auth: header `X-API-Key: $TEAM_API_KEY` on all team endpoints.
Leaderboard UI: `https://c2f.public.quantco.cloud/leaderboard/`

## `GET /api/games/list`

Lists all games: `[{"id": 1, "start_time": "2025-06-01T12:00:00Z"}, ...]`.
Game `0` is a permanent test game: always open, stores nothing. The starter script uses `games[0]`.

## `GET /api/games/{game_id}/key`

`{"decryption_key": "secret123"}`. Available **only after `start_time`**.
Errors: `403` not started, `404` unknown game.
Fair play: don't spam this before start. Schedule from `start_time` and retry briefly (e.g. every 0.5–1 s for a few seconds) right after it.

## `PUT /api/games/{game_id}/submissions`

Body: a JSON array. Upsert: last write wins. Partial submissions are allowed; omitted lines default to `0/0`.

```json
[
  {"index": 1, "charge_price": 50.0, "acceptance_limit": 80.0},
  {"index": 2, "charge_price": 120.0, "acceptance_limit": 150.0}
]
```

Response: one record per line, `{game_id, team_id, line_item_index, charge_price, acceptance_limit, submitted_at}`.
Errors: `401` bad key; `403` not started / already ended / team created after game start; `404` unknown game;
`422` negative or non-finite value. The test endpoint (game 0) accepts any well-formed JSON.

## Decryption

`7z x case_NNN.zip -p<key> -o<outdir>` (zips are WinZip-AES, method 99). The stdlib
`zipfile` **cannot** decrypt AES; use `7z` (pixi `p7zip`) or `pyzipper`. `7z` is not
installed on the dev box yet. Run `pixi install` or install `p7zip`.

## Starter kit

`starter_script.py` lists games, takes game 0, fetches the key, and submits two dummy lines.
`pixi.toml`: python 3.14, requests, openai, p7zip (Unix) / 7zip (Windows).
Run with `pixi install && pixi run python starter_script.py`. The env vars `TEAM_API_KEY`
and `OPENAI_KEY` are expected.

## Public leaderboard API (no auth, read-only)

Observed in the leaderboard page source (`/leaderboard/`, Alpine.js app) on 2026-11-21:

| Endpoint | Returns |
|---|---|
| `GET /leaderboard/api/games?page=1[&completed_only=true&page_size=1000]` | `{page, page_size, total, total_pages, items:[{id, start_time, status}]}` |
| `GET /leaderboard/api/performance?team=<name>` | `{income, issued_count, issued_accepted, costs, reviewed_count, reviewed_accepted, reviewed_accepted_right, reviewed_accepted_wrong, reviewed_correct_rejections, reviewed_penalties, net}` |
| `GET /leaderboard/api/matrix?page=&game_limit=20` | `{game_ids, items:[{team_name, cells:[net per game], total}], page, total_pages, total}` |
| `GET /leaderboard/api/matchup?team=&page=&game_limit=20` | `{game_ids, items:[{team, opponent, cells, total}], ...}` |
| `GET /leaderboard/api/transactions?game_id=&team=&page=[&line_item=]` | `{items:[{line_item_index, issuer, reviewer, accepted, amount}], total, page, total_pages}` |

Standings are server-rendered into the HTML. The page also embeds `nextGameStart` and
`gameDurationSeconds = 60.0`.

**Schedule (fetched):** games 1–100, `start_time` = 2026-11-21T13:00:00Z + (id−1)·800 s; the last is
2026-11-22T11:00:00Z. Window = 60 s. The status values seen so far are `scheduled`; others are presumably in progress or completed.

**Post-game inference** (from transactions): rejected with amount `1.5a` ⇒ `a ≤ t`;
rejected with amount 0 ⇒ `a > t`; accepted ⇒ amount = `a` (or `min(a, c)`). Pooling across
teams brackets `t` per line, which could be used for calibration between rounds. **Fair-play
status unclear** (the rules ban reading others' submissions and extracting thresholds). Do
not build automated scraping of this until the team has confirmed with QuantCo. Our own
performance numbers are fine to monitor. Cache responses (finished games never change),
use a low request rate, and keep identifying details out of requests.

## Timing and next game

- Window: `[start_time, start_time + 60 s)`. A late PUT returns `403` "already ended".
- Cadence: 800 s (= 79,200 s / 99 gaps between 14:00 and 12:00 local). `start_time(N) = 2026-11-21T13:00:00Z + (N−1)·800 s`, N = 1..100.
- There is no next-game endpoint. Next game = `min(start_time > now)` from `/api/games/list`. Re-fetch the list periodically (e.g. every few minutes) in case the schedule changes; never hard-code the schedule as the only source.
- There is no GET for our own submissions. The PUT response is the only confirmation, so verify that it echoes every index and log it.

## curl quick reference

```sh
curl -H "X-API-Key: $TEAM_API_KEY" $BASE/api/games/list
curl -H "X-API-Key: $TEAM_API_KEY" $BASE/api/games/0/key
curl -X PUT -H "X-API-Key: $TEAM_API_KEY" -H "Content-Type: application/json" \
     -d '[{"index":1,"charge_price":50.0,"acceptance_limit":80.0}]' $BASE/api/games/0/submissions
```

## Open points

- Does game id N map to `case_NNN.zip`? Not stated, but likely: there are 100 games (1–100) and cases 001–100, with 000 as the test. Verify on game 0 / the first real game by trying the key on the expected file, with a fallback of trying the key on every not-yet-opened zip (a local operation, so fair).
- Is there a submission-window end time in the list response? Assume `start_time + 60 s`.
