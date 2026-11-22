"""FDN Bench uploader: build EUR prediction payloads and POST to `/api/runs`."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import requests

from claimbot.models import LinePrice
from claimbot.strategies.base import LineValuation

DEFAULT_BENCH_URL = "https://bench.159-195-78-137.sslip.io"


class BenchError(RuntimeError):
    """Raised when uploading a run to FDN Bench fails."""


def build_prediction(
    game_id: int,
    quotes: Iterable[LinePrice],
    *,
    valuations: Iterable[LineValuation] | None = None,
    latency_ms: float | None = None,
) -> dict[str, Any]:
    """Build one FDN Bench EUR prediction entry from `LinePrice` + optional `LineValuation`s."""
    val_by_index = {v.index: v for v in (valuations or [])}
    items: list[dict[str, Any]] = []
    for q in quotes:
        item: dict[str, Any] = {
            "index": int(q.index),
            "a": float(q.a),
            "b": float(q.b),
        }
        v = val_by_index.get(q.index)
        if v is not None:
            for field in ("low", "fair", "high"):
                val = getattr(v, field)
                if val is not None:
                    item[field] = float(val)
            for field in ("covered", "related"):
                val = getattr(v, field)
                if val is not None:
                    item[field] = bool(val)
        items.append(item)

    pred: dict[str, Any] = {"game_id": int(game_id), "items": items}
    if latency_ms is not None:
        pred["latency_ms"] = round(float(latency_ms), 1)
    return pred


def push_run(
    bench_url: str,
    bench_token: str,
    *,
    strategy_name: str,
    author: str,
    predictions: list[dict[str, Any]],
    timeout_s: float = 10.0,
) -> dict[str, Any]:
    """POST one or more game predictions to FDN Bench (`POST /api/runs`)."""
    base = (bench_url or DEFAULT_BENCH_URL).strip().rstrip("/")
    token = (bench_token or "").strip()
    if not token:
        raise BenchError("CLAIMBOT_BENCH_TOKEN is not set")
    if not strategy_name:
        raise BenchError("strategy_name is required")
    if not predictions:
        raise BenchError("predictions must not be empty")

    url = f"{base}/api/runs"
    payload = {
        "strategy_name": strategy_name,
        "author": author or "fdn",
        "predictions": predictions,
    }
    try:
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout_s,
        )
    except requests.RequestException as exc:
        raise BenchError(f"POST {url} failed: {exc}") from exc

    if not resp.ok:
        body = (resp.text or "").strip()[:300]
        raise BenchError(f"POST {url} returned HTTP {resp.status_code}: {body}")

    try:
        data = resp.json()
        return data if isinstance(data, dict) else {"response": data}
    except ValueError:
        return {"status": resp.status_code}
