"""Council: settlement decoding, drift and reject-curve fits, quoting, and the in-game flow."""

from __future__ import annotations

import json
import math
import re
import time
from pathlib import Path

import numpy as np
import pytest

from claimbot.evaluation.settlement import decode, save_cached, transactions_dir
from claimbot.models import Case, LineItem
from claimbot.runner import pipeline
from claimbot.strategies.council import Council
from claimbot.strategies.council.calibrate import (
    Drift,
    Estimate,
    RejectCurve,
    _Obs,
    combine,
    fit_drift,
    fit_reject,
    quote,
)
from claimbot.strategies.council.roster import AgentSpec
from claimbot.evaluation.settlement import LineOutcome
from tests.conftest import FakeApi


# ---- settlement --------------------------------------------------------------------------

def tx(issuer, reviewer, line, accepted, amount):
    return {"issuer": issuer, "reviewer": reviewer, "line_item_index": line,
            "accepted": accepted, "amount": amount}


def test_decode_brackets_from_both_directions():
    txns = [
        tx("FDN", "x", 1, False, 150.0),     # our 100 rejected and paid 1.5x: t >= 100
        tx("FDN", "y", 1, True, 100.0),
        tx("y", "FDN", 1, False, 180.0),     # their 120 rejected, fair: t >= 120
        tx("x", "FDN", 1, True, 90.0),
        tx("FDN", "x", 2, False, 0.0),       # our 300 rejected, paid 0: t < 300
        tx("FDN", "y", 2, True, 300.0),
        tx("x", "FDN", 2, False, 0.0),       # their charge unknown: no number
    ]
    out = decode(txns, "FDN")
    assert out[1].our_a == 100.0 and out[1].t_lo == 120.0 and math.isinf(out[1].t_hi)
    assert out[1].rejected_fair == 1 and out[1].accepted == 1
    assert [x.a for x in out[1].incoming] == [120.0, 90.0]
    assert out[2].our_a == 300.0 and out[2].t_lo == 0.0 and out[2].t_hi == 300.0
    assert out[2].incoming[0].a is None


# ---- fits --------------------------------------------------------------------------------

def _synthetic_brackets(mu, sigma, n, rng):
    """t_hat = t * exp(-(mu + noise)), i.e. ln(t / t_hat) ~ N(mu, sigma); brackets from
    random probe charges, as settlement would produce them."""
    obs = _Obs()
    for _ in range(n):
        t = 100.0
        t_hat = t / math.exp(rng.normal(mu, sigma))
        probe = t * math.exp(rng.normal(0, 0.4))
        out = LineOutcome(line=1)
        if probe <= t:
            out.t_lo = probe
        else:
            out.t_hi = probe
        obs.add(out, t_hat, 0.01, 1.0)
    return obs


def test_fit_drift_recovers_bias_and_spread():
    rng = np.random.default_rng(1)
    d = fit_drift(_synthetic_brackets(0.2, 0.25, 600, rng))
    assert d.mu == pytest.approx(0.2, abs=0.06)
    assert d.sigma == pytest.approx(0.25, abs=0.07)
    assert d.n == 600 and d.n_lo + d.n_hi == 600


def test_fit_drift_without_data_is_the_prior():
    assert fit_drift(_Obs()) == Drift()


def test_fit_reject_recovers_curve_and_caps_markup():
    rng = np.random.default_rng(2)
    m = np.exp(rng.normal(0, 0.3, 4000))
    p = 1 / (1 + np.exp(-(-0.5 + 2.0 * np.log(m))))
    y = (rng.random(4000) < p).astype(int)
    curve = fit_reject(list(np.log(m)), list(y), [1.0] * 4000, m_seen=1.4)
    assert curve.alpha == pytest.approx(-0.5, abs=0.15)
    assert curve.beta == pytest.approx(2.0, abs=0.3)
    assert curve.m_cap == pytest.approx(1.75)


# ---- combining and quoting -----------------------------------------------------------------

def v(mid, covered=1.0, related=1.0):
    return {"fair_mid": mid, "covered": covered, "related": related}


def test_combine_corrects_each_agent_and_respects_trust():
    drifts = {"a@1": Drift(mu=math.log(0.8), sigma=0.2),   # a reads 20 % low
              "b@1": Drift(mu=0.0, sigma=0.2),
              "c@1": Drift(mu=0.0, sigma=0.2)}
    verdicts = {"a@1": v(80), "b@1": v(100), "c@1": v(400)}
    est = combine(verdicts, drifts, Drift(sigma=0.1),
                  {"legit": 0.9, "trust": ["a@1", "b@1"]})
    assert est.t_hat == pytest.approx(100.0)          # c dropped, a corrected 80 -> 100
    assert est.used == ["a@1", "b@1"] and est.p_excl == pytest.approx(0.1)
    assert est.sigma == pytest.approx(0.1)
    # Without the chief, everyone counts and the spread widens sigma.
    est2 = combine(verdicts, drifts, Drift(sigma=0.1))
    assert est2.t_hat > 150 and est2.sigma > 0.5
    # The chief trusting nobody usable falls back to all agents.
    est3 = combine(verdicts, drifts, Drift(sigma=0.1), {"legit": 1.0, "trust": ["zzz"]})
    assert est3.used == ["a@1", "b@1", "c@1"]


def test_single_agent_fallback_uses_its_own_drift():
    est = combine({"a@1": v(80)}, {"a@1": Drift(mu=math.log(0.8), sigma=0.3)})
    assert est.t_hat == pytest.approx(100.0) and est.sigma == pytest.approx(0.3)


def test_quote_b_is_one_third_quantile_and_zero_when_likely_worthless():
    a, b, m = quote(Estimate(100.0, 0.3, 0.0), RejectCurve())
    assert b == pytest.approx(100 * math.exp(0.3 * -0.4307), rel=1e-3)
    assert 0.3 <= m <= RejectCurve().m_cap and a == pytest.approx(100 * m)
    assert quote(Estimate(100.0, 0.3, 0.34), RejectCurve())[1] == 0.0
    assert quote(Estimate(0.0, 0.3, 0.0), RejectCurve()) == (0.0, 0.0, 0.0)
    # Fair bills pay 1.5a when rejected, so even a flat reject curve keeps a near t_hat...
    assert quote(Estimate(100.0, 0.3, 0.0), RejectCurve(beta=0.0, m_cap=1.3))[2] < 1.1
    # ...but on a likely-worthless line it pushes a to the cap, and no further.
    assert quote(Estimate(100.0, 0.3, 0.8), RejectCurve(beta=0.0, m_cap=1.3))[2] == \
        pytest.approx(1.3)


# ---- in-game flow --------------------------------------------------------------------------

class FakeLLM:
    def __init__(self, mid=100.0, delay=0.0, fail=False, covered=1.0):
        self.mid, self.delay, self.fail, self.covered = mid, delay, fail, covered
        self.calls = []

    def complete_json(self, req):
        self.calls.append(req)
        time.sleep(min(self.delay, req.timeout_s))
        if self.fail or self.delay > req.timeout_s:
            raise RuntimeError("boom")
        idx = [int(x) for x in re.search(r"line \(([\d, ]+)\)", req.task)[1].split(", ")]
        if req.schema_name == "chief":
            labels = req.schema["properties"]["lines"]["items"]["properties"]["trust"][
                "items"]["enum"]
            return {"case_notes": "c", "lines": [
                {"index": i, "legit": 0.9, "trust": labels[:2], "reasoning": "r"} for i in idx]}
        return {"case_notes": "n", "lines": [
            {"index": i, "covered": self.covered, "related": 1.0, "fair_mid": self.mid,
             "reasoning": "r"} for i in idx]}

    def take_usage(self):
        return {"calls": len(self.calls)}


AGENTS = (AgentSpec("a", "fake", None, None, "Your focus: the POLICY. x"),
          AgentSpec("b", "fake", None, None, "Your focus: the INVOICE. x"),
          AgentSpec("c", "fake", None, None, "Your focus: the EVIDENCE. x"))
CHIEF = AgentSpec("chief", "fake", None, None, photos=False)


def make_case(game_id=7):
    return Case(game_id=game_id, directory=Path("."), policy="p", description="d",
                invoice_text="inv", lines=[LineItem(1, "Leckortung", 1, "psch"),
                                           LineItem(2, "Trocknung", 10, "Tage")])


def council(env, clients, chief=CHIEF):
    return Council(env, agents=AGENTS, chief=chief,
                   clients={f"{k}@{AGENTS[0].version}": c for k, c in clients.items()})


def test_council_publishes_first_agent_then_blend_then_chief_decides(env):
    clients = {"a": FakeLLM(80, delay=0.05), "b": FakeLLM(100, delay=0.2),
               "c": FakeLLM(400, delay=0.3), "chief": FakeLLM()}
    strat = council(env, clients)
    published = []
    res = strat.price(make_case(), time.time() + 30, publish=published.append)
    assert [r.quotes[0].index for r in published] == [1, 1]           # first agent, blend
    trace = res.trace
    assert [s["source"] for s in trace["stages"]] == ["agent:a", "blend", "chief"]
    assert trace["source"] == "chief" and trace["labels"] == {"A": "a@1", "B": "b@1",
                                                              "C": "c@1"}
    # The chief trusted A and B only: the 400 estimate is out of the final number.
    line = trace["stages"][-1]["lines"]["1"]
    assert line["used"] == ["a@1", "b@1"] and line["t_hat"] == pytest.approx(89.44, rel=1e-3)
    assert {q.index for q in res.quotes} == {1, 2}
    # Agents never see the chief's output or the calibration; the chief sees labels only.
    chief_task = clients["chief"].calls[0].task
    assert "a@1" not in chief_task and '"A"' in chief_task


def test_council_without_chief_answer_keeps_the_blend(env):
    clients = {"a": FakeLLM(100), "b": FakeLLM(100), "c": FakeLLM(fail=True),
               "chief": FakeLLM(fail=True)}
    res = council(env, clients).price(make_case(), time.time() + 30)
    assert res.trace["source"] == "blend" and "c@1" in res.trace["failed"]
    assert "chief@1" in res.trace["failed"]


def test_council_slow_agent_misses_budget_but_first_answer_stands(env):
    # 16 s to the deadline: the agent budget ends 1 + 14 s before, i.e. after ~1 s.
    clients = {"a": FakeLLM(100, delay=0.1), "b": FakeLLM(100, delay=5),
               "c": FakeLLM(100, delay=5), "chief": FakeLLM()}
    t0 = time.time()
    res = council(env, clients).price(make_case(), time.time() + 16)
    assert time.time() - t0 < 3
    assert res.trace["source"] == "chief" and set(res.trace["failed"]) == {"b@1", "c@1"}
    assert res.trace["stages"][-1]["lines"]["1"]["used"] == ["a@1"]


def test_record_written_after_submit_and_refit_learns(env):
    clients = {"a": FakeLLM(80), "b": FakeLLM(100), "c": FakeLLM(120), "chief": FakeLLM()}
    strat = council(env, clients)
    api = FakeApi()
    report = pipeline.run_game(7, env, api, strat)
    assert report.final_submitted
    rec = json.loads((env.runs_dir / "council" / "games" / "game_007.json").read_text())
    assert rec["dry_run"] is False and rec["source"] == "chief"
    assert set(rec["agents"]) == {"a@1", "b@1", "c@1"}
    assert (Path(report.run_dir) / "strategy_trace.json").is_file()

    # Settlement: everything we charged was fair, t is well above every estimate.
    a1 = next(q for q in rec["submitted"] if q["index"] == 1)["a"]
    txns = [tx("FDN", "x", 1, False, 1.5 * a1), tx("y", "FDN", 1, False, 1.5 * 200.0)]
    strat.on_game_settled(7, txns)
    state = json.loads((env.runs_dir / "council" / "state.json").read_text())
    assert state["games"] == [7] and state["revision"] == 1
    assert state["agents"]["a@1"]["mu"] > 0                  # a reads low: corrected upward
    assert (transactions_dir(env.runs_dir) / "game_007.json").is_file()
    assert strat.state.final.n == 1


def test_dry_run_never_replaces_a_live_record(env):
    clients = {"a": FakeLLM(100), "b": FakeLLM(100), "c": FakeLLM(100), "chief": FakeLLM()}
    strat = council(env, clients)
    pipeline.run_game(7, env, FakeApi(), strat)                     # live
    pipeline.run_game(7, env, FakeApi(), strat, submit=False)       # backtest replay
    rec = json.loads((env.runs_dir / "council" / "games" / "game_007.json").read_text())
    assert rec["dry_run"] is False


def test_refit_with_no_settled_games_keeps_the_prior(env):
    strat = council(env, {"a": FakeLLM()})
    save_cached(transactions_dir(env.runs_dir), 3, [tx("FDN", "x", 1, True, 10.0)])
    state = strat.refit()
    assert state.games == [] and state.final == Drift()


def test_replay_plays_uploads_and_settles_each_game_before_the_next(env, monkeypatch):
    from tests.conftest import make_case_zip
    from claimbot.runner import replay, settle

    make_case_zip(env.cases_dir / "case_008.zip", "secret")
    env = env.with_overrides(bench_upload=True, bench_token="tok",
                             bench_strategy_name="Ankush Council v4")
    events = []
    monkeypatch.setattr(pipeline, "push_run",
                        lambda *a, **k: events.append(("bench", k["predictions"][0]["game_id"],
                                                       k["strategy_name"])) or {"ok": True})
    monkeypatch.setattr(settle, "completed_games", lambda *a, **k: {7, 8})

    def fake_fetch(base_url, gid, team, cache_dir, timeout_s):
        events.append(("settle", gid))
        txns = [tx("FDN", "x", 1, False, 300.0), tx("y", "FDN", 2, False, 600.0)]
        save_cached(cache_dir, gid, txns)
        return txns
    monkeypatch.setattr(settle, "fetch_transactions", fake_fetch)

    clients = {"a": FakeLLM(80), "b": FakeLLM(100), "c": FakeLLM(120), "chief": FakeLLM()}
    strat = council(env, clients)
    revisions = []
    orig_price = strat.price
    def price(case, deadline_ts, publish=None):
        revisions.append(strat.state.revision)       # state the game is played with
        return orig_price(case, deadline_ts, publish)
    monkeypatch.setattr(strat, "price", price)

    rows = replay.replay_games(env, FakeApi(), strat, [7, 8])
    assert [r["game_id"] for r in rows] == [7, 8]
    assert all(r["ok"] and r["settled"] and r["bench_uploaded"] for r in rows)
    assert events == [("bench", 7, "Ankush Council v4"), ("settle", 7),
                      ("bench", 8, "Ankush Council v4"), ("settle", 8)]
    assert revisions == [0, 1]                       # game 8 used what game 7 taught
    snaps = sorted(p.name for p in (env.runs_dir / "council" / "snapshots").iterdir())
    assert snaps == ["state_after_game_007.json", "state_after_game_008.json"]
    recs = sorted(p.name for p in (env.runs_dir / "council" / "games").iterdir())
    assert recs == ["game_007.json", "game_008.json"]
