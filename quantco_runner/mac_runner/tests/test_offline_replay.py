from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

import json
import pymupdf

from invoice_rows import HEADER, invoice_items, invoice_manifest
from pricing import price_payload
from replay_case import synthetic_scenario
from simulate_local import replay, wire_items


def make_invoice(path, pages, *, omit_last_rule=False):
    bounds = [40, 80, 330, 410, 470, 550]
    with pymupdf.open() as pdf:
        for rows in pages:
            page = pdf.new_page()
            for x, label in zip(bounds, HEADER):
                page.insert_text((x + 6, 90), label)
            for offset, row in enumerate(rows):
                top = 100 + offset * 40
                for left, right in zip(bounds, bounds[1:]):
                    page.draw_line((left, top), (right, top))
                for x, cell in zip(bounds, row):
                    page.insert_text((x + 6, top + 13), cell)
                page.insert_text((86, top + 27), "description continuation")
            if not omit_last_rule:
                bottom = 100 + len(rows) * 40
                for left, right in zip(bounds, bounds[1:]):
                    page.draw_line((left, bottom), (right, bottom))
            page.insert_text((510, 800), "Page footer")
        pdf.save(path)


class OfflineReplayTests(TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.invoice = Path(temporary.name) / "invoice.pdf"

    def test_multipage_wrapped_text_and_fractional_quantity(self):
        make_invoice(self.invoice, [
            [("1", "Repair work", "2,5", "hrs", ""), ("2", "Spare part", "1", "pcs", "")],
            [("3", "Test cycle", "2", "pcs", "")],
        ])
        manifest = invoice_manifest(self.invoice, 0)
        self.assertEqual(manifest["expected_item_ids"], [1, 2, 3])
        self.assertEqual(manifest["items"][0]["description"], "Repair work description continuation")
        self.assertEqual(manifest["items"][0]["quantity"], "2.5")
        self.assertEqual(manifest["items"][0]["vat_rate"], "0.19")
        prices = price_payload(manifest)
        wire = wire_items(prices, expected_ids=manifest["expected_item_ids"])
        self.assertEqual([line["index"] for line in wire], [1, 2, 3])
        self.assertTrue(all(0 < line["charge_price"] < line["acceptance_limit"] for line in wire))
        self.assertEqual(set(replay(prices, synthetic_scenario(prices))), {"earned_cents", "paid_cents", "net_cents"})

    def test_gap_duplicate_or_bad_quantity_fails_closed(self):
        for position, quantity in (("3", "1"), ("1", "1"), ("2", "0"), ("2", "-1")):
            with self.subTest(position=position, quantity=quantity):
                make_invoice(self.invoice, [[
                    ("1", "Repair work", "1", "hrs", ""), (position, "Part", quantity, "pcs", ""),
                ]])
                with self.assertRaises(ValueError):
                    invoice_items(self.invoice)
                self.invoice.unlink()

    def test_refuses_truncated_table_and_incorrect_wire_order(self):
        make_invoice(self.invoice, [[
            ("1", "Repair work", "1", "hrs", ""), ("2", "Part", "2", "pcs", ""),
        ]], omit_last_rule=True)
        with self.assertRaisesRegex(ValueError, "outside the ruled rows"):
            invoice_items(self.invoice)
        fixture = Path(__file__).resolve().parents[1] / "examples" / "game1_valuation.json"
        priced = price_payload(json.loads(fixture.read_text()))
        self.assertEqual(wire_items(priced)[0], {"index": 1, "charge_price": 113.05, "acceptance_limit": 119.0})
        with self.assertRaisesRegex(ValueError, "every invoice position in order"):
            wire_items(priced, expected_ids=[2, 1])
