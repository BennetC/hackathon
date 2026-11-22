# Synthesis brief: best formula from the 10 independent formula agents

Read research/formula9/BRIEF.md and research/BRIEF.md first: all Hard rules apply (read-only, never submit, never touch
the live runner or any state.json, no model calls). Write ONLY under research/formula9/<your folder>/.

Read ALL ten reports and their code: research/formula9/agent-1 .. agent-10 (REPORT.md + scripts). Collect every idea
(bases: group medians, min / median / geometric mean of groups, group-3 anchor and caps, judges' charges, disagreement
shading; limits: ~0.97-1.00 x consensus, exp(-0.55 s) shading; coverage gates) and build the best rule out of them.

What the 10 found (summary, check it yourself):
- Every charge multiplier sits near a cliff (~0.94-0.96); 0.90-0.93 x a cautious consensus is the safe zone.
- A cautious charge raises the worst case mainly through a few big lines (games 29, 33) and gives up best case/midpoint.
- The acceptance limit b ~ 0.97-1.00 x a cautious consensus beat both baselines on every split for several agents;
  agent-7: Ruben 3 groups' charge + b = 0.98 x lower-median of {3 group medians, judges' midpoint} improved both
  baselines on every split. Nobody tested every combination of the best charge with the best limit.
- On recent games (36-46) group 3 alone (a = 0.93 x G3 median) is strongest; rules that pull the price down to the old
  groups lose there. The live Ruben rule's high best case comes mostly from charging uncovered lines at the old
  judge's charge (not approved by Daniil).

Protocol: tune exact values on ODD games only; report EVEN games (validation) and even 36-46. Be honest that the even
games are no longer blind (the agents reported even numbers, so choosing among their ideas uses that information):
therefore also report the brand-new games 47-50 (fetch their market data read-only via session_backtest.bounds /
fable_vs_opus.tx_all into your folder; games 49-50 have live group-3 answers in backtest/v2/state.json "v3_answers";
the 4 judges exist only for games <= 46, so rules that need them fall back without judges there).
Prefer simple, explainable rules (few parameters); include the robustness checks (each value +-0.02/0.05, bootstrap).
Also evaluate the minimal change: keep Ruben (2 or 3 groups) charge exactly, replace only the limit.

Deliver REPORT.md: the recommended rule in exact maths with reasons, all splits (odd / even / even 36-46 / games 47-50),
worst/best/midpoint vs Ruben 2 groups (live) and Ruben 3 groups, robustness, and which idea from which agent survived.
Final message: the recommended rule + key numbers + whether to switch live now.
