# Prompt-ideas brief (read ~/dev/quantco-runner/research/BRIEF.md first; its Hard rules apply in full)

Goal: we will add a THIRD group of researchers (2 Fable 5.2 + 1 Opus 5.5) next to our current 6 sources
(v1: 3 Opus sessions; v2: 1 Fable + 2 Opus). The new group gets a different SYSTEM PROMPT so its answers are
meaningfully different (less correlated errors, less systematic bias) and add information when pooled / judged.
Later we run them on all past cases in order (a session per model, with per-game market feedback after each case,
like `v2_train.py`), then test judges that read all 9 answers and math combinations.

Current researcher prompt: `opus_case.py` `build_prompt()` (invoice prices are BLANK; models estimate fair gross line
totals with low/high and covered/related flags; output schema `opus_case.SCHEMA`). Training/feedback flow:
`v2_train.py`, `session_backtest.py` (GOAL, feedback_line). Data: see research/BRIEF.md (answers per source, market
bounds lo/hi in live_eval/tx_cache.pkl, research/opponents/tx_30_34.pkl, research/s4-imitate-404/tx_35.pkl).
Known: our estimates run 20-40% below the market's proven-fair level on covered lines (labour, plumbing, parts);
404's lead comes from ~10 large lines where all our sources were 30-80% off; the 6 sources' errors are highly correlated.
Earlier research reports in research/*/REPORT.md.

Rules: no model calls (data analysis only), write only in research/prompt-<your-angle>/. Must be leakage-free:
anything a prompt includes about prices must come only from games before the one being priced.

Deliver research/prompt-<your-angle>/PROPOSAL.md (short):
1. Evidence from the data that motivates your angle (numbers).
2. The full SYSTEM PROMPT text you propose (ready to paste, <= ~500 words), plus any per-game context or feedback
   text it needs, and whether it fits Fable, Opus or both.
3. Why its answers should differ from the current 6 (which errors it should fix / decorrelate), the expected effect,
   and the risks (e.g. overpricing -> inflated charges lose the whole line).
4. How to check after the runs that it helped (metric vs market bounds, correlation with the current sources).
Final message: the prompt in one paragraph summary + key evidence numbers.
