"""After a game: wait until the leaderboard marks it completed, fetch our transactions
(cached under runs/transactions/) and hand them to `strategy.on_game_settled`."""

from __future__ import annotations

import logging
import threading
import time

import requests

from claimbot.config import Settings
from claimbot.evaluation.settlement import fetch_transactions, transactions_dir
from claimbot.strategies import Strategy

log = logging.getLogger("claimbot.settle")


def completed_games(base_url: str, timeout_s: float = 15.0) -> set[int]:
    r = requests.get(f"{base_url.rstrip('/')}/leaderboard/api/games",
                     params={"page": 1, "completed_only": "true", "page_size": 1000},
                     timeout=timeout_s)
    r.raise_for_status()
    return {int(g["id"]) for g in r.json().get("items", []) if g.get("status") == "completed"}


def settle_game(settings: Settings, strategy: Strategy, game_id: int, *,
                not_before: float | None = None, attempts: int = 12, retry_s: float = 30.0,
                stop: threading.Event | None = None) -> bool:
    """Returns True once the strategy has seen the game's transactions."""
    stop = stop or threading.Event()
    if not_before and not_before > time.time():
        if stop.wait(not_before - time.time()):
            return False
    for attempt in range(1, attempts + 1):
        try:
            if game_id in completed_games(settings.base_url, settings.http_timeout_s):
                txns = fetch_transactions(settings.base_url, game_id, settings.team_name,
                                          transactions_dir(settings.runs_dir),
                                          settings.http_timeout_s)
                if txns:
                    t0 = time.time()
                    strategy.on_game_settled(game_id, txns)
                    log.info("game %d settled: %d transactions, strategy updated in %.1fs",
                             game_id, len(txns), time.time() - t0)
                    return True
            log.info("game %d not settled yet (attempt %d/%d)", game_id, attempt, attempts)
        except Exception as exc:
            log.warning("settling game %d failed (attempt %d/%d): %s", game_id, attempt,
                        attempts, exc)
        if stop.wait(retry_s):
            return False
    log.error("game %d: gave up waiting for its results", game_id)
    return False


def settle_in_background(settings: Settings, strategy: Strategy, game_id: int,
                         window_end_ts: float, stop: threading.Event) -> threading.Thread:
    th = threading.Thread(target=settle_game, args=(settings, strategy, game_id),
                          kwargs={"not_before": window_end_ts + settings.settle_delay_s,
                                  "stop": stop},
                          name=f"settle-{game_id}", daemon=True)
    th.start()
    return th
