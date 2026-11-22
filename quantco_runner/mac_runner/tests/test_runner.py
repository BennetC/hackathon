import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

import httpx
import pyzipper

from pricing import price_payload
from quantco_fetch import load_team_key, schedule_starts
from round_journal import Journal, submission_owner
from runner import BERLIN, Budget, Runner
from strategy import run_strategy
from tournament_api import TournamentAPI, verify_ack
from valuation import OpenAIValuator, merge_valuations
from test_offline_replay import make_invoice

RELEASE = datetime(2026, 11, 21, 13, tzinfo=timezone.utc)
CASE_ZERO = datetime(2020, 1, 1, tzinfo=timezone.utc)
PASSWORD = b"fixture-password"


class FakeClock:
    def __init__(self, now):
        self.wall = now
        self.elapsed = 0

    def now(self):
        return self.wall

    def monotonic(self):
        return self.elapsed

    async def sleep(self, seconds):
        self.wall += timedelta(seconds=seconds)
        self.elapsed += seconds


def receipt(game, payload, submitted_at):
    return [{
        "game_id": game, "team_id": 6, "line_item_index": row["index"],
        "charge_price": row["charge_price"], "acceptance_limit": row["acceptance_limit"],
        "submitted_at": submitted_at.isoformat(),
    } for row in payload]


def create_case(directory, game):
    invoice = directory / "invoice.pdf"
    make_invoice(invoice, [[
        ("1", "Leak detection", "2.5", "hrs", ""),
        ("2", "Annual service of boiler", "1", "pcs", ""),
    ]])
    path = directory / f"case_{game:03d}.zip"
    with pyzipper.AESZipFile(path, "w", encryption=pyzipper.WZ_AES) as archive:
        archive.setpassword(PASSWORD)
        archive.write(invoice, "invoices.pdf")
        archive.writestr("policy.txt", "Exclusions\n3.1 Maintenance, servicing or descaling.")
        archive.writestr("description.txt", "Copper supply pipe leak. Includes locating the leak only.")
        archive.writestr("photo.jpg", b"fixture-image-content")
    invoice.unlink()


class TimingTests(TestCase):
    def test_berlin_schedule(self):
        official = {
            0: "2020-01-01T00:00:00Z", 1: "2026-11-21T13:00:00Z",
            2: "2026-11-21T13:13:20Z", 3: "2026-11-21T13:26:40Z",
            4: "2026-11-21T13:40:00Z", 5: "2026-11-21T13:53:20Z",
            100: "2026-11-22T11:00:00Z",
        }
        starts = schedule_starts([{"id": game, "start_time": ts} for game, ts in official.items()])
        berlin_times = ["21 14:00:00", "21 14:13:20", "21 14:26:40", "21 14:40:00",
                        "21 14:53:20", "22 12:00:00"]
        for game, berlin in zip((1, 2, 3, 4, 5, 100), berlin_times):
            self.assertEqual(starts[game], starts[1] + timedelta(seconds=800 * (game - 1)))
            self.assertEqual(starts[game].astimezone(BERLIN).strftime("%d %H:%M:%S"), berlin)
        with self.assertRaisesRegex(ValueError, "timezone"):
            schedule_starts([{"id": 1, "start_time": "2026-11-21T13:00:00"}])

    def test_two_owners(self):
        with TemporaryDirectory() as directory, submission_owner(Path(directory)):
            result = subprocess.run(
                [sys.executable, "-c", (
                    "from pathlib import Path; import sys; "
                    "from round_journal import submission_owner; "
                    "lock = submission_owner(Path(sys.argv[1])); lock.__enter__()"
                ), directory],
                capture_output=True, text=True, timeout=3,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("another local tournament runner owns submission", result.stderr)

    def test_eight_second_late_wake_and_wall_clock_jump(self):
        clock = FakeClock(RELEASE + timedelta(seconds=8))
        budget = Budget(clock, RELEASE)
        self.assertEqual(budget.remaining(), 52)
        self.assertEqual(budget.remaining(28), 20)
        clock.wall -= timedelta(seconds=10)
        clock.elapsed += 3
        self.assertEqual(budget.remaining(), 49)
        clock.wall += timedelta(seconds=35)
        self.assertEqual(budget.remaining(), 27)

    def test_receipt_requires_correct_team_game_rows_amounts_and_time(self):
        payload = [{"index": 1, "charge_price": 15.3, "acceptance_limit": 17.0}]
        response = receipt(1, payload, RELEASE + timedelta(seconds=59))
        deadline = RELEASE + timedelta(seconds=60)
        self.assertEqual(verify_ack(response, payload, 1, RELEASE, deadline, 6)[0], 6)
        for key, value in [
            ("game_id", 2), ("team_id", 5), ("line_item_index", 2), ("charge_price", 16),
            ("submitted_at", deadline.isoformat()),
        ]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                verify_ack([{**response[0], key: value}], payload, 1, RELEASE, deadline, 6)

    def test_team_key_can_be_reused_without_shell_configuration(self):
        with TemporaryDirectory() as directory:
            canonical = Path(directory) / "team.key"
            legacy = Path(directory) / "legacy.key"
            legacy.write_text("legacy-fixture\n")
            with patch("quantco_fetch.TEAM_KEY_FILES", (canonical, legacy)), patch.dict(
                "os.environ", {"TEAM_API_KEY": ""}
            ):
                self.assertEqual(load_team_key(), "legacy-fixture")
                canonical.write_text("canonical-fixture\n")
                self.assertEqual(load_team_key(), "canonical-fixture")
                self.assertEqual(load_team_key(legacy), "legacy-fixture")
                with patch.dict("os.environ", {"TEAM_API_KEY": "fixture-from-env"}):
                    self.assertEqual(load_team_key(), "fixture-from-env")


class RoundTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.clock = FakeClock(RELEASE - timedelta(seconds=45))
        self.journal = Journal(self.directory, self.clock)
        self.alerts = []
        self.releases = {0: CASE_ZERO, 1: RELEASE, 2: RELEASE + timedelta(seconds=800)}
        self.requests = []
        self.puts = []
        self.delay = 0
        self.timeout = False
        self.key_for_attempt = lambda _attempt: PASSWORD
        self.keys_requested = 0

    def events(self, game):
        return self.journal.history(game)

    async def transport(self, request):
        self.assertEqual(request.headers["X-API-Key"], "fixture-team")
        self.requests.append((request.method, request.url.path, self.clock.now()))
        path = request.url.path
        if path == "/api/games/list":
            self.assertEqual(request.method, "GET")
            return httpx.Response(200, json=[
                {"id": game, "start_time": time.isoformat()} for game, time in self.releases.items()
            ])
        game = int(path.split("/")[3])
        self.assertGreaterEqual(self.clock.now(), self.releases[game])
        if path.endswith("/key"):
            self.assertEqual(request.method, "GET")
            self.keys_requested += 1
            return httpx.Response(200, json={"decryption_key": self.key_for_attempt(self.keys_requested).decode()})
        self.assertEqual((request.method, path), ("PUT", f"/api/games/{game}/submissions"))
        payload = json.loads(request.content)
        self.assertEqual([row["index"] for row in payload], [1, 2])
        self.assertEqual(set(payload[0]), {"index", "charge_price", "acceptance_limit"})
        self.puts.append((game, payload, self.clock.now()))
        await self.clock.sleep(self.delay)
        if self.timeout:
            raise httpx.ReadTimeout("mock delayed acknowledgement", request=request)
        return httpx.Response(200, json=receipt(game, payload, self.clock.now()))

    async def create_runner(self, model=None, *, strategy=None):
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(self.transport), headers={"X-API-Key": "fixture-team"},
        )
        self.addAsyncCleanup(client.aclose)
        return Runner(TournamentAPI(client), self.journal, self.clock, self.directory, Decimal(".19"),
                      2, model, self.alerts.append, strategy=strategy)

    async def test_case_zero_wire_and_acknowledgement(self):
        create_case(self.directory, 0)
        runner = await self.create_runner()
        schedule = await runner.api.schedule()
        self.assertEqual(await runner.run(schedule, only_game=0), {0: "ACKNOWLEDGED"})
        self.assertEqual(self.journal.team_id(), 6)
        self.assertEqual([event["state"] for event in self.events(0)][-3:],
                         ["SUBMITTING", "ACKNOWLEDGED", "CLOSED"])
        self.assertEqual(self.puts[0][1][1], {"index": 2, "charge_price": 0, "acceptance_limit": 0})
        self.assertEqual(next(e for e in self.events(0) if e.get("stage") == "parsed")["images"], 1)

    async def test_strategy_submission_continues_after_a_round_with_missing_prices(self):
        self.releases[3] = self.releases[2] + timedelta(seconds=800)
        for game in (1, 2, 3):
            create_case(self.directory, game)
        script = self.directory / "teammate.py"
        script.write_text("""
import json
import os
from pathlib import Path
import sys

request = json.load(sys.stdin)
game = request["game_id"]
evidence = request["evidence"]
root = Path(request["case_dir"])
assert "TEAM_API_KEY" not in os.environ
assert (root / evidence["images"][0]).is_file()
assert "Maintenance" in evidence["documents"]["policy"]
assert [row["item_id"] for row in evidence["rows"]] == request["expected_item_ids"]
assert 0 < request["budget_seconds"] < 32
ids = request["expected_item_ids"][:1] if game == 2 else request["expected_item_ids"]
json.dump({"game_id": game, "items": [
    {"item_id": item_id, "charge_cents": 1000 * game + item_id, "limit_cents": 4500}
    for item_id in ids
]}, sys.stdout)
""", encoding="utf-8")
        runner = await self.create_runner(strategy=script)
        with patch.dict("os.environ", {"TEAM_API_KEY": "fixture-team"}), patch(
            "runner.fallback_valuation", side_effect=AssertionError("built-in analysis called")
        ), patch("runner.price_payload", side_effect=AssertionError("built-in pricing called")):
            results = await runner.run(await runner.api.schedule(), first_game=1)
            restarted = await self.create_runner(strategy=script)
            self.assertEqual(await restarted.run(self.releases, first_game=1), results)

        self.assertEqual(results, {1: "ACKNOWLEDGED", 2: "MISSED", 3: "ACKNOWLEDGED"})
        self.assertEqual([game for game, _, _ in self.puts], [1, 3])
        for game, payload, sent_at in self.puts:
            self.assertEqual(payload[0], {"index": 1, "charge_price": 10 * game + .01, "acceptance_limit": 45})
            self.assertLess(sent_at, self.releases[game] + timedelta(seconds=35))
            self.assertTrue(any(event.get("pricing_source") == "strategy" for event in self.events(game)))
        self.assertFalse(any(event["state"] == "SUBMITTING" for event in self.events(2)))

    async def test_hanging_strategy_is_stopped_at_cutoff(self):
        script = self.directory / "stalled.py"
        script.write_text("import time\ntime.sleep(5)\n", encoding="utf-8")
        with self.assertRaises(TimeoutError):
            await run_strategy(script, 1, self.directory, {}, [1], .1)

    async def test_stalled_model_is_cancelled_and_fallback_is_sent(self):
        create_case(self.directory, 1)
        clock = self.clock
        cancelled = False

        class HungModel:
            async def analyze(self, evidence, budget):
                nonlocal cancelled
                try:
                    await asyncio.sleep(3600)
                finally:
                    cancelled = True
                    await clock.sleep(budget)

        runner = await self.create_runner(HungModel())
        with patch("runner.MODEL_CUTOFF", 1.2):
            self.assertEqual(await runner.round(1, RELEASE), "ACKNOWLEDGED")
        self.assertTrue(cancelled)
        finished = next(e for e in self.events(1) if e.get("stage") == "model_finish")
        self.assertEqual(finished["result"], "TimeoutError")
        self.assertGreater(self.puts[0][1][0]["charge_price"], 0)
        self.assertLess(self.puts[0][2], RELEASE + timedelta(seconds=35))

    async def test_temporary_bad_key_is_retried(self):
        create_case(self.directory, 1)
        self.key_for_attempt = lambda attempt: b"incorrect-fixture-key" if attempt == 1 else PASSWORD
        runner = await self.create_runner()
        self.assertEqual(await runner.round(1, RELEASE), "ACKNOWLEDGED")
        self.assertEqual(self.keys_requested, 2)
        self.assertEqual(len(self.puts), 1)

    async def test_expired_ack_or_timeout_never_retries_put(self):
        create_case(self.directory, 1)
        create_case(self.directory, 2)
        runner = await self.create_runner()
        self.delay = 62
        self.assertEqual(await runner.round(1, RELEASE), "MISSED")
        self.delay = 10
        self.timeout = True
        self.assertEqual(await runner.round(2, self.releases[2]), "MISSED")
        for game in (1, 2):
            events = self.events(game)
            self.assertFalse(any(event["state"] == "ACKNOWLEDGED" for event in events))
            self.assertEqual(events[-1]["outcome"], "ambiguous")
            self.assertEqual(len([put for put in self.puts if put[0] == game]), 1)

    async def test_restart_between_games_skips_acknowledged_or_ambiguous_puts(self):
        create_case(self.directory, 1)
        create_case(self.directory, 2)
        original = await self.create_runner()
        self.assertEqual(await original.round(1, RELEASE), "ACKNOWLEDGED")
        restarted = await self.create_runner()
        self.assertEqual(await restarted.run(self.releases, first_game=1), {1: "ACKNOWLEDGED", 2: "ACKNOWLEDGED"})
        self.assertEqual([put[0] for put in self.puts], [1, 2])
        self.journal.record(3, "SUBMITTING", payload=[])
        self.assertEqual(await restarted.round(3, self.releases[2] + timedelta(seconds=800)), "MISSED")
        self.assertEqual([put[0] for put in self.puts], [1, 2])

    async def test_eight_seconds_late_and_expired_round_skip_preflight_network(self):
        create_case(self.directory, 1)
        await self.clock.sleep(53)
        runner = await self.create_runner()
        self.assertEqual(await runner.round(1, RELEASE), "ACKNOWLEDGED")
        released = next(e for e in self.events(1) if e["state"] == "RELEASED")
        self.assertEqual(released["remaining_ms"], 52_000)
        await self.clock.sleep(900)
        self.assertEqual(await runner.round(2, self.releases[2]), "MISSED")
        self.assertEqual([r[1] for r in self.requests], ["/api/games/1/key", "/api/games/1/submissions"])

    async def test_revised_official_release_moves_the_key_request(self):
        create_case(self.directory, 1)
        self.releases[1] += timedelta(seconds=7)
        runner = await self.create_runner()
        self.assertEqual(await runner.round(1, RELEASE), "ACKNOWLEDGED")
        key_time = next(at for _, path, at in self.requests if path.endswith("/key"))
        self.assertGreaterEqual(key_time, self.releases[1])
        self.assertEqual(self.events(1)[-2]["server_remaining_ms"], 59_900)

    async def test_torn_journal_blocks_only_its_own_game(self):
        create_case(self.directory, 2)
        (self.directory / "game-1.jsonl").write_bytes(b'{"state":"SUBMITTING"')
        runner = await self.create_runner()
        results = await runner.run(self.releases, first_game=1)
        self.assertEqual(results, {1: "MISSED", 2: "ACKNOWLEDGED"})
        self.assertEqual([put[0] for put in self.puts], [2])

    async def test_whole_http_request_timeout_cancels_hanging_transport(self):
        cancelled = asyncio.Event()

        async def hanging(_):
            try:
                await asyncio.sleep(3600)
            finally:
                cancelled.set()

        async with httpx.AsyncClient(transport=httpx.MockTransport(hanging)) as client:
            with self.assertRaises(TimeoutError):
                await TournamentAPI(client).submit(1, [], .01)
        self.assertTrue(cancelled.is_set())

    async def test_model_sends_one_structured_request_with_all_items(self):
        estimate = {"item_id": 1, "coverage": "yes", "relevance": "yes", "low_gross_cents": 5,
                    "fair_gross_cents": 7, "high_gross_cents": 9, "confidence": 80, "evidence": "Example"}
        requests = []

        async def transport(request):
            requests.append(request)
            payload = json.loads(request.content)
            self.assertEqual(payload["model"], "configured-model")
            self.assertTrue(payload["response_format"]["json_schema"]["strict"])
            self.assertEqual(len(json.loads(payload["messages"][1]["content"])["invoice_rows"]), 2)
            return httpx.Response(200, json={
                "choices": [{"message": {"content": json.dumps({"items": [estimate]})}}],
            })

        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
            model = OpenAIValuator(client, "configured-model")
            evidence = {"documents": {"policy": "Policy", "damage": "Claim"},
                        "rows": [{"item_id": 1}, {"item_id": 2}]}
            self.assertEqual(await model.analyze(evidence, 1), [estimate])
        self.assertEqual(len(requests), 1)


class ValuationTests(TestCase):
    def test_valid_estimates_survive_invalid_and_missing_rows_without_repricing_vat(self):
        def item(index):
            return {"item_id": index, "quantity": "2", "vat_rate": ".19", "unit": "pcs",
                    "coverage": "uncertain", "relevance": "uncertain", "eligible_samples": 100,
                    "unit_price_band_net_cents": [10_000, 10_000, 10_000]}
        fallback = {"game_id": 0, "expected_item_ids": [1, 2, 3],
                    "items": [item(i) for i in (1, 2, 3)]}

        def estimate(index, coverage):
            return {"item_id": index, "coverage": coverage, "relevance": "yes",
                    "low_gross_cents": 20_000, "fair_gross_cents": 20_000, "high_gross_cents": 20_000,
                    "confidence": 90, "evidence": "Claim evidence"}

        merged, count = merge_valuations(fallback, [
            estimate(2, "no"), {"item_id": 3, "coverage": "yes"}, estimate(1, "yes"), estimate(99, "yes"),
        ])
        self.assertEqual(count, 2)
        self.assertEqual([line["limit_cents"] for line in price_payload(merged)["items"]], [20_000, 0, 23_800])
        self.assertEqual(merged["items"][0]["quantity"], "2")
