"""Replay finished games exactly like the live loop, just without waiting between them:

    for each game, oldest first:
        play it with the current strategy state (dry run: never submits to QuantCo),
        upload the result to FDN Bench (if enabled), then settle it (the strategy learns),
    so game g is played with what games before g taught, as it would have been live.
"""

from __future__ import annotations

import logging
import threading
import time

from claimbot.api import ClaimApi
from claimbot.config import Settings
from claimbot.runner.pipeline import run_game
from claimbot.runner.settle import settle_game
from claimbot.strategies import Strategy

log = logging.getLogger("claimbot.replay")


def replay_games(settings: Settings, api: ClaimApi, strategy: Strategy, games: list[int],
                 stop: threading.Event | None = None) -> list[dict]:
    stop = stop or threading.Event()
    rows: list[dict] = []
    t_all = time.time()
    for n, gid in enumerate(games, 1):
        if stop.is_set():
            break
        t0 = time.time()
        report = run_game(gid, settings, api, strategy, submit=False)
        played = time.time() - t0
        settled = settle_game(settings, strategy, gid, attempts=1, stop=stop)
        row = {"game_id": gid, "ok": report.ok, "errors": report.errors,
               "bench_uploaded": report.bench_uploaded, "settled": settled,
               "play_s": round(played, 1), "run_dir": report.run_dir}
        rows.append(row)
        log.info("replay %d/%d: game %d played in %.1fs, bench=%s, settled=%s, errors=%s",
                 n, len(games), gid, played, report.bench_uploaded, settled,
                 report.errors or "none")
    log.info("replay done: %d game(s) in %.0fs", len(rows), time.time() - t_all)
    return rows
