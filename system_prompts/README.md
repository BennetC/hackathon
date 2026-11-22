# System prompts

Every prompt the QuantCo runner sends, extracted from [`quantco_runner/`](../quantco_runner/). Each folder is named after the script that defines the prompt, and each file after its constant. The scripts remain the source of truth.

| Pipeline | Prompts | Used for |
| --- | --- | --- |
| Final appraiser, version 5 | [`pricing_analyst_v5_system_prompt.txt`](pricing_analyst_v5_system_prompt.txt) | System prompt for `v4_train.py` and `v5_train.py`. Same text as `quantco_runner/v4_system_prompt.txt` |
| Every case | [`opus_case/CASE_MESSAGE_TEMPLATE.txt`](opus_case/CASE_MESSAGE_TEMPLATE.txt) | The per-case message. The placeholders stand for the policy, the damage description and the invoice |
| First persistent panel | [`session_backtest/`](session_backtest/), [`fable_vs_opus/RULES.txt`](fable_vs_opus/RULES.txt) | Standing rules, the feedback goal reminder and the compaction instruction |
| Decider | [`decider/RULES.txt`](decider/RULES.txt), [`live_opus/`](live_opus/) | Decider rules, the correction from Games 1 to 19, extra decider rules and decider compaction |
| Second live pipeline, from Game 30 | [`v2_record/`](v2_record/), [`v2_train/MUNICH.txt`](v2_train/MUNICH.txt) | Researcher and judge rules, the 30-second rule, rule updates sent mid-tournament, and the Munich price reference |
| Third researcher group | [`v3_train/`](v3_train/), [`v3_group/`](v3_group/), [`v3_judges/`](v3_judges/) | Core rules, the two framing variants, the recency rule and the judges' source notes |
| Offline experiments | [`book_test/`](book_test/), [`memo_writer/`](memo_writer/), [`pricing_writer/`](pricing_writer/), [`persona_tests/`](persona_tests/) | Pricing-book, case-memo and persona experiments |

[TRAINING.md](../docs/TRAINING.md) explains how these prompts were used in training.
