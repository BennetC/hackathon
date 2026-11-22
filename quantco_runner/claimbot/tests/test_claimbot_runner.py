from datetime import datetime, timezone
from pathlib import Path

from claimbot.api import Game
from claimbot.models import LinePrice
from claimbot.runner import pipeline
from claimbot.runner.listener import next_game
from claimbot.strategies import load_strategy
from tests.conftest import FakeApi, GoodStrategy, SlowStrategy


def test_quote_clamps_invalid_values():
    assert LinePrice(1, -5, float("nan")).to_api() == {
        "index": 1, "charge_price": 0.0, "acceptance_limit": 0.0}

def _game(i, ts):
    return Game(i, datetime.fromtimestamp(ts, timezone.utc))

def test_next_game_skips_test_done_and_closed():
    now = 10_000.0
    games = [_game(0, 0), _game(1, now - 100), _game(2, now - 30), _game(3, now + 800)]
    assert next_game(games, now, 60, set()).id == 2          # still open
    assert next_game(games, now, 60, {2}).id == 3
    assert next_game(games, now, 60, {2, 3}) is None

def test_pipeline_submits_fallback_then_strategy(env):
    api = FakeApi(not_started_calls=1)
    report = pipeline.run_game(7, env, api, GoodStrategy())
    assert report.ok and report.fallback_submitted and report.final_submitted
    assert len(api.submissions) == 2
    assert api.submissions[0][0]["acceptance_limit"] == 200   # fallback first
    assert api.submissions[1] == [
        {"index": 1, "charge_price": 100.0, "acceptance_limit": 120.0},
        {"index": 2, "charge_price": 100.0, "acceptance_limit": 120.0}]
    assert (Path(report.run_dir) / "report.json").exists()
    assert (Path(report.run_dir) / "run.log").stat().st_size > 0

def test_pipeline_strategy_timeout_keeps_fallback(env):
    settings = env.with_overrides(game_window_s=1.5, submit_margin_s=0.5)
    api = FakeApi()
    report = pipeline.run_game(7, settings, api, SlowStrategy())
    assert "strategy timed out" in report.errors
    assert report.final_submitted
    assert api.submissions[-1][0]["acceptance_limit"] == 200

def test_pipeline_finds_archive_when_name_does_not_match(env):
    (env.cases_dir / "case_007.zip").rename(env.cases_dir / "case_042.zip")
    report = pipeline.run_game(7, env, FakeApi(), GoodStrategy(), submit=False)
    assert report.ok and report.case["zip"] == "case_042.zip"

def test_load_strategy_registry_and_import(env):
    assert load_strategy("council", env).name == "council"
    assert load_strategy("tests.conftest:GoodStrategy", env).name == "good"

def test_fetch_key_polls_from_just_before_start(monkeypatch):
    import time as _t
    api = FakeApi(not_started_calls=2)
    start = _t.time() + 0.3
    key = pipeline.fetch_key(api, 1, start, retry_s=5, poll_s=0.05, early_s=0.2)
    assert key == "secret" and api.not_started_calls == 0

def test_merge_accepts_triples_dicts_and_drops_junk():
    fb = [LinePrice(1, 0, 200), LinePrice(2, 0, 200)]
    out = pipeline.merge(fb, [(1, 50, 60), {"index": 2, "a": 70, "b": 80}, (9, 1, 1), "junk"])
    assert out == [LinePrice(1, 50, 60), LinePrice(2, 70, 80)]

class InterimThenHangStrategy:
    name = "interim-then-hang"

    def __init__(self, settings=None):
        pass

    def price(self, case, deadline_ts, publish=None):
        import time
        publish([(li.index, 77.0, 88.0) for li in case.lines])
        time.sleep(5)  # overruns the deadline
        return []

def test_timeout_after_interim_keeps_interim_not_fallback(env):
    settings = env.with_overrides(game_window_s=1.5, submit_margin_s=0.5)
    api = FakeApi()
    report = pipeline.run_game(7, settings, api, InterimThenHangStrategy())
    assert "strategy timed out" in report.errors and report.final_submitted
    assert api.submissions[-1][0] == {"index": 1, "charge_price": 77.0, "acceptance_limit": 88.0}


def test_backtest_summary_from_own_transactions():
    from claimbot.evaluation.backtest import summarise
    report = {"final_quotes": [{"index": 1, "a": 90.0, "b": 110.0}], "errors": [], "stages": []}
    txns = [
        {"issuer": "FDN", "reviewer": "X", "line_item_index": 1, "accepted": True, "amount": 100.0},
        {"issuer": "FDN", "reviewer": "Y", "line_item_index": 1, "accepted": False, "amount": 150.0},
        {"issuer": "X", "reviewer": "FDN", "line_item_index": 1, "accepted": False, "amount": 180.0},
        {"issuer": "Y", "reviewer": "FDN", "line_item_index": 1, "accepted": True, "amount": 95.0},
    ]
    s = summarise(3, "FDN", report, txns)
    assert s["actual_net"] == 250.0 - 275.0
    ln = s["lines"][0]
    assert ln["old_charge"] == 100.0 and ln["old_charge_verdict"] == "fair"
    assert ln["incoming_known_fair"] == 1 and ln["new_b_accepts_known_fair"] == 0   # 120 > 110
    assert ln["new_b_accepts_incoming"] == 1                                       # 95 <= 110


def test_pipeline_uploads_quotes_and_valuations_to_bench(env, monkeypatch):
    from claimbot.strategies.base import LineValuation, Strategy, StrategyResult

    class ValuedStrategy(Strategy):
        name = "valued"

        def price(self, case, deadline_ts, publish=None):
            return StrategyResult(
                quotes=[LinePrice(1, 100.0, 140.0), LinePrice(2, 0.0, 0.0)],
                valuations=[
                    LineValuation(1, covered=True, related=True, low=100.0, fair=150.0, high=220.0),
                    LineValuation(2, covered=False, related=False, low=30.0, fair=50.0, high=80.0),
                ],
            )

    pushed = {}

    def fake_push(bench_url, bench_token, *, strategy_name, author, predictions, timeout_s=10.0):
        pushed.update(
            url=bench_url, token=bench_token, strategy_name=strategy_name,
            author=author, predictions=predictions, timeout_s=timeout_s,
        )
        return {"ok": True, "games": 1}

    monkeypatch.setattr(pipeline, "push_run", fake_push)
    settings = env.with_overrides(
        bench_url="https://bench.example",
        bench_token="tok-123",
        bench_author="ankush",
        bench_strategy_name="council-exp",
        bench_upload=True,
    )
    report = pipeline.run_game(7, settings, FakeApi(), ValuedStrategy(settings), submit=False)
    assert report.ok and report.bench_uploaded and report.bench_response == {"ok": True, "games": 1}
    assert pushed["url"] == "https://bench.example" and pushed["token"] == "tok-123"
    assert pushed["strategy_name"] == "council-exp" and pushed["author"] == "ankush"
    pred = pushed["predictions"][0]
    assert pred["game_id"] == 7 and pred["latency_ms"] >= 0
    assert pred["items"] == [
        {"index": 1, "a": 100.0, "b": 140.0, "low": 100.0, "fair": 150.0, "high": 220.0, "covered": True, "related": True},
        {"index": 2, "a": 0.0, "b": 0.0, "low": 30.0, "fair": 50.0, "high": 80.0, "covered": False, "related": False},
    ]


def test_pipeline_bench_upload_skips_game_zero_and_survives_errors(env, monkeypatch):
    from claimbot.evaluation.bench import BenchError

    called = []
    monkeypatch.setattr(
        pipeline,
        "push_run",
        lambda *a, **kw: (called.append(True), (_ for _ in ()).throw(BenchError("down")))[1],
    )
    settings = env.with_overrides(bench_token="tok", bench_upload=True)

    # Game 0 is skipped (test game, never uploaded)
    (env.cases_dir / "case_007.zip").rename(env.cases_dir / "case_000.zip")
    r0 = pipeline.run_game(0, settings, FakeApi(), GoodStrategy(), submit=False)
    assert r0.ok and not r0.bench_uploaded and called == []

    # Real game: bench error is logged & recorded, but QuantCo submission & report.ok succeed
    (env.cases_dir / "case_000.zip").rename(env.cases_dir / "case_007.zip")
    api = FakeApi()
    r7 = pipeline.run_game(7, settings, api, GoodStrategy(), submit=True)
    assert r7.ok and r7.final_submitted and not r7.bench_uploaded
    assert any("bench upload:" in e for e in r7.errors)
