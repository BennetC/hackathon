"""Command line: `claimbot listen | debug <game> | games | backtest | settle | replay`."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from claimbot.api import ClaimApi
from claimbot.config import ConfigError, load_settings
from claimbot.runner.listener import Listener
from claimbot.logs import setup_logging
from claimbot.runner.pipeline import run_game, utc_iso
from claimbot.strategies import load_strategy

log = logging.getLogger("claimbot")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="claimbot", description=__doc__)
    p.add_argument("-v", "--verbose", action="store_true", help="DEBUG logs on the console")
    p.add_argument("--env-file", type=Path, default=Path(".env"), help="default: ./.env")
    p.add_argument("--strategy", help="override CLAIMBOT_STRATEGY")
    p.add_argument("--bench-name", help="override CLAIMBOT_BENCH_STRATEGY_NAME for FDN Bench uploads")
    p.add_argument("--no-bench", action="store_true", help="disable uploading results to FDN Bench")
    sub = p.add_subparsers(dest="command", required=True)

    listen = sub.add_parser("listen", help="run forever: play every scheduled game")
    listen.add_argument("--dry-run", action="store_true", help="do everything except submit")

    dbg = sub.add_parser("debug", help="run the full pipeline once for one game, verbosely")
    dbg.add_argument("game_id", type=int, help="game id (0 = always-open test game)")
    dbg.add_argument("--dry-run", action="store_true", help="do not submit")
    dbg.add_argument("--key", help="use this decryption key instead of fetching it")
    dbg.add_argument("--zip", type=Path, help="use this archive instead of case_NNN.zip")
    dbg.add_argument("--wait", action="store_true",
                     help="if the game is in the future, wait for its start_time")
    dbg.add_argument("--no-deadline", action="store_true",
                     help="let the strategy run as long as it needs")

    sub.add_parser("games", help="show the schedule and what is next")

    bt = sub.add_parser("backtest", help="replay finished games (dry run, never submits) and "
                                         "compare with our team's actual results")
    bt.add_argument("--games", help="e.g. 1-10 or 3,5,7 (default: all finished games)")
    bt.add_argument("--team", default="FDN", help="our team name on the leaderboard")
    bt.add_argument("--parallel", type=int, default=4,
                    help="games replayed at the same time (mind LLM rate limits; default 4)")
    st = sub.add_parser("settle", help="fetch settled results of finished games and let the "
                                       "strategy learn from them (the listener does this "
                                       "after every game)")
    st.add_argument("--games", help="e.g. 1-34 or 3,5,7 (default: all completed games)")

    rp = sub.add_parser("replay", help="replay finished games one by one exactly like the live "
                                       "loop (play, bench upload, settle, next game); dry run, "
                                       "never submits")
    rp.add_argument("--games", help="e.g. 1-38 (default: all completed games)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    load_dotenv(args.env_file)
    setup_logging(verbose=args.verbose or args.command == "debug")
    try:
        settings = load_settings(require_api_key=not (args.command == "debug" and args.key))
    except ConfigError as exc:
        log.error("%s", exc)
        return 2
    if args.strategy:
        settings = settings.with_overrides(strategy=args.strategy)
    if args.bench_name:
        settings = settings.with_overrides(bench_strategy_name=args.bench_name)
    if args.no_bench:
        settings = settings.with_overrides(bench_upload=False)
    api = ClaimApi(settings.base_url, settings.api_key, settings.http_timeout_s)

    if args.command == "games":
        return cmd_games(api, settings)
    strategy = load_strategy(settings.strategy, settings)
    if args.command == "backtest":
        return cmd_backtest(args, settings, api, strategy)
    if args.command == "settle":
        return cmd_settle(args, settings, strategy)
    if args.command == "replay":
        return cmd_replay(args, settings, api, strategy)
    if args.command == "listen":
        listener = Listener(settings, api, strategy, submit=not args.dry_run)
        listener.install_signal_handlers()
        listener.run_forever()
        return 0
    return cmd_debug(args, settings, api, strategy)


def _parse_games(spec: str) -> list[int]:
    out: list[int] = []
    for part in spec.split(","):
        if "-" in part:
            lo, hi = part.split("-", 1)
            out += list(range(int(lo), int(hi) + 1))
        elif part.strip():
            out.append(int(part))
    return out


def cmd_backtest(args, settings, api, strategy) -> int:
    from claimbot.evaluation.backtest import finished_games, run_backtest

    done = set(finished_games(api, settings.game_window_s))
    games = _parse_games(args.games) if args.games else sorted(done)
    games = [g for g in games if g in done]
    log.info("backtesting %d finished game(s) with strategy %s, %d in parallel "
             "(dry run, no submissions): %s", len(games), settings.strategy, args.parallel, games)
    out_dir = run_backtest(settings, games, args.team, settings.strategy, args.parallel)
    print((out_dir / "results.md").read_text())
    print(f"results: {out_dir}/results.json")
    return 0


def cmd_settle(args, settings, strategy) -> int:
    from claimbot.runner.settle import completed_games, settle_game

    done = completed_games(settings.base_url, settings.http_timeout_s)
    games = _parse_games(args.games) if args.games else sorted(done)
    games = [g for g in games if g in done and g != 0]
    log.info("settling %d completed game(s) as %s: %s", len(games), settings.team_name, games)
    ok = [g for g in games if settle_game(settings, strategy, g, attempts=1)]
    log.info("settled %d/%d game(s)", len(ok), len(games))
    return 0 if len(ok) == len(games) else 1


def cmd_replay(args, settings, api, strategy) -> int:
    import json

    from claimbot.runner.replay import replay_games
    from claimbot.runner.settle import completed_games

    done = completed_games(settings.base_url, settings.http_timeout_s)
    games = _parse_games(args.games) if args.games else sorted(done)
    games = sorted(g for g in games if g in done and g != 0)
    log.info("replaying %d game(s) in order as %s, bench=%s (%s): %s", len(games),
             settings.team_name, settings.bench_upload,
             settings.bench_strategy_name or strategy.name, games)
    rows = replay_games(settings, api, strategy, games)
    out = settings.runs_dir / "replay" / time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(rows, indent=2))
    print(f"results: {out}/results.json")
    return 0 if all(r["ok"] and r["settled"] for r in rows) else 1


def cmd_games(api: ClaimApi, settings) -> int:
    now = time.time()
    games = api.list_games()
    shown_next = False
    for g in games:
        if g.start_ts + settings.game_window_s <= now:
            status = "ended"
        elif g.start_ts <= now:
            status = "OPEN NOW"
        else:
            status = f"in {g.start_ts - now:8.0f}s"
        marker = ""
        if not shown_next and g.id != 0 and g.start_ts + settings.game_window_s > now:
            marker, shown_next = "  <- next", True
        print(f"game {g.id:3d}  {utc_iso(g.start_ts)}  {status}{marker}")
    return 0


def cmd_debug(args, settings, api, strategy) -> int:
    start_ts = None
    if args.game_id != 0 and not args.key:
        try:
            game = next((g for g in api.list_games() if g.id == args.game_id), None)
        except Exception as exc:
            game = None
            log.warning("could not list games: %s", exc)
        if game is None:
            log.warning("game %d not in the schedule", args.game_id)
        else:
            delta = game.start_ts - time.time()
            log.info("game %d start_time %s (%s)", game.id, utc_iso(game.start_ts),
                     f"in {delta:.1f}s" if delta > 0 else f"{-delta:.1f}s ago")
            if delta > 0 and not args.wait:
                log.error("game has not started; key not available yet (use --wait)")
                return 1
            if delta > 0 or -delta < settings.game_window_s:
                start_ts = game.start_ts  # live: enforce the real window
            elif not args.dry_run:
                log.warning("window closed %.0fs ago; submission will be refused (use --dry-run)",
                            -delta - settings.game_window_s)

    report = run_game(
        args.game_id, settings, api, strategy,
        start_ts=start_ts,
        submit=not args.dry_run,
        key=args.key,
        zip_path=args.zip,
        enforce_deadline=not args.no_deadline,
    )
    print("\nTimeline")
    for st in report.stages:
        rel = f"+{st['since_run_start_s']:7.3f}s"
        flag = "ok " if st["ok"] else "FAIL"
        extra = {k: v for k, v in st.items() if k not in {"stage", "ok", "at", "since_run_start_s"}}
        print(f"  {st['at']}  {rel}  {flag} {st['stage']:<16} {extra or ''}")
    print(f"\nerrors: {report.errors or 'none'}")
    print(f"report: {report.run_dir}/report.json")
    print(f"log:    {report.run_dir}/run.log")
    print(f"case:   {report.run_dir}/case/")
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
