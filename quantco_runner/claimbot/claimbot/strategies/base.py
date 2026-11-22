"""Generic `Strategy` super-class and typed `StrategyResult` contract.

What a strategy returns and what happens with it in `claimbot/runner/pipeline.py`:
  1. `strategy.price(case, deadline_ts, publish=...)` returns a `StrategyResult`:
       - `quotes`: list of `LinePrice(index, a, b)` (gross EUR whole-line totals:
         `a` = charge price we bill rivals, `b` = max incoming charge we accept).
       - `valuations`: optional per-line `LineValuation` records (`covered`, `related`,
         `low`, `fair`, `high`, `reason`) for offline evaluation, auditing, and
         FDN Bench `/api/sweep` pricing sweeps.
       - `trace`: optional JSON-serialisable debug metadata (timings, token usage, raw calls).
  2. Downstream in `pipeline.py`:
       - Every quote is sanitized (`_money`: non-finite/negative clamped to `0.0`, rounded to cents).
       - Unknown line indexes (not present in `case.lines`) are dropped.
       - `quotes` are merged over the immediate fallback quotes: any line the strategy omits
         (including when a no-op strategy returns an empty `StrategyResult()`) keeps its
         fallback quote.
       - The merged list is sent via `PUT /api/games/{id}/submissions` and verified against
         QuantCo's echoed line indexes.
       - `trace` + `valuations` are persisted to `runs/game_NNN/<ts>/strategy_trace.json`.
  3. Optional `publish(quotes)` callback:
       - Calling `publish([...])` mid-run submits an interim PUT right away and saves those
         quotes so that if `price()` later times out, the interim quotes stand instead of
         reverting to the blind fallback.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

from claimbot.models import Case, LinePrice

if TYPE_CHECKING:
    from claimbot.config import Settings

PublishFn = Callable[[Iterable[Any]], None]


@dataclass(frozen=True)
class LineValuation:
    """Optional underlying valuation for one invoice line (for auditing & FDN Bench sweeps)."""

    index: int
    covered: bool | None = None
    related: bool | None = None
    low: float | None = None
    fair: float | None = None
    high: float | None = None
    reason: str = ""


@dataclass
class StrategyResult:
    """Structured output returned by `Strategy.price(...)`."""

    quotes: list[LinePrice] = field(default_factory=list)
    valuations: list[LineValuation] = field(default_factory=list)
    trace: dict[str, Any] = field(default_factory=dict)

    def to_trace_dict(self) -> dict[str, Any]:
        out = dict(self.trace)
        if self.valuations:
            out["valuations"] = [asdict(v) for v in self.valuations]
        return out


class Strategy(ABC):
    """Generic super-class for all Claim to Fame pricing strategies."""

    name: ClassVar[str] = ""

    def __init__(self, settings: "Settings"):
        self.settings = settings
        self.last_trace: dict[str, Any] = {}

    @staticmethod
    def remaining_s(deadline_ts: float) -> float:
        """Seconds remaining before the pipeline's hard strategy deadline."""
        return max(0.0, deadline_ts - time.time())

    @abstractmethod
    def price(
        self,
        case: Case,
        deadline_ts: float,
        publish: PublishFn | None = None,
    ) -> StrategyResult:
        """Price `case` before `deadline_ts` and return a `StrategyResult`."""

    def on_submitted(self, game_id: int, quotes: list[LinePrice], dry_run: bool) -> None:
        """Optional hook called once the final quotes are submitted (or would have been, in a
        dry run), even when `price()` timed out. Write logs here, off the critical path."""

    def on_game_settled(self, game_id: int, transactions: list[dict]) -> None:
        """Optional post-game hook: the listener calls it once our team's public settlement
        transactions for `game_id` are available (`claimbot settle` replays it)."""

    def close(self) -> None:
        """Release any resources (LLM workers, connections) held by this strategy."""

    def __enter__(self) -> "Strategy":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()
