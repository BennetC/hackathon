"""Client for the QuantCo team API (see docs/agents/02-api.md)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime

import requests

log = logging.getLogger("claimbot.api")


class ApiError(RuntimeError):
    def __init__(self, status: int, body: str, action: str):
        super().__init__(f"{action} failed: HTTP {status} {body[:300]}")
        self.status = status
        self.body = body


@dataclass(frozen=True)
class Game:
    id: int
    start_time: datetime  # timezone-aware UTC

    @property
    def start_ts(self) -> float:
        return self.start_time.timestamp()


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class ClaimApi:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout_s: float = 8.0,
        session: requests.Session | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.session = session or requests.Session()
        self.session.headers.update({"X-API-Key": api_key})

    def _request(self, method: str, path: str, action: str, attempts: int = 3, **kw):
        url = f"{self.base_url}{path}"
        last_exc: Exception | None = None
        for attempt in range(1, attempts + 1):
            t0 = time.monotonic()
            try:
                resp = self.session.request(method, url, timeout=self.timeout_s, **kw)
            except requests.RequestException as exc:  # network trouble: retry
                last_exc = exc
                log.warning("%s %s attempt %d/%d network error: %s",
                            method, path, attempt, attempts, exc)
                time.sleep(min(0.5 * attempt, 2.0))
                continue
            ms = (time.monotonic() - t0) * 1000
            log.debug("%s %s -> %d in %.0f ms", method, path, resp.status_code, ms)
            if resp.status_code >= 500 and attempt < attempts:
                log.warning("%s %s server error %d, retrying", method, path, resp.status_code)
                time.sleep(min(0.5 * attempt, 2.0))
                continue
            if resp.status_code != 200:
                raise ApiError(resp.status_code, resp.text, action)
            return resp.json()
        raise ApiError(0, str(last_exc), action)

    def list_games(self) -> list[Game]:
        data = self._request("GET", "/api/games/list", "list games")
        games = [Game(int(g["id"]), parse_time(g["start_time"])) for g in data]
        return sorted(games, key=lambda g: g.start_time)

    def get_key(self, game_id: int) -> str:
        data = self._request("GET", f"/api/games/{game_id}/key", "get key", attempts=1)
        return str(data["decryption_key"])

    def submit(self, game_id: int, items: list[dict]) -> list[dict]:
        return self._request(
            "PUT", f"/api/games/{game_id}/submissions", "submit", json=items
        )
