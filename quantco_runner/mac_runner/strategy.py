"""Run a teammate's analysis and pricing script with a bounded JSON protocol."""

import asyncio
from contextlib import suppress
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import time

from tournament_api import submission_payload


STRATEGY_CUTOFF = 32
STRATEGY_DOC_CHARS = 120_000
MAX_RESULT_BYTES = 1_000_000


def strategy_script(value):
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"strategy script is not a file: {path}")
    return path


async def run_strategy(script, game_id, case_dir, evidence, expected_ids, budget):
    """Return validated internal prices and the matching QuantCo wire payload."""
    if budget <= 0:
        raise TimeoutError("Strategy budget elapsed before launch")
    deadline = time.monotonic() + budget
    request = {
        "game_id": game_id,
        "case_dir": str(case_dir.resolve()),
        "evidence": evidence,
        "expected_item_ids": expected_ids,
        "budget_seconds": budget,
    }
    env = {key: value for key, value in os.environ.items() if key != "TEAM_API_KEY"}
    with tempfile.TemporaryFile() as stdin, tempfile.TemporaryFile() as stdout:
        stdin.write(json.dumps(request, ensure_ascii=False).encode("utf-8"))
        stdin.seek(0)
        process = await asyncio.create_subprocess_exec(
            sys.executable, str(script), stdin=stdin, stdout=stdout,
            stderr=asyncio.subprocess.DEVNULL, env=env, start_new_session=True,
        )
        try:
            async with asyncio.timeout(deadline - time.monotonic()):
                await process.wait()
        except (TimeoutError, asyncio.CancelledError):
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            await process.wait()
            raise
        if process.returncode:
            raise ValueError(f"Strategy script exited with status {process.returncode}")
        stdout.seek(0)
        result = stdout.read(MAX_RESULT_BYTES + 1)
    if len(result) > MAX_RESULT_BYTES:
        raise ValueError("Strategy response exceeds the size limit")
    try:
        prices = json.loads(result.decode("utf-8"))
    except (RecursionError, ValueError) as exc:
        raise ValueError("Strategy stdout must contain a single UTF-8 JSON object") from exc
    if not isinstance(prices, dict) or not isinstance(prices.get("items"), list):
        raise ValueError("Strategy response must be an object with an items array")
    try:
        payload = submission_payload(prices, game_id, expected_ids)
    except (ArithmeticError, KeyError, TypeError) as exc:
        raise ValueError(f"Strategy response has missing or invalid price fields ({type(exc).__name__})") from exc
    if time.monotonic() >= deadline:
        raise TimeoutError("Strategy validation exceeded its time budget")
    # Keep only the pricing fields in private output and round journals.
    prices = {"game_id": game_id, "items": [
        {key: row[key] for key in ("item_id", "charge_cents", "limit_cents")}
        for row in prices["items"]
    ]}
    return prices, payload
