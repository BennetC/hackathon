"""Backtest: replay finished games through a strategy (dry run, never submits) and compare
with what our team actually submitted and earned.

Only OUR team's own published transactions are used (leaderboard, team=FDN). From them:
  * our actual net per game;
  * our actual charge per line (accepted -> amount; rejected and paid -> amount / 1.5, which
    means it was fair; rejected and unpaid -> it was judged inflated, amount unknown);
  * charges other teams sent us, where the amount is visible.
The true fair value t stays secret, so the comparison is a proxy, not a counterfactual net:
it shows where the new prices sit relative to what the old ones achieved.
"""

from __future__ import annotations

import json
import logging
import statistics
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests

from claimbot.api import ClaimApi
from claimbot.config import Settings
from claimbot.runner.pipeline import run_game

log = logging.getLogger("claimbot.backtest")


def fetch_team_transactions(base_url: str, game_id: int, team: str) -> list[dict]:
    items, page = [], 1
    while True:
        r = requests.get(f"{base_url}/leaderboard/api/transactions",
                         params={"game_id": game_id, "team": team, "page": page}, timeout=15)
        r.raise_for_status()
        data = r.json()
        items += data.get("items", [])
        if page >= data.get("total_pages", 1):
            return items
        page += 1
        time.sleep(0.2)  # be gentle with the public API


def finished_games(api: ClaimApi, window_s: float) -> list[int]:
    now = time.time()
    return [g.id for g in api.list_games() if g.id != 0 and g.start_ts + window_s < now]


def summarise(game_id: int, team: str, report: dict, txns: list[dict]) -> dict:
    ours = [t for t in txns if t["issuer"] == team]
    theirs = [t for t in txns if t["reviewer"] == team]
    actual_net = sum(t["amount"] for t in ours) - sum(t["amount"] for t in theirs)

    by_line: dict[int, dict] = defaultdict(lambda: {"our_charge": None, "our_fair": None,
                                                    "accepted_by": 0, "rejected_by": 0,
                                                    "incoming": []})
    for t in ours:
        d = by_line[t["line_item_index"]]
        if t["accepted"]:
            d["accepted_by"] += 1
            d["our_charge"] = d["our_charge"] or t["amount"]
        else:
            d["rejected_by"] += 1
            if t["amount"] > 0:
                d["our_charge"], d["our_fair"] = round(t["amount"] / 1.5, 2), True
            elif d["our_fair"] is None:
                d["our_fair"] = False
    for t in theirs:
        d = by_line[t["line_item_index"]]
        if t["accepted"]:
            d["incoming"].append({"a": t["amount"], "fair": None})
        elif t["amount"] > 0:
            d["incoming"].append({"a": round(t["amount"] / 1.5, 2), "fair": True})
        else:
            d["incoming"].append({"a": None, "fair": False})

    lines = []
    for q in report.get("final_quotes", []):
        i, a, b = q["index"], q["a"], q["b"]
        d = by_line[i]
        known = [x["a"] for x in d["incoming"] if x["a"] is not None]
        fair_known = [x["a"] for x in d["incoming"] if x["fair"]]
        lines.append({
            "line": i,
            "new_a": a, "new_b": b,
            "old_charge": d["our_charge"],
            "old_charge_verdict": {True: "fair", False: "inflated", None: "?"}[d["our_fair"]],
            "old_accepted_by": d["accepted_by"], "old_rejected_by": d["rejected_by"],
            "incoming_median": round(statistics.median(known), 2) if known else None,
            "incoming_known_fair": len(fair_known),
            # charges that were certainly fair: would the new b accept them?
            "new_b_accepts_known_fair": sum(1 for x in fair_known if x <= b),
            "new_b_accepts_incoming": sum(1 for x in known if x <= b),
            "incoming_count": len(d["incoming"]),
        })
    return {"game_id": game_id, "actual_net": round(actual_net, 2), "lines": lines,
            "strategy_errors": report.get("errors", []),
            "strategy_seconds": next((s.get("since_run_start_s") for s in report.get("stages", [])
                                      if s["stage"] == "strategy"), None)}


def render_markdown(rows: list[dict]) -> str:
    out = ["| game | line | new a | new b | old charge | old verdict | old accepted/rejected "
           "| incoming median | new b accepts known-fair | FDN actual net |",
           "|---:|---:|---:|---:|---:|---|---|---:|---|---:|"]
    for g in rows:
        for j, ln in enumerate(g["lines"]):
            out.append(
                f"| {g['game_id'] if j == 0 else ''} | {ln['line']} | {ln['new_a']:.2f} | "
                f"{ln['new_b']:.2f} | {ln['old_charge'] if ln['old_charge'] is not None else '-'} | "
                f"{ln['old_charge_verdict']} | {ln['old_accepted_by']}/{ln['old_rejected_by']} | "
                f"{ln['incoming_median'] if ln['incoming_median'] is not None else '-'} | "
                f"{ln['new_b_accepts_known_fair']}/{ln['incoming_known_fair']} | "
                f"{g['actual_net'] if j == 0 else ''} |")
    return "\n".join(out)


def _backtest_one(gid: int, team: str, strategy_spec: str, settings: Settings) -> dict:
    """Runs in its own process: one game, dry run, then our team's transactions."""
    from claimbot.logs import setup_logging
    from claimbot.strategies import load_strategy

    setup_logging(verbose=False)
    api = ClaimApi(settings.base_url, settings.api_key, settings.http_timeout_s)
    strategy = load_strategy(strategy_spec, settings)
    t0 = time.time()
    report = run_game(gid, settings, api, strategy, submit=False)   # NEVER submits
    rep = json.loads((Path(report.run_dir) / "report.json").read_text())
    try:
        txns = fetch_team_transactions(settings.base_url, gid, team)
    except Exception as exc:
        log.warning("could not fetch transactions for game %d: %s", gid, exc)
        txns = []
    row = summarise(gid, team, rep, txns)
    row["run_dir"] = report.run_dir
    row["wall_s"] = round(time.time() - t0, 1)
    return row


def run_backtest(settings: Settings, games: list[int], team: str, strategy_spec: str,
                 parallel: int = 4) -> Path:
    """Games are independent, so they run in parallel, one process per game (separate
    logs and state). `parallel` caps concurrent games to stay within LLM rate limits."""
    from concurrent.futures import ProcessPoolExecutor, as_completed

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = settings.runs_dir / "backtest" / stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=max(1, parallel)) as ex:
        futs = {ex.submit(_backtest_one, gid, team, strategy_spec, settings): gid for gid in games}
        for fut in as_completed(futs):
            gid = futs[fut]
            try:
                row = fut.result()
            except Exception as exc:
                log.error("backtest game %d failed: %s", gid, exc)
                continue
            rows.append(row)
            rows.sort(key=lambda r: r["game_id"])
            log.info("backtest: game %d done in %.0fs (%d/%d)", gid, row["wall_s"],
                     len(rows), len(games))
            (out_dir / "results.json").write_text(json.dumps(rows, indent=2))
            (out_dir / "results.md").write_text(render_markdown(rows) + "\n")
    log.info("backtest done in %.0fs: %s", time.time() - t0, out_dir)
    return out_dir
