"""Tests for the generic `Strategy` super-class, `StrategyResult`, and `Council`."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from claimbot.config import Settings
from claimbot.models import Case, LineItem, LinePrice
from claimbot.runner import pipeline
from claimbot.strategies import (
    Council,
    LineValuation,
    REGISTRY,
    Strategy,
    StrategyResult,
    load_strategy,
)
from tests.conftest import FakeApi


def test_council_is_registered(env):
    assert list(REGISTRY.keys()) == ["council"]
    strat = load_strategy("council", env)
    assert isinstance(strat, Council) and isinstance(strat, Strategy)
    assert strat.name == "council"
    # Empty invoice: nothing to price, no LLM call.
    case = Case(game_id=1, directory=Path("."), policy="p", description="d",
                invoice_text="", lines=[])
    res = strat.price(case, time.time() + 30)
    assert isinstance(res, StrategyResult) and res.quotes == []


def test_old_strategies_are_removed(env):
    for removed in ("baseline", "panel", "live_neon"):
        with pytest.raises(ValueError, match="unknown strategy"):
            load_strategy(removed, env)


class _StructuredStrategy(Strategy):
    name = "structured"

    def price(self, case, deadline_ts, publish=None) -> StrategyResult:
        assert self.remaining_s(deadline_ts) > 0
        quotes = [LinePrice(li.index, 120.0, 180.0) for li in case.lines]
        vals = [
            LineValuation(index=li.index, covered=True, related=True, low=120.0, fair=150.0, high=210.0)
            for li in case.lines
        ]
        if publish:
            publish(StrategyResult(quotes=[LinePrice(case.lines[0].index, 100.0, 150.0)]))
        return StrategyResult(quotes=quotes, valuations=vals, trace={"model": "test-model"})


def test_pipeline_consumes_strategy_result_quotes_valuations_and_trace(env):
    api = FakeApi()
    report = pipeline.run_game(7, env, api, _StructuredStrategy(env))
    assert report.ok and report.final_submitted
    # Fallback + interim + final
    assert len(api.submissions) == 3
    assert api.submissions[-1] == [
        {"index": 1, "charge_price": 120.0, "acceptance_limit": 180.0},
        {"index": 2, "charge_price": 120.0, "acceptance_limit": 180.0},
    ]
    trace_file = Path(report.run_dir) / "strategy_trace.json"
    assert trace_file.is_file()
    trace = json.loads(trace_file.read_text())
    assert trace["model"] == "test-model"
    assert len(trace["valuations"]) == 2
    assert trace["valuations"][0]["low"] == 120.0

