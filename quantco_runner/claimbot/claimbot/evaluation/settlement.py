"""Settled games: fetch our team's transactions (cached) and decode them into facts about t.

Each transaction row is one line x (issuer, reviewer) pair: `accepted` plus the `amount` paid.
From the settlement rules (docs/agents/01-game-rules.md):

  accepted                 -> amount = a (or min(a, c)); says nothing about t
  rejected, amount = 1.5a  -> a <= t   (fair bill)            => lower bound t >= a
  rejected, amount = 0     -> a >  t   (inflated, or a == 0)  => upper bound t < a, but only
                                                                 when we know a (our own charge)

t itself is never revealed, so per line we get a bracket [t_lo, t_hi): t_lo = 0 and
t_hi = inf mean "no bound on that side".
"""

from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import requests

log = logging.getLogger("claimbot.settlement")

PENALTY = 1.5


@dataclass
class Outgoing:
    """Our charge to one opponent on one line."""

    reviewer: str
    accepted: bool
    amount: float


@dataclass
class Incoming:
    """One opponent's charge to us on one line. `a` is None when we cannot know it."""

    issuer: str
    accepted: bool
    amount: float
    a: float | None


@dataclass
class LineOutcome:
    line: int
    our_a: float | None = None          # what we charged (None if no row reveals it)
    t_lo: float = 0.0                   # t >= t_lo
    t_hi: float = math.inf              # t <  t_hi
    outgoing: list[Outgoing] = field(default_factory=list)
    incoming: list[Incoming] = field(default_factory=list)

    @property
    def rejected_fair(self) -> int:
        return sum(1 for o in self.outgoing if not o.accepted and o.amount > 0)

    @property
    def rejected_zero(self) -> int:
        return sum(1 for o in self.outgoing if not o.accepted and o.amount <= 0)

    @property
    def accepted(self) -> int:
        return sum(1 for o in self.outgoing if o.accepted)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["t_hi"] = None if math.isinf(self.t_hi) else self.t_hi
        return d


def decode(transactions: list[dict], team: str) -> dict[int, LineOutcome]:
    """Decode one game's transactions (as seen by `team`) into per-line outcomes."""
    lines: dict[int, LineOutcome] = {}
    for tx in transactions:
        i = int(tx["line_item_index"])
        lo = lines.setdefault(i, LineOutcome(line=i))
        accepted = bool(tx["accepted"])
        amount = round(float(tx["amount"] or 0.0), 2)
        if tx["issuer"] == team:
            lo.outgoing.append(Outgoing(tx["reviewer"], accepted, amount))
            if accepted and amount > 0:
                lo.our_a = lo.our_a or amount
            elif not accepted and amount > 0:
                lo.our_a = round(amount / PENALTY, 2)
        elif tx["reviewer"] == team:
            if accepted:
                a = amount
            elif amount > 0:
                a = round(amount / PENALTY, 2)
            else:
                a = None
            lo.incoming.append(Incoming(tx["issuer"], accepted, amount, a))

    for lo in lines.values():
        # Lower bounds: every fair rejection, in either direction.
        lows = [o.amount / PENALTY for o in lo.outgoing if not o.accepted and o.amount > 0]
        lows += [x.a for x in lo.incoming if not x.accepted and x.amount > 0 and x.a]
        if lows:
            lo.t_lo = round(max(lows), 2)
        # Upper bound: our own charge rejected with 0 (we know our a).
        if lo.our_a and lo.rejected_zero:
            lo.t_hi = lo.our_a
        if lo.t_hi < lo.t_lo:   # cannot happen under the rules; keep the data honest
            log.warning("line %d: inconsistent bracket [%.2f, %.2f)", lo.line, lo.t_lo, lo.t_hi)
            lo.t_hi = math.inf
    return lines


def transactions_dir(runs_dir: Path) -> Path:
    return runs_dir / "transactions"


def load_cached(cache_dir: Path, game_id: int) -> list[dict] | None:
    path = cache_dir / f"game_{game_id:03d}.json"
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return None


def save_cached(cache_dir: Path, game_id: int, items: list[dict]) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"game_{game_id:03d}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(items))
    tmp.replace(path)


def fetch_transactions(base_url: str, game_id: int, team: str, cache_dir: Path | None = None,
                       timeout_s: float = 15.0) -> list[dict]:
    """All of `team`'s transactions for one game. A non-empty result is cached on disk,
    since a settled game never changes."""
    if cache_dir is not None:
        cached = load_cached(cache_dir, game_id)
        if cached:
            return cached
    items, page = [], 1
    while True:
        r = requests.get(f"{base_url.rstrip('/')}/leaderboard/api/transactions",
                         params={"game_id": game_id, "team": team, "page": page},
                         timeout=timeout_s)
        r.raise_for_status()
        data = r.json()
        items += data.get("items", [])
        if page >= data.get("total_pages", 1):
            break
        page += 1
        time.sleep(0.2)  # be gentle with the public API
    if cache_dir is not None and items:
        save_cached(cache_dir, game_id, items)
    return items
