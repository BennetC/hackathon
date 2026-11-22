# How training works

**No model weights change.** "Training" here means walking a fresh language-model session through every finished game in order. After each case, the session sees what the market proved about each line. The session keeps that history in its context and carries it into the live games. Everything is done through the Claude Code CLI (`claude -p`) with persistent sessions (`--session-id`, then `--resume`).

The code is in [`quantco_runner/`](../quantco_runner/). Its scripts expect a local `.env` with `TEAM_API_KEY=...` and, for the second judge, a `.openai_key` file. Neither is committed. Case archives, decrypted cases and run state also stay local.

## 1. Labels from the market

Every finished game publishes each team's settled trades on the public leaderboard API. `session_backtest.bounds()` turns them into an interval for each invoice line:

- **Floor.** A rejected bill that the insurer still paid proves the charge was fair. The floor is the largest such charge, which is the payment divided by 1.5.
- **Ceiling.** A rejected bill that paid nothing proves the charge was inflated. The ceiling is the smallest such charge.
- **Accepted bills are ignored.** Acceptance says nothing about the fair value.

So each labelled line has floor ≤ t < ceiling, where t is the hidden fair value. Lines without a rejection get no label. These bounds are the only training signal.

## 2. The training loop

`v3_train.py` is the clearest version. For each finished game g, in order:

1. Build the **market price book** from games before g only. It lists unit prices proven fair or inflated, newest game first. It keeps all hourly lines, lines bounded tightly on both sides, and lines from the same trade as game g.
2. Add a **policy note** when game g's policy is identical or 95% similar to an earlier case's, with that case's bounds.
3. Send each session one message. It holds the photos, the feedback for game g − 1, the price book, the policy note and the case text: policy, damage description and the invoice with blank prices.
4. Each session must answer within 30 seconds with JSON for every line: covered, related, fair gross total, and low and high estimates. A late answer is dropped, and the next message starts with a "too slow" note, so sessions learn the time limit.
5. Score the answers against game g's bounds and save everything to the run's `state.json`.
6. The next message gives each session its own feedback for game g, line by line: market floor and ceiling, the same per unit, its own fair value, and a verdict. The verdict says the estimate was too low, too high or consistent with the market.

**No look-ahead.** The price book, the policy note and the feedback only use games before the one being priced. Feedback for game g arrives only after the session has answered game g.

Large sessions are compacted between games with a fixed instruction. It keeps each past case's damage type, the deciding policy clauses, our estimate and the feedback range per line, and drops full policy texts.

## 3. The training runs

| Script | Sessions | What changed |
| --- | --- | --- |
| `session_backtest.py` | 3 Claude Opus 5.5 | First version. The low estimate is defined as the charge, and feedback says whether it was safe or risky. Used to bootstrap the live persistent panel in `live_opus.py`. |
| `v2_train.py` | 1 Claude Fable 5.2, 2 Opus 5.5, optional Gemini researchers, plus a Fable judge | Adds a calibration table, a track record per source and a judge that sees answers under neutral labels. `openai_judge.py` adds a second judge on GPT-6.2 Astra. |
| `v3_train.py` | 2 Fable 5.2 and 1 Opus 5.5 | New prompts from the prompt research in [`research/`](../research/): bottom-up decomposition, predicting the market's fair value without shading, and coverage only through the flags. Adds the market price book. |
| `v4_train.py`, `v5_train.py` | 1 Fable 5.2 | The rules move into a real system prompt, [`quantco_runner/v4_system_prompt.txt`](../quantco_runner/v4_system_prompt.txt), also in [`system_prompts/`](../system_prompts/). v5 fixes contract limits, the "newest comparable row wins" rule and feedback wording that invited overreacting to one case. |

Each run writes to its own directory under `backtest/`, never submits and never touches the live sessions.

## 4. From trained sessions to live prices

- `live_opus.py` runs the persistent panel live: three Opus sessions bootstrapped by `session_backtest.py`. Before each release it catches up on any game they have not seen and feeds back every newly settled game. At release it asks for the new case with a 40-second timeout and combines the answers.
- `v2_record.py` is the second live pipeline, from Game 30. It runs the researchers in parallel with a 40-second limit and a judge that must finish by 55 seconds. It submits the pooled formula's prices at 56 seconds. `v2_forever.sh` runs it game after game.
- `formula.py` holds the pooled pricing formula. The charge is 0.92, 0.84 or 1.16 times the median fair value, depending on how far the sources agree. The limit is 1.04 times the lowest fair value. [`research/robustness/REPORT.md`](../research/robustness/REPORT.md) audits it with walk-forward fits, leave-one-game-out fits and a bootstrap.
- `bench.py` pushes each strategy's prices to FDN Bench. There, each strategy is scored against the same settled games.

## 5. Offline research

[`research/`](../research/) holds the reports from research agents. The `prompt-*` folders are prompt proposals that fed v3 to v5. `formula9/` and `synth-*` are pricing-formula searches, and `robustness/` is the overfitting audit. `charge-side/`, `acceptance-side/` and `fdn-gap/` analyse where FDN lost money against other teams. [`research/BRIEF.md`](../research/BRIEF.md) is the shared brief.
