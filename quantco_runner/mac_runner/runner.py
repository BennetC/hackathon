"""Run the QuantCo tournament from the organizer's official UTC schedule."""
import argparse
import asyncio
from contextlib import AsyncExitStack
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import time
from zipfile import BadZipFile as ZipHeaderError, ZipFile
from zoneinfo import ZoneInfo

import httpx
from pyzipper.zipfile import BadZipFile

from case_pipeline import case_manifest, extract_case, inspection_input
from invoice_rows import DEFAULT_VAT_RATE, checked_vat
from pricing import price_payload
from quantco_fetch import load_team_key
from round_journal import BrokenJournal, Journal, STATE_DIR, SubmissionOwnerBusy, submission_owner
from strategy import STRATEGY_CUTOFF, STRATEGY_DOC_CHARS, run_strategy, strategy_script
from tournament_api import Rejected, TournamentAPI, submission_payload, verify_ack
from valuation import OpenAIValuator, fallback_valuation, merge_valuations

BERLIN = ZoneInfo("Europe/Berlin")
WINDOW = 60
PREPARE_SECONDS = 35
RELEASE_GUARD = .10
MODEL_CUTOFF = 28
BASELINE_TARGET = 35
MIN_PUT_SECONDS = 2
NETWORK_FAILURE = (httpx.TransportError, TimeoutError)
PRE_SEND = (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)


class Clock:
    now = staticmethod(lambda: datetime.now(timezone.utc))
    monotonic = staticmethod(time.monotonic)
    sleep = staticmethod(asyncio.sleep)


class Budget:
    def __init__(self, clock, release, case_zero=False):
        self.clock = clock
        self.start = clock.monotonic()
        self.release = release
        self.initial_age = 0 if case_zero else (clock.now() - release).total_seconds()
        self.case_zero = case_zero

    def age(self):
        elapsed = self.initial_age + self.clock.monotonic() - self.start
        if self.case_zero:
            return elapsed
        return max(elapsed, (self.clock.now() - self.release).total_seconds())

    def remaining(self, cutoff=WINDOW):
        return cutoff - self.age()


def notice(message):
    print(f"\a{message}", file=sys.stderr, flush=True)
    if sys.platform == "darwin":
        try:
            subprocess.Popen(
                ["osascript", "-e", "on run argv", "-e",
                 'display notification (item 1 of argv) with title "QuantCo runner"',
                 "-e", "end run", message],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except OSError:
            pass


def archive_ready(path):
    try:
        with ZipFile(path) as archive:
            files = [item for item in archive.infolist() if not item.is_dir()]
            return bool(files) and all(item.flag_bits & 1 for item in files)
    except (OSError, ZipHeaderError):
        return False


class Runner:
    def __init__(self, api, journal, clock, archive_dir, vat_rate, margin, model=None, alert=notice,
                 *, strategy=None):
        self.api, self.journal, self.clock = api, journal, clock
        self.archives, self.vat_rate, self.margin = archive_dir, vat_rate, margin
        self.model, self.alert = model, alert
        self.strategy = strategy

    async def built_in_prices(self, game_id, fallback, evidence, budget):
        valuation = fallback
        prices = price_payload(fallback)
        model_budget = budget.remaining(min(MODEL_CUTOFF, WINDOW - self.margin - 5))
        if self.model is not None and model_budget >= 1:
            start = self.clock.monotonic()
            valid_count = 0
            self.journal.record(game_id, "PROCESSING", stage="model_start")
            try:
                async with asyncio.timeout(model_budget):
                    estimates = await self.model.analyze(evidence, model_budget)
                candidate, count = merge_valuations(fallback, estimates)
                prices = price_payload(candidate)
                valuation, valid_count = candidate, count
                result = "valued"
            except (httpx.HTTPError, TimeoutError, TypeError, ValueError, KeyError, IndexError,
                    ArithmeticError) as exc:
                result = type(exc).__name__
            self.journal.record(game_id, "PROCESSING", stage="model_finish", result=result,
                                duration_ms=round((self.clock.monotonic() - start) * 1000),
                                valid_estimates=valid_count)
        return valuation, prices

    async def wait_until(self, target):
        while (left := (target - self.clock.now()).total_seconds()) > 0:
            await self.clock.sleep(min(.05 if left <= 5 else left - 5, 20, left))

    async def released_key(self, game_id, budget, cutoff):
        for attempt in range(6):
            remaining = budget.remaining(cutoff)
            if remaining <= .4:
                raise TimeoutError("released key did not arrive within the processing budget")
            try:
                return await self.api.key(game_id, min(2, remaining))
            except Rejected as exc:
                if exc.status_code not in {403, 500, 502, 503, 504}:
                    raise
                reason = str(exc)
            except NETWORK_FAILURE as exc:
                reason = type(exc).__name__
            if attempt == 5:
                break
            pause = min(1.8, .45 * 1.45 ** attempt) + random.uniform(0, .12)
            self.journal.record(game_id, "RETRYING", stage="key", reason=reason)
            await self.clock.sleep(min(pause, max(0, budget.remaining(cutoff) - .4)))
        raise ValueError(f"released key unavailable after bounded retries ({reason})")

    def failure(self, game_id, state, reason, outcome=None):
        self.journal.record(game_id, state, reason=reason, outcome=outcome)
        self.alert(f"Game {game_id} {state.lower()}. {reason}")
        return state

    async def without_ack(self, game_id, deadline, reason, outcome=None):
        self.failure(game_id, "FAILED", reason, outcome=outcome)
        return await self.close_without_ack(game_id, deadline, reason, outcome)

    async def close_without_ack(self, game_id, deadline, reason, outcome=None):
        if deadline is None:
            return "FAILED"
        await self.wait_until(deadline)
        self.journal.record(game_id, "MISSED", reason=reason, outcome=outcome)
        return "MISSED"

    async def submit(self, game_id, release, deadline, payload, budget, team):
        for attempt in range(2):
            # Dispatch with a margin and keep listening for a receipt until
            # the hard cutoff. A short connect timeout leaves room to retry
            # only when the transport can establish that no bytes were sent.
            left = budget.remaining(WINDOW - self.margin)
            if left < MIN_PUT_SECONDS:
                return await self.without_ack(game_id, deadline, "Too little time for a safe submission")
            self.journal.record(game_id, "SUBMITTING", attempt=attempt + 1,
                                payload=payload, remaining_ms=round(budget.remaining() * 1000),
                                baseline_target_met=budget.age() <= BASELINE_TARGET)
            # Recheck after persisting the intent in case of slow disk or sleep.
            left = budget.remaining(WINDOW - self.margin)
            if left < MIN_PUT_SECONDS:
                return await self.without_ack(game_id, deadline, "Submission window elapsed before dispatch",
                                              outcome="not_sent")
            try:
                response = await self.api.submit(game_id, payload, budget.remaining())
            except PRE_SEND as exc:
                self.journal.record(game_id, "RETRYING", stage="submission", outcome="not_sent",
                                    reason=type(exc).__name__)
                if attempt == 0:
                    await self.clock.sleep(.2)
                    continue
                return await self.without_ack(game_id, deadline, "Could not establish a submission connection",
                                              outcome="not_sent")
            except Rejected as exc:
                if exc.status_code in {401, 403, 404, 422}:
                    return await self.without_ack(game_id, deadline, str(exc), outcome="rejected")
                return await self.without_ack(game_id, deadline, str(exc), outcome="ambiguous")
            except (*NETWORK_FAILURE, ValueError, TypeError) as exc:
                return await self.without_ack(
                    game_id, deadline, f"Submission acknowledgement unavailable ({type(exc).__name__})",
                    outcome="ambiguous",
                )
            receipt_time = self.clock.now()
            # Only keep response metadata and prices. Error bodies can echo request data.
            try:
                team_id, accepted = verify_ack(response, payload, game_id, release, deadline, team)
            except (TypeError, KeyError, ValueError, ArithmeticError) as exc:
                return await self.without_ack(game_id, deadline, f"Invalid submission acknowledgement ({exc})",
                                              outcome="ambiguous")
            fields = ("game_id", "team_id", "line_item_index", "charge_price", "acceptance_limit", "submitted_at")
            metadata = [{field: row[field] for field in fields} for row in response]
            self.journal.record(
                game_id, "ACKNOWLEDGED", team_id=team_id, response=json.loads(json.dumps(metadata, default=str)),
                received_at=receipt_time.isoformat(), server_submitted_at=accepted.isoformat(),
                server_remaining_ms=round((deadline - accepted).total_seconds() * 1000) if deadline else None,
                local_remaining_ms=round(budget.remaining() * 1000) if deadline else None,
            )
            self.journal.record(game_id, "CLOSED", result="ACKNOWLEDGED")
            return "ACKNOWLEDGED"

    async def round(self, game_id, release, *, clock_offset=None):
        case_zero = game_id == 0
        deadline = None if case_zero else release + timedelta(seconds=WINDOW)
        try:
            history = self.journal.history(game_id)
        except BrokenJournal as exc:
            self.alert(str(exc))
            if deadline:
                await self.wait_until(deadline)
            return "MISSED" if deadline else "FAILED"
        last = history[-1] if history else {}
        if last.get("state") in {"CLOSED", "MISSED"}:
            return last.get("result", last["state"])
        if last.get("state") == "FAILED":
            return await self.close_without_ack(game_id, deadline, last["reason"], last.get("outcome"))
        if last.get("state") == "ACKNOWLEDGED":
            self.journal.record(game_id, "CLOSED", result="ACKNOWLEDGED")
            return "ACKNOWLEDGED"
        if last.get("state") == "SUBMITTING":
            return await self.without_ack(game_id, deadline, "Prior PUT has no verified acknowledgement",
                                          outcome="ambiguous")

        if deadline and self.clock.now() >= deadline:
            return self.failure(game_id, "MISSED", "Official window already expired")

        self.journal.record(game_id, "WAITING", release=release.isoformat(),
                            deadline=deadline.isoformat() if deadline else None)
        if not case_zero:
            await self.wait_until(release - timedelta(seconds=PREPARE_SECONDS))
        archive = self.archives / f"case_{game_id:03d}.zip"
        ready = archive_ready(archive)
        self.journal.record(game_id, "PREPARING", archive_available=ready,
                            credentials_ready=True, api_ready=True, model_ready=self.model is not None,
                            strategy_ready=self.strategy is not None,
                            expected_game=game_id, prior_round_in_flight=False, clock_offset=clock_offset)
        until_release = (release - self.clock.now()).total_seconds()
        if not case_zero and until_release > 5:
            try:
                revised = (await self.api.schedule(budget=4)).get(game_id)
            except (*NETWORK_FAILURE, ValueError, TypeError, KeyError) as exc:
                if isinstance(exc, Rejected) and exc.status_code == 401:
                    return await self.without_ack(game_id, deadline, "Team key failed preflight authentication")
                reason = str(exc) if isinstance(exc, Rejected) else type(exc).__name__
                self.journal.record(game_id, "PREPARING", stage="schedule_refresh", result=reason)
                self.alert(f"Game {game_id} preflight could not refresh the official schedule.")
            else:
                if revised is None:
                    return await self.without_ack(game_id, deadline, "Game removed from the official schedule")
                if revised != release:
                    release, deadline = revised, revised + timedelta(seconds=WINDOW)
                    self.journal.record(game_id, "WAITING", release=release.isoformat(),
                                        deadline=deadline.isoformat(), reason="official schedule changed")
                    await self.wait_until(release - timedelta(seconds=PREPARE_SECONDS))
                self.journal.record(game_id, "PREPARING", stage="schedule_refresh", result="verified")
        if not ready:
            self.alert(f"Game {game_id} preflight could not read the encrypted archive ({archive.name}).")
        if not case_zero:
            await self.wait_until(release + timedelta(seconds=RELEASE_GUARD))
        woke = self.clock.now()
        budget = Budget(self.clock, release, case_zero)
        self.journal.record(game_id, "RELEASED", actual_wake=woke.isoformat(),
                            remaining_ms=round(budget.remaining() * 1000))
        if budget.remaining(WINDOW - self.margin) < MIN_PUT_SECONDS:
            return await self.without_ack(game_id, deadline, "Woke too late for a safe submission")
        if not ready and not archive_ready(archive):
            return await self.without_ack(game_id, deadline, f"Staged archive missing or invalid ({archive.name})")
        self.journal.record(game_id, "PROCESSING")
        try:
            with tempfile.TemporaryDirectory(prefix=f"case-{game_id}-", dir=self.journal.directory) as temporary:
                root = Path(temporary) / "decrypted"
                spare = budget.remaining(WINDOW - self.margin - MIN_PUT_SECONDS)
                key_cutoff = min(WINDOW - self.margin - MIN_PUT_SECONDS,
                                 max(15, budget.age() + min(8, max(.5, spare / 2))))
                for extraction_attempt in range(2):
                    key = await self.released_key(game_id, budget, key_cutoff)
                    self.journal.record(game_id, "PROCESSING", stage="key_retrieved",
                                        elapsed_ms=round(budget.age() * 1000))
                    try:
                        extract_case(archive, root, key, require_encrypted=True)
                        break
                    except (ValueError, BadZipFile) as exc:
                        if extraction_attempt or budget.remaining(key_cutoff) < 2:
                            raise
                        self.journal.record(game_id, "RETRYING", stage="decrypt", reason=str(exc))
                        await self.clock.sleep(.6)
                self.journal.record(game_id, "PROCESSING", stage="decrypted",
                                    elapsed_ms=round(budget.age() * 1000))
                manifest = case_manifest(root, game_id, vat_rate=self.vat_rate)
                evidence = inspection_input(manifest, root, max_doc_chars=STRATEGY_DOC_CHARS)
                ids = manifest["expected_item_ids"]
                self.journal.record(game_id, "PROCESSING", stage="parsed", items=len(ids),
                                    images=len(evidence["images"]), elapsed_ms=round(budget.age() * 1000))
                if self.strategy is None:
                    fallback = fallback_valuation(manifest, evidence)
                else:
                    self.journal.record(game_id, "PROCESSING", stage="strategy_start")
                    prices, payload = await run_strategy(
                        self.strategy, game_id, root, evidence, ids, budget.remaining(STRATEGY_CUTOFF),
                    )
                    if budget.remaining(STRATEGY_CUTOFF) <= 0:
                        raise TimeoutError("Strategy exceeded the round cutoff")
            if self.strategy is None:
                valuation, prices = await self.built_in_prices(game_id, fallback, evidence, budget)
                payload = submission_payload(prices, game_id, ids)
                pricing_source = "built-in"
            else:
                valuation = None
                pricing_source = "strategy"
            self.journal.record(game_id, "PROCESSING", stage="priced", valuation=valuation, prices=prices,
                                pricing_source=pricing_source,
                                elapsed_ms=round(budget.age() * 1000))
        except (OSError, ValueError, TypeError, KeyError, ArithmeticError, BadZipFile) as exc:
            return await self.without_ack(game_id, deadline, str(exc))
        return await self.submit(game_id, release, deadline, payload, budget, self.journal.team_id())

    async def run(self, schedule, *, first_game=1, only_game=None, clock_offset=None, wait_for_owner=0):
        rounds = sorted((release, game_id) for game_id, release in schedule.items()
                        if game_id == only_game or (only_game is None and game_id >= first_game))
        if not rounds:
            raise ValueError("selected round range is absent from the official schedule")
        results = {}
        for index, (release, game_id) in enumerate(rounds):
            release_local = release.astimezone(BERLIN).isoformat(timespec="seconds")
            lock_wait = wait_for_owner
            if game_id != 0:
                print(f"Waiting for Game {game_id}, scheduled for {release_local}.", flush=True)
                await self.wait_until(release - timedelta(seconds=PREPARE_SECONDS))
                remaining = (release - self.clock.now()).total_seconds() + WINDOW - self.margin
                lock_wait = min(lock_wait, max(0, remaining))
            try:
                with submission_owner(self.journal.directory, wait_seconds=lock_wait):
                    result = await self.round(game_id, release, clock_offset=clock_offset)
            except SubmissionOwnerBusy:
                self.alert(f"Game {game_id} skipped. Another local worker owns submission.")
                result = "SKIPPED"
            results[game_id] = result
            next_time = (rounds[index + 1][0].astimezone(BERLIN).isoformat(timespec="seconds")
                         if index + 1 < len(rounds) else "none")
            print(f"Game {game_id} {result.lower()}. Next selected release {next_time}.", flush=True)
        return results


def clock_offset():
    if sys.platform != "darwin":
        return None
    try:
        result = subprocess.run(["sntp", "-t", "2", "time.apple.com"],
                                capture_output=True, text=True, timeout=3, check=True)
        return result.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


async def operate(args, directory, team_key):
    clock = Clock()
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    async with AsyncExitStack() as stack:
        client = await stack.enter_async_context(httpx.AsyncClient(
            headers={"X-API-Key": team_key}, trust_env=False, follow_redirects=False,
            limits=httpx.Limits(keepalive_expiry=45),
        ))
        api = TournamentAPI(client)
        journal = Journal(directory, clock)
        openai_key = (os.getenv("OPENAI_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
        model = None
        if openai_key and not args.no_llm and args.strategy is None:
            client = await stack.enter_async_context(httpx.AsyncClient(
                headers={"Authorization": f"Bearer {openai_key}"}, trust_env=False,
                follow_redirects=False,
            ))
            model = OpenAIValuator(client, args.model)
        runner = Runner(api, journal, clock, args.archives, args.vat_rate, args.safety_margin, model,
                        strategy=args.strategy)
        offset = clock_offset()
        for attempt in range(3):
            try:
                schedule = await api.schedule()
                break
            except NETWORK_FAILURE:
                if attempt == 2:
                    raise
                await clock.sleep(1)
        game_id = args.game if args.game is not None else args.from_game
        if game_id not in schedule:
            raise ValueError(f"game {game_id} does not appear on the official schedule")
        pricing = "teammate strategy" if args.strategy else "built-in model" if model else "deterministic"
        print(f"Loaded {len(schedule)} official releases. First selected game {game_id}. "
              f"Pricing {pricing}. SNTP {offset or 'unavailable'}.", flush=True)
        results = await runner.run(schedule, first_game=args.from_game, only_game=args.game, clock_offset=offset,
                                   wait_for_owner=args.wait_for_owner)
        return int(args.game is not None and results[args.game] != "ACKNOWLEDGED")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--game", type=int, help="run exactly one game (0 is the permanent test)")
    choice.add_argument("--from-game", type=int, default=1, help="run this game and all later games")
    parser.add_argument("--archives", type=Path, required=True, help="directory containing case_NNN.zip")
    parser.add_argument("--key-file", type=Path, help="override TEAM_API_KEY or the private local team key file")
    parser.add_argument("--vat-rate", type=Decimal, default=DEFAULT_VAT_RATE)
    parser.add_argument("--safety-margin", type=float, default=2)
    parser.add_argument("--wait-for-owner", type=int, default=0,
                        help="seconds to wait if another local runner owns submission")
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"))
    analysis = parser.add_mutually_exclusive_group()
    analysis.add_argument("--no-llm", action="store_true")
    analysis.add_argument("--strategy", help="Python script that analyzes each case and returns final prices")
    args = parser.parse_args()
    try:
        if args.strategy is not None:
            args.strategy = strategy_script(args.strategy)
        checked_vat(args.vat_rate)
        if not 0 < args.safety_margin <= 15:
            raise ValueError("safety margin must be greater than zero and at most 15 seconds")
        if args.wait_for_owner < 0:
            raise ValueError("lock wait must be nonnegative")
        if args.from_game < 1 or (args.game is not None and args.game < 0):
            raise ValueError("select game 0 explicitly, or choose a positive tournament game")
        return asyncio.run(operate(args, STATE_DIR, load_team_key(args.key_file)))
    except NETWORK_FAILURE as exc:
        notice(f"QuantCo runner stopped. Schedule connection failed ({type(exc).__name__}).")
        return 2
    except (OSError, ValueError, TypeError, KeyError, InvalidOperation) as exc:
        notice(f"QuantCo runner stopped. {type(exc).__name__}: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
