"""Async transport and acknowledgement checks for the sponsor's documented API."""
import asyncio
import json
from datetime import datetime, timezone
from decimal import Decimal

import httpx

from quantco_fetch import BASE, schedule_starts, validate_key
from simulate_local import wire_items


class Rejected(ValueError):
    def __init__(self, status_code):
        self.status_code = status_code
        super().__init__(f"QuantCo returned HTTP {status_code}")


def timestamp(value):
    result = datetime.fromisoformat(value)
    if result.utcoffset() is None:
        raise ValueError("QuantCo timestamp has no timezone")
    return result.astimezone(timezone.utc)


class TournamentAPI:
    def __init__(self, client):
        self.client = client

    async def request(self, method, path, budget, **kwargs):
        timeout = httpx.Timeout(budget, connect=min(2, budget), pool=min(1, budget), write=min(2, budget))
        async with asyncio.timeout(budget):
            response = await self.client.request(method, BASE + path, timeout=timeout, **kwargs)
        if response.status_code != 200:
            raise Rejected(response.status_code)
        return json.loads(response.content, parse_float=Decimal)

    async def schedule(self, budget=5):
        return schedule_starts(await self.request("GET", "/api/games/list", budget))

    async def key(self, game_id, budget):
        result = await self.request("GET", f"/api/games/{game_id}/key", budget)
        return validate_key(result).encode()

    async def submit(self, game_id, payload, budget):
        return await self.request("PUT", f"/api/games/{game_id}/submissions", budget, json=payload)


def submission_payload(prices, game_id, expected_ids):
    if type(prices["game_id"]) is not int or prices["game_id"] != game_id:
        raise ValueError("submission must match this game")
    if [item["item_id"] for item in prices["items"]] != expected_ids:
        raise ValueError("submission must contain the exact invoice positions for this game")
    return wire_items(prices)


def verify_ack(response, payload, game_id, release, deadline, expected_team):
    if not isinstance(response, list) or len(response) != len(payload):
        raise ValueError("acknowledgement does not contain every submitted row")
    expected = {item["index"]: item for item in payload}
    team = expected_team
    last = release
    for item in response:
        if type(item["team_id"]) is not int or item["team_id"] <= 0:
            raise ValueError("acknowledgement contains an invalid team ID")
        if team is None:
            team = item["team_id"]
        if type(item["game_id"]) is not int or item["game_id"] != game_id or item["team_id"] != team:
            raise ValueError("acknowledgement has the wrong game or team")
        index = item["line_item_index"]
        sent = expected.pop(index, None) if type(index) is int else None
        if sent is None or any(Decimal(str(item[p])) != Decimal(str(sent[p]))
                               for p in ("charge_price", "acceptance_limit")):
            raise ValueError("acknowledgement contains unknown, duplicate or changed prices")
        submitted_at = timestamp(item["submitted_at"])
        if submitted_at < release or (deadline is not None and submitted_at >= deadline):
            raise ValueError("server submission timestamp falls outside the game window")
        last = max(last, submitted_at)
    return team, last
