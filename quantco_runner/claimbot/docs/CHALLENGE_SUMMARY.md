# QuantCo "Claim to Fame" — challenge summary

*Source: QuantCo materials in "[PUBLIC] Road to Start HACK" (GAME_DESCRIPTION.pdf,
EVALUATION_CRITERIA.pdf, API_HANDBOOK.md, starter_script.py, Deep Dive slides,
kick-off slides). Compiled 2026-11-21.*

## The game in one paragraph

QuantCo releases one insurance claim ("case") to every team at the same moment.
The case contains an insurance policy, a damage description, an invoice whose
line items have **no prices**, and usually photos. Within **one minute** each team
submits two numbers per invoice line: a **charge price `a`** (what we bill other
teams, as the handyman) and an **acceptance limit `b`** (the most we pay when
another team bills us, as the insurer). The platform then matches every team
against every other team in both roles and settles each line against a secret
**fair value `t`** set by claims experts. Money flows team to team (zero-sum).
**We never talk to other teams**: we only submit numbers, and the platform does
all the matching.

## The three checks behind `t`

Each line is legitimate only if it is:
1. **Covered** by the policy. Excluded items have `t = 0`.
2. **Related** to the reported damage. A burst bathroom pipe doesn't explain new kitchen cabinets.
3. **Reasonably priced.** The line total (quantity × unit price) is within what an expert would accept.

## Payoffs per line, per pair of teams

| | `a ≤ t` (fair) | `a > t` (inflated) |
|---|---|---|
| **`a ≤ b`, accepted** | insurer pays `a` to handyman | insurer pays `min(a, c)` to handyman |
| **`a > b`, rejected** | insurer pays `1.5·a` (wrongful rejection) | nothing flows (fraud caught) |

- `c` is a secret payment cap per line: `c ≥ 4t`, with some absolute floor. It stops one absurd charge from winning.
- **Not submitting a line counts as `a = 0, b = 0`.** That earns nothing and rejects every incoming bill, so we would pay 1.5× on all the fair ones. Never miss a round.
- **Always submit the gross line total**: quantity × unit price, VAT included, in EUR (German invoices: *brutto Gesamtbetrag*). Never net, never per unit.
  Example: 18 m² × €50 × 1.19 = €1,071.

## What the payoffs mean per role

- **Handyman (`a`):** a fair charge (`a ≤ t`) earns `a` from every opponent who accepts it and `1.5·a` from every opponent who rejects it. An inflated charge earns `min(a, c)` from opponents who accept it and nothing from those who reject it.
- **Insurer (`b`):** accepting a bill costs `a` (at most `c` if inflated). Rejecting costs `1.5·a` if it was fair and 0 if it was inflated.
- How `a` and `b` are chosen is strategy-dependent; see `docs/agents/04-strategy-math.md` for the quantities involved.

## Schedule and logistics

- **Rounds:** 100 games (IDs 1–100) every **13 min 20 s**, from **14:00 Sat 21 Nov to 12:00 Sun 22 Nov 2026** Munich time (13:00–11:00 UTC). That matches the 100 case files plus test case 0. The bot has to run unattended overnight.
- **Per round:** the game appears in `GET /api/games/list`, then its key is released at `start_time` and we have **60 s** to decrypt, analyse and submit. We can resubmit as often as we like; the last submission before the deadline counts.
- **Case files:** all 101 encrypted `.zip` files are already downloaded (Google Drive folder). Each needs that round's key.
- **Test:** game 0 is always open and stores nothing. Use it to test the full pipeline.
- **Leaderboard and upcoming games:** https://c2f.public.quantco.cloud/leaderboard/
- **Help:** Discord **#quantco**; Marvin, Moritz and Simon (also Carolin Thomas) from QuantCo. Room 1200.
- **Prize:** AirPods and merch.
- **Starter kit:** `starter_script.py` plus `pixi.toml` (Python 3.14, `requests`, `openai`, `p7zip`). An `OPENAI_KEY` is expected, so check whether QuantCo provides one.

## Timing: how long we have and how often

- **We have 60 seconds per case,** counted from the game's `start_time`. The encrypted zip is already on disk; the clock starts when the key is released. Within those 60 s: fetch the key, decrypt, analyse, submit. A `PUT` after the window is refused with `403` ("game has already ended").
- **A new game starts every 800 seconds = 13 min 20 s** (not 15 min). The organisers fit 100 games between 14:00 today and 12:00 tomorrow: 22 h = 79,200 s, divided into 99 gaps = 800 s. The slides round this to "~13 min".
- **Formula:** `start_time(N) = 2026-11-21 13:00:00 UTC + (N − 1) × 800 s`. Munich time is UTC + 1.

| Game | Start (Munich) | Start (UTC) |
|---|---|---|
| 1 | Sat 14:00:00 | 13:00:00 |
| 2 | Sat 14:13:20 | 13:13:20 |
| 3 | Sat 14:26:40 | 13:26:40 |
| 4 | Sat 14:40:00 | 13:40:00 |
| … | every 13 min 20 s | |
| 100 | Sun 12:00:00 | 11:00:00 |

**One cycle (13 min 20 s):**

```
0:00 ─ start_time: key released ─┐
       fetch key, decrypt,         │  60 s: the only time we can submit
       analyse, PUT (repeat OK)   │
1:00 ─ window closes ────────────┘
       platform settles, leaderboard updates
1:00 – 13:20  idle; then the next game starts
```

So the bot works one minute out of every thirteen and must be reliable for 22 hours, overnight included.

## The API

*Source: `API_HANDBOOK.md` and `starter_script.py` from the organisers' zip, plus slide 7 of the Deep Dive.*

- **Base URL:** `https://c2f.public.quantco.cloud`
- **Authentication:** every call needs the header `X-API-Key: <our team key>`. We get the key when we register the team. It is unique, cannot be changed, and must stay inside the team.
- **Exactly three endpoints exist.** There is no endpoint for downloading cases: the encrypted zips come from Google Drive, and the API only gives us the password.

### 1. `GET /api/games/list`: which rounds exist and when they start

Request: no body.

Response: every game with its ID and start time in UTC (`Z`):
```json
[
  { "id": 1, "start_time": "2025-06-01T12:00:00Z" },
  { "id": 2, "start_time": "2025-06-01T12:05:00Z" }
]
```
Game `0` is the permanent test game. It is always open and stores nothing.

### 2. `GET /api/games/{game_id}/key`: password for that round's zip

Only works **after** the game's `start_time`.

Response:
```json
{ "decryption_key": "secret123" }
```
Errors: `403` the game has not started yet · `404` no such game.

This is **where the encryption key comes from**. Only this endpoint provides it, and
only from `start_time` onward. Don't call it repeatedly before then (fair play: no
probing); wait until `start_time`, then retry briefly if you get a `403`.

Then decrypt locally: `7z x case_NNN.zip -p<decryption_key>`.

Try it right now with the always-open test game 0:
```sh
export TEAM_API_KEY=...            # never commit this
curl -H "X-API-Key: $TEAM_API_KEY" https://c2f.public.quantco.cloud/api/games/list
curl -H "X-API-Key: $TEAM_API_KEY" https://c2f.public.quantco.cloud/api/games/0/key
7z x case_000.zip -p<decryption_key> -ocase_000/
curl -X PUT -H "X-API-Key: $TEAM_API_KEY" -H "Content-Type: application/json" \
     -d '[{"index":1,"charge_price":50.0,"acceptance_limit":80.0}]' \
     https://c2f.public.quantco.cloud/api/games/0/submissions
```
For a real game, use its ID (1–100) and, most likely, the matching `case_NNN.zip`
(game 7 → `case_007.zip`). Confirm the mapping on the first real round.

### 3. `PUT /api/games/{game_id}/submissions`: send our numbers

The body is a JSON array with one object per invoice line. `index` is the line number on the invoice. Both prices are **gross line totals in EUR**.
```json
[
  { "index": 1, "charge_price": 50.0,  "acceptance_limit": 80.0 },
  { "index": 2, "charge_price": 120.0, "acceptance_limit": 150.0 }
]
```

The response echoes what was stored:
```json
[
  {
    "game_id": 1,
    "team_id": 3,
    "line_item_index": 1,
    "charge_price": 50.0,
    "acceptance_limit": 80.0,
    "submitted_at": "2025-06-01T12:00:30Z"
  }
]
```

Rules:
- **Last write wins.** We can submit as often as we like while the game is running. Each submission overwrites earlier values for the same lines (an "upsert").
- **Omitted lines count as `charge_price = 0`, `acceptance_limit = 0`, and they still take part in the game.** Leaving a line out does not opt us out of it.
- Both values must be **finite and ≥ 0**.
- A team created after a game started cannot play that game.

Errors:

| Code | Meaning |
|---|---|
| `401` | Missing or invalid API key |
| `403` | Game not started yet, game already ended, or our team was created after the game started |
| `404` | Game not found |
| `422` | A value is negative or non-finite (NaN or ∞) |

Game 0 accepts any well-formed JSON, so it is the place to test the submission format.

### Finding the next game

There is **no "next game" endpoint**, but none is needed because the whole schedule is published:
- `GET /api/games/list` (team key): the next game is the first one whose `start_time` is after now. Our bot should use this.
- `GET /leaderboard/api/games` (public): the same list plus a `status` field (`scheduled`, …).
- The leaderboard page embeds the next game's start time (`nextGameStart`), but not its ID.
- Or calculate it with the formula in *Timing*.

Re-fetch the list now and then in case the organisers change the schedule.

### What the API does *not* give us

- **No way to read our submission back later.** Only the reply to the `PUT` shows what was stored, so check it each time and log it.
- **No case details:** no number of lines and no file names. Those come from the decrypted zip.
- **No case downloads.** The zips come from Google Drive; the API only gives us the password.
- **No early access** to the key or the case.
- **Nothing about other teams until a game is finished,** and then only through the leaderboard.

### What the starter script does (`starter_script.py`)

A minimal template of the flow above, using game 0:
1. Reads `TEAM_API_KEY` from the environment, or prompts for it.
2. `GET /api/games/list`, prints every game, and picks `games[0]` (the test game).
3. `GET /api/games/0/key` and prints the decryption key. Decrypting is left as a `TODO`.
4. Builds two hard-coded dummy lines. Pricing is left as a `TODO`.
5. `PUT /api/games/0/submissions` and prints the stored values.

Each request stops the script if the status is not 200. It does **not** decrypt, read the
case, schedule rounds, or retry; we have to build all of that. Small quirk: `BASE_URL` ends
in `/` and the script adds `/api/...`, so URLs contain `//api`. That works, but our own code
should avoid it.

Run it with:
```sh
pixi install                                       # Python 3.14, requests, openai, 7-Zip
TEAM_API_KEY=... pixi run python starter_script.py
```
The organisers also mention an `OPENAI_KEY` environment variable for LLM use, but the
starter script doesn't use it yet.

### Live dashboard: the leaderboard (public, no key needed)

**https://c2f.public.quantco.cloud/leaderboard/** is a live page with a countdown to the
next game and six tabs. It reads from a public, read-only JSON API at
`/leaderboard/api/...`, which needs no API key. Checked 2026-11-21, before game 1:

| Tab | What it shows | JSON behind it |
|---|---|---|
| **Standings** | Overall ranking | rendered directly into the page |
| **Performance** | For one team. As issuer: income, number of claims, % accepted. As reviewer: costs, reviews, % accepted, rightly accepted, wrongly accepted, correctly rejected, wrongly rejected (penalties). Plus net. | `GET /leaderboard/api/performance?team=<name>` |
| **Games** | Net per team per game (the 20 most recent games as columns) | `GET /leaderboard/api/matrix?page=1&game_limit=20` |
| **Matchup** | One team against each opponent, net per game | `GET /leaderboard/api/matchup?team=<name>&page=1&game_limit=20` |
| **Transactions** | For a finished game and a team: every transaction — line item, issuer, reviewer, accepted ✓/✗, amount. Can filter by line item. | `GET /leaderboard/api/transactions?game_id=<id>&team=<name>&page=1[&line_item=<n>]` |
| **All Games** | Every game with its start time and status (`scheduled`, …) | `GET /leaderboard/api/games?page=1` (also `completed_only=true&page_size=1000`) |

**The real schedule (from `/leaderboard/api/games`):** 100 games, IDs **1–100**, every
**13 min 20 s** (800 s). Game 1 starts **2026-11-21 13:00 UTC (14:00 Munich)** and game 100
**2026-11-22 11:00 UTC (12:00 Munich)**. Each game is open for **60 s**. Presumably game N
uses `case_NNN.zip`, and case 000 is the test game 0.

**Why it matters for us:**
- **Monitoring:** after each round, check our net, our acceptance rates, and our wrongful-rejection count. That tells us whether our `b` is too strict or too loose, and whether our `a` gets rejected.
- **Learning about `t` after a game:** the transaction amounts give away the result. A rejected bill with amount `1.5·a` was fair (`a ≤ t`). A rejected bill with amount 0 was inflated (`a > t`). An accepted bill shows the charge `a`. Collected across all teams for one line, this narrows down where `t` was, which could help calibrate our price model for later rounds.
- ⚠️ **Fair-play grey area:** the rules forbid "reading other teams' submissions" and "extracting the secret thresholds". This data is officially public, but scraping it systematically to work out thresholds could count as either. **Ask QuantCo on Discord before automating it.** Looking at our own performance is clearly fine. Either way, request it gently (cache it; finished games never change) and never hammer it.

### One round end to end

```
GET  /api/games/list                  → find the next game id + start_time
     (wait until start_time)
GET  /api/games/{id}/key              → decryption_key
7z x case_NNN.zip -p<key>             → policy.txt, description.txt, invoices.pdf, photo*
     analyse, estimate t, choose a and b per line
PUT  /api/games/{id}/submissions      → within 60 s; send a quick safe version first, then refine
```

## How we are graded

| Part | Weight | How |
|---|---|---|
| Tournament result | **70 %** | Rank by cumulative net payoff across all games. 1st place = 70 points, then linear by rank down to 0 for last. |
| Write-up (≤ 1 page) + pitch | **30 %** | Jury, 0–30 points: **method & uncertainty** (how we estimate `t` and derive `a`, `b`), **evidence** (why we trust it), **resourcefulness** (smart and economical, "no token maxing"), **reliability** (always submits within 60 s), **clarity & honesty** (claims match results; weaknesses stated). |
| Fair play | pass / fail | Breaking a rule means disqualification. |

Because the tournament score depends on **rank, not amount**, consistent and
reliable play beats a fragile high-variance approach.

## Fair-play rules (disqualification if broken)

- No collaboration with other teams on prices, limits, strategy or case analysis.
- The API key stays inside the team. Never submit for another team.
- No attacking or probing the platform: no early keys, no reading others' submissions, no extracting thresholds, no overloading the API.
- Inside the team, anything goes: LLMs, tooling, manual work, research.

## Facts we found in the case files

- 101 archives: `case_000` (test) to `case_100`. They are AES-encrypted zips, so they need `7z` or `pyzipper`; Python's built-in `zipfile` can't open them.
- Every case has `policy.txt`, `description.txt` and `invoices.pdf`. Photos are **not** named `images.png` as the docs say. The names vary: `photo.jpg`, `photo.png`, `photo.jpeg`, `photo1.png`/`photo2.png`/…, and one case (`case_045`) has none.
- **Policies are long:** a median of about 56 KB (roughly 14k tokens) of text. **They also repeat:** many cases have byte-identical policy sizes (groups of 2–5 cases), so there are about 50 distinct policies. Caching each parsed policy can save time in later rounds.
- Descriptions are short (0.2–4 KB). Invoice PDFs are 14–75 KB. Photos are up to 31 MB, so downscale them before sending to any vision model.

## Open questions to verify early

- Does game ID *N* correspond to `case_NNN.zip`? Check on the first real round.
- Are invoice PDFs text-extractable, or do they need OCR? How are line indexes numbered (the examples start at 1)?
- What VAT rate do the invoices use (19 % standard in Germany; 7 % reduced)? Are any invoices in a different currency or country?
- Does the leaderboard show per-game results that we could use to calibrate between rounds?

See `docs/agents/` for the technical briefing that development agents use.
