"""Long-running loop: follow the schedule, wake at each start_time, run the pipeline."""

from __future__ import annotations

import logging
import signal
import threading
import time

from claimbot.api import ClaimApi, Game
from claimbot.config import Settings
from claimbot.runner.pipeline import run_game, utc_iso
from claimbot.runner.settle import settle_in_background
from claimbot.strategies import Strategy

log = logging.getLogger("claimbot.listener")

TEST_GAME_ID = 0  # always open, stores nothing: never part of the schedule we play


def next_game(games: list[Game], now: float, window_s: float, done: set[int]) -> Game | None:
    """Earliest game we haven't played whose submission window has not closed yet."""
    pending = [
        g for g in games
        if g.id != TEST_GAME_ID and g.id not in done and g.start_ts + window_s > now
    ]
    return min(pending, key=lambda g: g.start_time, default=None)


class Listener:
    def __init__(self, settings: Settings, api: ClaimApi, strategy: Strategy, submit: bool = True):
        self.settings = settings
        self.api = api
        self.strategy = strategy
        self.submit = submit
        self.done: set[int] = set()
        self.stop = threading.Event()

    def install_signal_handlers(self) -> None:
        def handler(signum, _frame):
            log.info("signal %s received; stopping after the current step", signum)
            self.stop.set()

        signal.signal(signal.SIGINT, handler)
        signal.signal(signal.SIGTERM, handler)

    def run_forever(self) -> None:
        s = self.settings
        log.info("listener up | strategy=%s | submit=%s | cases=%s | runs=%s",
                 getattr(self.strategy, "name", "?"), self.submit, s.cases_dir, s.runs_dir)
        games: list[Game] = []
        last_refresh = 0.0
        while not self.stop.is_set():
            now = time.time()
            if now - last_refresh >= s.schedule_refresh_s or not games:
                try:
                    games = self.api.list_games()
                    last_refresh = now
                    log.debug("schedule refreshed: %d games", len(games))
                except Exception as exc:
                    log.error("could not list games: %s (retrying in 10 s)", exc)
                    self.stop.wait(10)
                    continue

            game = next_game(games, time.time(), s.game_window_s, self.done)
            if game is None:
                log.info("no upcoming games; checking again in %.0f s", s.schedule_refresh_s)
                self.stop.wait(s.schedule_refresh_s)
                last_refresh = 0.0
                continue

            wait = game.start_ts - time.time()
            if wait > s.wake_lead_s:
                # Never sleep past (start - wake_lead): wake for the next schedule refresh
                # or for the pre-start phase, whichever comes first.
                nap = min(wait - s.wake_lead_s, s.schedule_refresh_s)
                log.info("next: game %d at %s (in %s); sleeping %.0f s",
                         game.id, utc_iso(game.start_ts), _fmt(wait), nap)
                self.stop.wait(nap)
                continue

            # Pre-start phase (≤ wake_lead_s before start): confirm the start time once
            # more (this also warms the HTTP connection), then hand over to the pipeline,
            # which polls the key from just before start_time.
            if wait > 0:
                try:
                    fresh = {g.id: g for g in self.api.list_games()}.get(game.id)
                    if fresh is not None and fresh.start_ts != game.start_ts:
                        log.warning("game %d moved to %s; rescheduling",
                                    game.id, utc_iso(fresh.start_ts))
                        last_refresh = 0.0
                        continue
                except Exception as exc:
                    log.warning("pre-start schedule check failed (%s); going ahead", exc)
                log.info("game %d starts at %s (in %.1f s); armed", game.id,
                         utc_iso(game.start_ts), game.start_ts - time.time())
            else:
                log.warning("game %d already running (%.1f s in); joining late", game.id, -wait)

            report = run_game(game.id, s, self.api, self.strategy,
                              start_ts=game.start_ts, submit=self.submit)
            self.done.add(game.id)
            # Results arrive after the window closes; the strategy learns from them in the
            # background, long before the next game (800 s cadence).
            settle_in_background(s, self.strategy, game.id,
                                 game.start_ts + s.game_window_s, self.stop)
            level = log.info if report.ok else log.error
            level("game %d finished: ok=%s errors=%s report=%s/report.json",
                  game.id, report.ok, report.errors or "none", report.run_dir)
        log.info("listener stopped")


def _fmt(seconds: float) -> str:
    seconds = int(max(0, seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}"
