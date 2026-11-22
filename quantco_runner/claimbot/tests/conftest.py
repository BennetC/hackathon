"""Shared test helpers: synthetic encrypted cases, a fake QuantCo API, test strategies."""

import time
from pathlib import Path

import pytest
import pyzipper

from claimbot.api import ApiError
from claimbot.config import Settings
from claimbot.preprocessing import case


def make_case_zip(path: Path, key: str, extra: dict | None = None) -> None:
    files = {"policy.txt": "Leitungswasser versichert.", "description.txt": "Rohrbruch im Bad.",
             "invoices.pdf": "%PDF-fake", "photo1.jpg": "jpg"}
    files.update(extra or {})
    with pyzipper.AESZipFile(path, "w", compression=pyzipper.ZIP_DEFLATED,
                             encryption=pyzipper.WZ_AES) as zf:
        zf.setpassword(key.encode())
        for name, content in files.items():
            zf.writestr(name, content)

class FakeApi:
    def __init__(self, key="secret", not_started_calls=0):
        self.key = key
        self.not_started_calls = not_started_calls
        self.submissions = []

    def get_key(self, game_id):
        if self.not_started_calls > 0:
            self.not_started_calls -= 1
            raise ApiError(403, "Game has not started yet", "get key")
        return self.key

    def submit(self, game_id, items):
        self.submissions.append(items)
        return [{"game_id": game_id, "team_id": 1, "line_item_index": i["index"],
                 "charge_price": i["charge_price"], "acceptance_limit": i["acceptance_limit"]}
                for i in items]

INVOICE_TEXT = "1 Leckortung 1 psch\n2 Trocknung 10 Tage\n"

@pytest.fixture
def env(tmp_path, monkeypatch):
    cases = tmp_path / "cases"
    cases.mkdir()
    make_case_zip(cases / "case_007.zip", "secret")
    monkeypatch.setattr(case, "extract_pdf_text", lambda p: INVOICE_TEXT)
    settings = Settings(api_key="x", cases_dir=cases, runs_dir=tmp_path / "runs",
                        fallback_charge=0, fallback_limit=200, key_retry_s=5)
    return settings

class SlowStrategy:
    name = "slow"

    def __init__(self, settings=None):
        pass

    def price(self, case, deadline_ts):
        time.sleep(5)
        return []

class GoodStrategy:
    name = "good"

    def __init__(self, settings=None):
        pass

    def price(self, case, deadline_ts):
        return [(li.index, 100.0, 120.0) for li in case.lines]   # (index, a, b)
