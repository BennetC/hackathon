# Mac runner and opening pricing baseline

Bennet's live runner, Strategy A pricing and replay tools. The files are at the repository root: `runner.py`, `pricing.py`, `strategy.py`, `valuation.py`, `case_pipeline.py` and the related tests.

## Game 1 pricing

Run the dependency-free Strategy A smoke test with Python 3.13:

```sh
python3 pricing.py examples/game1_valuation.json
```

Expected output: covered line `1` has charge `11305` and limit `11900`, and excluded line `2`
has charge and limit `0`. The runner can import `price_game(game)` for ordered
`(item_id, charge_cents, limit_cents)` tuples, or pass valuation JSON through the
CLI. The runner converts these internal results to QuantCo's documented wire
format. The CLI does not submit requests.

Set `game_id` and `expected_item_ids` from the parsed invoice and supply one entry
in `items` for every expected ID. Each item has `item_id`, `quantity`, `unit`,
`coverage`, `relevance`, and `evidence`. Coverage and relevance can each be
`yes`, `no` or `uncertain`. The model returns both prices as zero for explicit
exclusions and unrelated repairs. It rejects missing, unexpected or duplicate IDs.

For eligible or uncertain rows, supply `threshold_samples_gross_cents` as 100
sorted, nonnegative integer estimates of the **whole-line price including VAT**.
Include zeros to represent the chance of exclusion or unrelated damage. The strategy
sets the limit at the 33rd sample and caps the 25th-sample charge at 5% below
that limit. This puts uncertainty headroom on what we charge, while preserving the
limit that helps avoid the 1.5× penalty for rejecting a fair incoming quote. The
5% minimum gap (rounded up to cents) is a tunable starting value, not a rule or
an empirically calibrated optimum. Use `--spread-bps` or the equivalent keyword
argument to change it. Use cents throughout and preserve invoice order.

If valuation samples aren't ready, provide an evidence-based net unit price band
as `unit_price_band_net_cents: [low, typical, high]`, along with `quantity` and a
fractional `vat_rate` (e.g. `0.19`). The model interpolates between the band
values, multiplies by quantity, and applies VAT once. For uncertain rows also
provide `eligible_samples` (0–100), the estimated number of draws where the item
is both covered and relevant. The remaining draws get zero. The example uses a
flat price band to show the arithmetic. Use the actual case evidence for live prices.

## Live tournament runner

Install the case dependencies in the Python 3.13 environment described below
and stage the encrypted `case_NNN.zip` files in a single directory. The runner
uses `TEAM_API_KEY` or the private local file `~/.config/fdn-quantco/team.key`.
Pass `--key-file` to use a different private file. The runner reads the official
UTC schedule from QuantCo and displays release times in Europe/Berlin.

Verify the API with the permanent test game first.

```sh
.venv/bin/python runner.py --game 0 --no-llm --archives "$HOME/Downloads/Cases"
```

Choose the first game the runner owns. This command starts at Game 4 and
continues through the last scheduled game. On macOS, `caffeinate -is` keeps the
machine awake while it is connected to power.

```sh
caffeinate -is .venv/bin/python runner.py --from-game 4 --archives "$HOME/Downloads/Cases"
```

Set `OPENAI_KEY` in the runner's environment to enable one structured request
per round. `OPENAI_MODEL` defaults to `gpt-4.1-mini`. The model receives the
policy, claim and all parsed invoice rows. The runner applies deterministic
gross pricing when the model is unavailable and keeps fallback values for
individual rows with invalid or missing model estimates. The default VAT rate
is 19% and can be configured with `--vat-rate`.

The first complete payload targets release plus 35 seconds. The runner uses
the official release plus 60 seconds as the hard cutoff, with a two-second
default safety margin. It submits one set of prices, with one additional attempt
allowed only after a confirmed connection failure before dispatch. The local
lock coordinates submission attempts on the same macOS user account.
A restart uses the same command and reads the round journals in
`~/.cache/fdn-quantco/`. A persisted write without a verified receipt blocks
another attempt for that game. The server receipt must match every row,
both prices and the game. After Case 0, the runner also checks the team ID
against its verified test receipt.

The journals contain UTC timestamps, stage timings, valuations, payloads,
and acknowledgement metadata. The console reports each round's result and
the next release. On macOS, the runner also posts local failure notifications.

### Run with a teammate's analysis and pricing

Pass `--strategy /path/to/teammate_strategy.py` to use a teammate's final
prices for every selected game. The runner still waits for release, decrypts
the case, checks the full invoice, submits the prices, and verifies the receipt.
Assign one submission owner across the team before starting a live runner.

Write a Python adapter that reads one JSON object from stdin and writes one
JSON object to stdout. The runner starts a fresh process using its own Python
environment for each game. Install the strategy's dependencies in that
environment. Use trusted team code, since the strategy can read the decrypted
case and inherits the local environment with `TEAM_API_KEY` removed.

| Request field | Contents |
| --- | --- |
| `game_id` | Integer game ID to echo in the result. |
| `case_dir` | Absolute path to the extracted files, available while the live strategy runs. |
| `evidence` | `documents` with policy, damage and invoice text, `rows` with the parsed invoice, and `images` with paths relative to `case_dir`. |
| `expected_item_ids` | Invoice position IDs in required output order. |
| `budget_seconds` | Time available for the strategy, including its startup and response validation. |

Return `{"game_id": 0, "items": [{"item_id": 1, "charge_cents": 12345, "limit_cents": 13750}]}`
with one item for every expected position in order. Both amounts must be
nonnegative integer cents for the whole line, including VAT. The runner
converts them to the sponsor's euro fields. Keep stdout reserved for JSON.
A script failure, invalid prices or a result after release plus 32 seconds
skips submission for that game and the runner continues to the next release.

Replay Case 0 with the same strategy and validation using its cached key and
schedule from the read-only fetch below. Inspect `strategy-wire.json` and
`run.json` in the output directory. This replay makes no QuantCo requests.

```sh
.venv/bin/python replay_case.py 0 "$HOME/Downloads/Cases/case_000.zip" \
  --strategy /path/to/teammate_strategy.py --output .cache/quantco/replay/teammate-test
```

For continuous live use, replace `4` with the first game assigned to this runner.

```sh
.venv/bin/python runner.py --from-game 4 --archives "$HOME/Downloads/Cases" \
  --strategy /path/to/teammate_strategy.py
```

Run the tests to exercise the continuous loop against a mock QuantCo API.

```sh
.venv/bin/python -m unittest discover -s tests
```

## Read-only fetch and offline case processing

Keep the sponsor's originals under the ignored local directory
`.sponsor/quantco/`: `API_HANDBOOK.md` defines the API, `starter_script.py`
shows the official flow, and `pixi.toml` and `pixi.lock` are its reproducible
starter environment. Keep the Pixi files together and use
`pixi install --locked --manifest-path .sponsor/quantco/pixi.toml` to provision
that environment. The starter contains a live PUT. Read it as a reference for
this workflow, and use our separate GET-only client.

Install the local simulator's case dependencies:

```sh
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python -r requirements-case.txt
```

Fetch the schedule and permanent test case's released decryption key with
the runner's team key lookup. The client uses the handbook's GET endpoints and checks the listed
start time before requesting a key. It saves both responses locally without
printing the keys.

```sh
python3 quantco_fetch.py --game 0
```

Replay the organizer's staged Case 0 archive using the cached schedule and
released key. This command runs locally and writes case contents, evidence,
and results to a fresh ignored directory.

```sh
.venv/bin/python replay_case.py 0 ~/Downloads/Cases/case_000.zip \
  --output .cache/quantco/replay/game-0
```

The replay validates the archive name and encryption against the selected game
and verifies the complete sequence of position numbers across the invoice
pages. The parser handles the ruled `POS. / DESCRIPTION / AMOUNT / UNIT /
TOTAL` template, including wrapped descriptions and decimal quantities.
Unrecognized layouts fail with a validation error. Case 0 leaves the tax
rate and unit prices blank. The baseline uses the configured VAT fraction
(`--vat-rate 0.19` by default) and fixed net unit-price bands for hourly and
other work. Its coverage, relevance, and price estimates remain unverified.

The output directory includes the extracted case, the manifest, local evidence,
gross-cent prices, the wire array, and stage timings. The payoffs replay uses
the real invoice and a synthetic scenario with illustrative thresholds, caps,
and opponents. It does not measure tournament performance. Choose a new output
directory for each replay.

To build an evidence packet from an existing extraction and manifest:

```sh
.venv/bin/python case_pipeline.py inspect .cache/quantco/replay/game-0/case \
  .cache/quantco/replay/game-0/manifest.json > .cache/quantco/case-0-evidence.json
```

`inspect` produces a local evidence packet from `policy.txt`, `description.txt`,
`invoices.pdf` and optional `images.png` or JPEG photos. If needed, override the three
document paths with a `documents` object keyed by `policy`, `damage` and
`invoice`, and list photo paths in `photos`. All paths are relative to the
case directory. Scanned pages and photos can be reviewed from the extracted
files on the local machine. Keep case data, outputs and credentials in ignored
paths.

For manual or offline model analysis, use `--analysis-file` with a private
assessment JSON file.
The file contains an `items` array with one record per zero-based
`row_index` in the evidence packet, plus `coverage`, `relevance`,
`eligible_samples`, `unit_price_band_net_cents` and `evidence`. The
analysis may change estimates. Invoice IDs, quantities and VAT come from
the manifest. The program saves `baseline.json` first and writes any
valid refinement separately to `refined.json`, or to `candidate.json`
when there is no baseline. No case data is uploaded.

Preview the handbook's `index`, `charge_price`, `acceptance_limit` array
and replay both roles against local thresholds, caps and opponents:

```sh
mkdir -p .cache
python3 pricing.py examples/game1_valuation.json > .cache/smoke-prices.json
python3 simulate_local.py .cache/smoke-prices.json --scenario examples/smoke_scenario.json \
  --schedule .cache/quantco/games.json
```

Omit `--schedule` for a fully synthetic smoke run. The smoke prices and
scenario are synthetic, even when checked against the real Game 0 schedule.
QuantCo's read endpoints do not reveal the
true thresholds, caps or rivals' quotes for a case. The simulator never
submits its preview.

## Single-round submission rehearsal

Run the invoice and round integration tests with the local test environment.
The round tests use an injected fake HTTP transport and synthetic encrypted
case, so the organizer receives no requests.

```sh
.venv/bin/python -m unittest discover -s tests -v
```

`round_rehearsal.py` waits for the UTC release using wall time and derives
monotonic deadlines from that release, including after a late wake. It aims
to verify a complete baseline by +35 seconds. A valid local assessment can
start one overwrite before +50 seconds after the baseline is acknowledged.
The +60-second hard close bounds the overwrite acknowledgement. The lock and
sanitized journal block duplicate writes on restart after any write intent.
The rehearsal has no command-line sender. The timing and acknowledgement
checks here exercise the documented contract with the fake server.

## Before hacking starts

- Keep this repository private. Add only confirmed teammates with write access.
- Do not add challenge-specific solution code before the organizers open hacking.
- Follow the event's challenge, AI-tool, data and submission rules when announced.
- Keep credentials, personal data and proprietary code out of commits. Store
  local secrets in ignored `.env` files.
- No license has been granted by this setup. Ask the team before adding a license
  or publishing any part of the repository.

## Get ready

Accept your GitHub invitation, clone this repository, and complete the access
check in [CONTRIBUTING.md](CONTRIBUTING.md). Python and Node dependencies will be
chosen after the challenge is announced; no runtime setup is required yet.

Use `main` plus short feature branches and small pull requests. The proposed
rapid merge process and access check are in [CONTRIBUTING.md](CONTRIBUTING.md);
team agreement and each teammate's access check must still be confirmed.
