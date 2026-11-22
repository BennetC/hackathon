import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase, mock

import httpx
import pyzipper

from round_journal import Journal, submission_owner
from round_rehearsal import manual_assessment, rehearse_round
from test_offline_replay import make_invoice
from tournament_api import TournamentAPI


class VirtualClock:
    def __init__(self, release, age):
        self.release = release
        self.age = age
        self.started = time.monotonic()

    def monotonic(self):
        return time.monotonic() + self.age

    def now(self):
        return self.release + timedelta(seconds=self.monotonic() - self.started)

    async def sleep(self, seconds):
        self.age += seconds
        await asyncio.sleep(0)


class RoundRehearsalTests(IsolatedAsyncioTestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.release = datetime(2026, 11, 21, 13, tzinfo=timezone.utc)
        self.clock = VirtualClock(self.release, -0.5)
        self.archive = self.root / "case_001.zip"
        invoice = self.root / "test-invoice.pdf"
        make_invoice(invoice, [[("1", "One", "2,5", "hrs", ""), ("2", "Two", "1", "pcs", "")]])
        with pyzipper.AESZipFile(self.archive, "w", encryption=pyzipper.WZ_AES) as encrypted:
            encrypted.setpassword(b"fake-case-pass")
            encrypted.write(invoice, "invoices.pdf")
            encrypted.writestr("policy.txt", "Synthetic test policy")
            encrypted.writestr("description.txt", "Synthetic test description")
        self.state = self.root / "state"
        self.requests = []
        self.puts = []
        self.bad_ack = None
        self.stalled_put = None

    async def fake_server(self, request):
        self.assertEqual(request.headers["X-API-Key"], "fake-team-key")
        sequence = (request.method, request.url.path)
        age = (self.clock.now() - self.release).total_seconds()
        self.requests.append(sequence)
        if sequence == ("GET", "/api/games/list"):
            return httpx.Response(200, json=[{"id": 1, "start_time": self.release.isoformat()}])
        if sequence == ("GET", "/api/games/1/key"):
            self.assertGreaterEqual(age, 0)
            return httpx.Response(200, json={"decryption_key": "fake-case-pass"})
        self.assertEqual(sequence, ("PUT", "/api/games/1/submissions"))
        payload = json.loads(request.content)
        self.assertEqual([line["index"] for line in payload], [1, 2])
        for line in payload:
            self.assertEqual(set(line), {"index", "charge_price", "acceptance_limit"})
            self.assertTrue(0 <= line["charge_price"] <= line["acceptance_limit"])
        self.puts.append((age, payload))
        if self.stalled_put == len(self.puts):
            await asyncio.sleep(30)
        ack = [{
            "game_id": 1, "team_id": 7, "line_item_index": line["index"],
            "charge_price": line["charge_price"], "acceptance_limit": line["acceptance_limit"],
            "submitted_at": self.clock.now().isoformat(),
        } for line in payload]
        if self.bad_ack == "missing":
            ack.pop()
        if self.bad_ack == "duplicate":
            ack[1] = ack[0]
        if self.bad_ack == "price":
            ack[0]["charge_price"] += 1
        if self.bad_ack == "game":
            ack[0]["game_id"] += 1
        if self.bad_ack == "timestamp":
            ack[0]["submitted_at"] = (self.release + timedelta(seconds=60)).isoformat()
        if self.bad_ack == "team_on_overwrite" and len(self.puts) > 1:
            for line in ack:
                line["team_id"] = 8
        return httpx.Response(200, json=list(reversed(ack)))

    async def run_round(self, assessment=None):
        transport = httpx.MockTransport(self.fake_server)
        async with httpx.AsyncClient(transport=transport, headers={"X-API-Key": "fake-team-key"}) as client:
            api = TournamentAPI(client)
            starts = await api.schedule()
            return await rehearse_round(
                api, 1, starts[1], self.archive, self.state, assessment=assessment, clock=self.clock,
            )

    async def refined(self, manifest):
        return {"game_id": 1, "items": [
            {"row_index": index, "coverage": "yes", "relevance": "yes", "eligible_samples": 100,
             "evidence": "Synthetic estimate", "unit_price_band_net_cents": [3000, 3500, 4000]}
            for index, _ in enumerate(manifest["items"])
        ]}

    async def test_release_wire_ack_overwrite_and_restart(self):
        self.assertEqual(await self.run_round(self.refined), "overwrite_acknowledged")
        self.assertLess(self.puts[0][0], 35)
        self.assertLess(self.puts[1][0], 50)
        self.assertNotEqual(self.puts[0][1], self.puts[1][1])
        self.assertEqual(await self.run_round(self.refined), "prior_write")
        self.assertEqual(len(self.puts), 2)
        self.assertEqual(sum(method == "GET" and path.endswith("/key") for method, path in self.requests), 1)
        history = Journal(self.state, self.clock).history(1)
        self.assertEqual([event["stage"] for event in history if event["state"] == "acknowledged"],
                         ["baseline", "overwrite"])
        self.assertFalse(any("payload" in event or "response" in event for event in history))

    async def test_local_assessment_file_is_applied(self):
        path = self.root / "manual.json"
        path.write_text(json.dumps(await self.refined({"items": [{}, {}]})))
        self.assertEqual(await self.run_round(manual_assessment(path)), "overwrite_acknowledged")
        self.assertEqual(len(self.puts), 2)

    async def test_delayed_wake_uses_release_budget(self):
        self.clock.age = 35.1
        self.assertEqual(await self.run_round(), "baseline_unavailable")
        self.assertEqual(self.requests, [("GET", "/api/games/list")])

    async def test_missing_invalid_and_stalled_assessment_keep_baseline(self):
        async def invalid(_manifest):
            return {"game_id": 1, "items": []}

        async def stalled(_manifest):
            await asyncio.sleep(30)

        for name, assessment in (("absent", None), ("invalid", invalid), ("stalled", stalled)):
            with self.subTest(assessment=name), mock.patch("round_rehearsal.OVERWRITE_BEFORE", .12):
                self.state = self.root / name
                self.clock = VirtualClock(self.release, 0)
                self.puts.clear()
                self.assertEqual(await self.run_round(assessment), "baseline_acknowledged")
                self.assertEqual(len(self.puts), 1)
                if name == "stalled":
                    self.assertEqual(Journal(self.state, self.clock).history(1)[-1]["reason"], "TimeoutError")

    async def test_late_refinement_cannot_start_overwrite(self):
        async def late(manifest):
            self.clock.age = 50
            return await self.refined(manifest)

        self.assertEqual(await self.run_round(late), "baseline_acknowledged")
        self.assertEqual(len(self.puts), 1)

    async def test_ambiguous_ack_and_restart_do_not_retry(self):
        for error in ("missing", "duplicate", "price", "game", "timestamp"):
            with self.subTest(ack=error):
                self.state = self.root / error
                self.bad_ack = error
                self.puts.clear()
                self.assertEqual(await self.run_round(self.refined), "baseline_unconfirmed")
                self.assertEqual(await self.run_round(self.refined), "prior_write")
                self.assertEqual(len(self.puts), 1)

    async def test_overwrite_rejects_wrong_team_and_stops_at_hard_close(self):
        self.bad_ack = "team_on_overwrite"
        self.assertEqual(await self.run_round(self.refined), "overwrite_unconfirmed")
        self.assertEqual(len(self.puts), 2)
        self.state = self.root / "timeout"
        self.stalled_put = 2
        self.puts.clear()
        self.clock = VirtualClock(self.release, 0)
        with mock.patch("round_rehearsal.HARD_CLOSE", .2), mock.patch("round_rehearsal.OVERWRITE_BEFORE", .15):
            self.assertEqual(await self.run_round(self.refined), "overwrite_unconfirmed")
        self.assertEqual(len(self.puts), 2)
        self.assertEqual(Journal(self.state, self.clock).history(1)[-1]["reason"], "TimeoutError")
        self.assertEqual(await self.run_round(self.refined), "prior_write")

    async def test_active_owner_and_interrupted_intent_prevent_duplicate(self):
        with submission_owner(self.state):
            with self.assertRaisesRegex(ValueError, "another local"):
                await self.run_round()
            Journal(self.state, self.clock).record(1, "attempted", stage="baseline")
        self.assertEqual(await self.run_round(), "prior_write")
        self.assertEqual(self.puts, [])
