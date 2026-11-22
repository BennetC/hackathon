"""Who sits on the council, what each agent focuses on, and the in-game time budget.

Every agent reviews the WHOLE claim (all lines: coverage, causation and price), but leans
on one aspect so the council's errors are less correlated. The chief reads all verdicts and
decides coverage and which agents' prices to trust; code computes the numbers.

Bump an agent's `version` (or COUNCIL_VERSION for the chief or the roster as a whole)
whenever its model, effort or prompt changes: calibration only uses history recorded under
the current versions, so a changed agent starts again from the prior.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentSpec:
    id: str                 # short stable name, used in history and calibration keys
    provider: str           # make_llm provider: claude_code | codex | antigravity | anthropic
    model: str | None
    effort: str | None
    focus: str = ""         # the aspect this agent leans on
    version: str = "1"
    photos: bool = True     # attach the case photos
    max_tokens: int = 16000

    @property
    def key(self) -> str:
        return f"{self.id}@{self.version}"


POLICY_FOCUS = """Your focus: the POLICY. Read the insurance terms closely: insured perils,
insured objects (building vs contents), exclusions, sub-limits, waiting periods, and which
ancillary costs (leak detection, drying, tear-out and restoration, disposal, travel) are
covered. For each line, cite the clause that decides cover. You still price every line and
check it against the damage report and photos."""

# Second Opus instance: same model as the policy agent, so it must differ in METHOD, not
# just in topic, or the two make the same errors and their blend adds nothing. It works
# like an independent cost estimator: own quantities first, then a bottom-up build of each
# line. A consistent lean (high or low) is fine, since the drift fit corrects it per agent.
COSTING_FOCUS = """Your focus: COSTING, as an independent cost estimator who prepares a
counter-quote for this repair. Work in this order:
1. From the damage report and the photos alone, decide what work the reported damage really
   needs and in what quantity (area, hours, days, pieces).
2. Compare that with each invoice line's quantity and unit. Where they differ, price YOUR
   plausible quantity and lower `related` for the excess.
3. Build each line's price bottom-up from its components: labour hours x the hourly rate of
   that trade, materials x unit cost, equipment or rental days x day rate, disposal and
   travel where the line includes them. Use market rates of the invoice's country, then
   add the VAT rate the invoice uses. Do not price by what such a line "usually" costs on
   an invoice; build the number.
You still judge cover and causation for every line."""

EVIDENCE_FOCUS = """Your focus: the EVIDENCE. Compare the photos, the damage report and the
invoice: does each line belong to the damage that is reported and visible (right room,
right object, fresh damage rather than wear or old damage)? Flag lines that look unrelated,
like upgrades, or like they belong to a different job; those are worth 0. You still
judge cover and price every line."""

AGENTS: tuple[AgentSpec, ...] = (
    AgentSpec("opus", "claude_code", "claude-opus-5-5", "high", POLICY_FOCUS, version="3"),
    AgentSpec("opus_cost", "claude_code", "claude-opus-5-5", "high", COSTING_FOCUS, version="2"),
    AgentSpec("neon", "antigravity", "gemini-4-neon", "low", EVIDENCE_FOCUS, version="3"),
)

# The chief decides coverage and which prices to trust; no photos, so it answers quickly.
CHIEF = AgentSpec("chief", "claude_code", "claude-opus-5-5", "medium", photos=False)

# Bump when the chief, its prompt or the roster changes.
COUNCIL_VERSION = "4"   # 2: neon low, compact output; 3: Codex -> second Opus (costing)
#                         4: fair_mid before deductibles / reductions / sub-limits

# ---- in-game time budget (seconds) -----------------------------------------------------
MAX_PHOTOS = 6
CHIEF_BUDGET_S = 18.0   # agents get everything up to (deadline - CHIEF_BUDGET_S)
MIN_CHIEF_S = 6.0       # skip the chief if less than this is left
DEADLINE_SLACK_S = 1.0  # return this long before the pipeline's hard deadline
