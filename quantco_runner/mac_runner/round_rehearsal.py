"""Single-round timing and write checks for a fake or loopback QuantCo API.

The standalone offline entry point is replay_case.py. This module has no
production transport or command-line sender.
"""

import asyncio
import json
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from case_pipeline import _assessment_rows, case_manifest, extract_case
from invoice_rows import DEFAULT_VAT_RATE
from pricing import price_payload
from round_journal import Journal, submission_owner
from simulate_local import wire_items
from tournament_api import verify_ack


BASELINE_BY = 35
OVERWRITE_BEFORE = 50
HARD_CLOSE = 60


class Clock:
    now = staticmethod(lambda: datetime.now(timezone.utc))
    monotonic = staticmethod(time.monotonic)
    sleep = staticmethod(asyncio.sleep)


class RoundWindow:
    def __init__(self, clock, release):
        self.clock, self.release = clock, release
        now = clock.now()
        self.zero = clock.monotonic() - (now - release).total_seconds()

    def remaining(self, offset):
        return self.zero + offset - self.clock.monotonic()

    def require(self, offset):
        remaining = self.remaining(offset)
        if remaining <= 0:
            raise TimeoutError("round cutoff elapsed")
        return remaining

    def elapsed_ms(self):
        return round((self.clock.monotonic() - self.zero) * 1000)


def manual_assessment(path):
    """Read an atomically published local JSON file once it exists."""
    async def assess(_manifest):
        while not path.exists():
            await asyncio.sleep(.1)
        if not path.is_file() or path.stat().st_size > 1_000_000:
            raise ValueError("expected a bounded regular assessment file")
        return json.loads(path.read_text(encoding="utf-8"))

    return assess


async def _write(api, journal, window, game, stage, payload, *, start_before, finish_by, team=None):
    window.require(start_before)
    # A restart after this record treats the outcome as ambiguous unless we
    # have a complete acknowledgement. Never repeat a prior write.
    journal.record(game, "attempted", stage=stage, elapsed_ms=window.elapsed_ms())
    try:
        window.require(start_before)
        remaining = window.require(finish_by)
        async with asyncio.timeout(remaining):
            response = await api.submit(game, payload, remaining)
        window.require(finish_by)
        team, _ = verify_ack(
            response, payload, game, window.release,
            window.release + timedelta(seconds=HARD_CLOSE), team,
        )
    except Exception as exc:
        journal.record(game, "write_unconfirmed", stage=stage, reason=type(exc).__name__)
        return None
    journal.record(game, "acknowledged", stage=stage, rows=len(payload), elapsed_ms=window.elapsed_ms())
    return team


async def rehearse_round(api, game, release, archive, state, *, assessment=None,
                         clock=None, vat_rate=DEFAULT_VAT_RATE):
    """Run one bounded rehearsal using an injected key and submission transport."""
    clock = clock or Clock()
    if release.utcoffset() is None:
        raise ValueError("release must be timezone-aware")
    release = release.astimezone(timezone.utc)
    if type(game) is not int or game < 0 or archive.name != f"case_{game:03d}.zip" or not archive.is_file():
        raise ValueError("staged case does not match the selected game")
    with submission_owner(state):
        journal = Journal(state, clock)
        if any(event["state"] == "attempted" for event in journal.history(game)):
            return "prior_write"
        while (until_release := (release - clock.now()).total_seconds()) > 0:
            await clock.sleep(min(1, until_release))
        window = RoundWindow(clock, release)
        journal.record(game, "released", release=release.isoformat(), elapsed_ms=window.elapsed_ms())
        try:
            remaining = window.require(BASELINE_BY)
            async with asyncio.timeout(remaining):
                key = await api.key(game, remaining)
                window.require(BASELINE_BY)
                journal.record(game, "key_ready", elapsed_ms=window.elapsed_ms())
                with tempfile.TemporaryDirectory(dir=state) as scratch:
                    root = Path(scratch) / "case"
                    extract_case(archive, root, key, require_encrypted=True)
                    manifest = case_manifest(root, game, vat_rate=vat_rate)
                ids = manifest["expected_item_ids"]
                baseline = wire_items(price_payload(manifest), expected_ids=ids)
            journal.record(game, "baseline_ready", rows=len(ids), elapsed_ms=window.elapsed_ms())
            team = await _write(
                api, journal, window, game, "baseline", baseline,
                start_before=BASELINE_BY, finish_by=BASELINE_BY,
            )
        except Exception as exc:
            journal.record(game, "baseline_unavailable", reason=type(exc).__name__,
                           elapsed_ms=window.elapsed_ms())
            return "baseline_unavailable"
        if team is None:
            return "baseline_unconfirmed"
        if assessment is None:
            journal.record(game, "baseline_kept", reason="assessment_absent")
            return "baseline_acknowledged"
        try:
            async with asyncio.timeout(window.require(OVERWRITE_BEFORE)):
                analysis = await assessment(manifest)
                if type(analysis["game_id"]) is not int or analysis["game_id"] != game:
                    raise ValueError("assessment does not match the active game")
                refined = wire_items(price_payload(_assessment_rows(manifest, analysis)), expected_ids=ids)
            window.require(OVERWRITE_BEFORE)
            if refined == baseline:
                journal.record(game, "baseline_kept", reason="unchanged")
                return "baseline_acknowledged"
        except Exception as exc:
            journal.record(game, "baseline_kept", reason=type(exc).__name__, elapsed_ms=window.elapsed_ms())
            return "baseline_acknowledged"
        try:
            confirmed = await _write(
                api, journal, window, game, "overwrite", refined,
                start_before=OVERWRITE_BEFORE, finish_by=HARD_CLOSE, team=team,
            )
        except TimeoutError:
            journal.record(game, "baseline_kept", reason="overwrite_cutoff", elapsed_ms=window.elapsed_ms())
            return "baseline_acknowledged"
        return "overwrite_acknowledged" if confirmed is not None else "overwrite_unconfirmed"
