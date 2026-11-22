from claimbot.preprocessing import archive
from claimbot.preprocessing.invoice import parse_line_items, parse_number
from tests.conftest import make_case_zip


def test_parse_number_german():
    assert parse_number("1.234,5") == 1234.5
    assert parse_number("4,5") == 4.5
    assert parse_number("12") == 12.0
    assert parse_number("2,412.1") == 2412.1
    assert parse_number("2,412") == 2412.0

def test_parse_line_items():
    text = """Rechnung Nr. 2026-117
    Pos. Beschreibung Menge Einheit
    1 Leckortung mit Thermografie 1 psch
    2 Trocknungsgerät aufstellen und betreiben 14 Tage
    3 Fliesen entfernen und entsorgen 6,5 m²
    80331 München
    """
    lines = parse_line_items(text)
    assert [li.index for li in lines] == [1, 2, 3]
    assert lines[2].quantity == 6.5 and lines[2].unit == "m²"

def test_parse_real_english_invoice_with_wrapped_line():
    text = """POS. DESCRIPTION AMOUNT UNIT TOTAL
1 Laptop screen crack repair 1 pcs
2 Lower-right corner and housing repair 1 pcs
3 Polish of pre-existing lid scuff (surface only, does not
affect operation)
1 pcs
4 Diagnostic inspection 1 pcs
DUE
15 Apr 2026"""
    lines = parse_line_items(text)
    assert [li.index for li in lines] == [1, 2, 3, 4]
    assert lines[0].unit == "pcs" and lines[0].quantity == 1

def test_decrypt_and_find_by_key(tmp_path):
    make_case_zip(tmp_path / "case_001.zip", "k1")
    make_case_zip(tmp_path / "case_002.zip", "k2", {"../../evil.txt": "x"})
    assert archive.key_opens(tmp_path / "case_001.zip", "k1")
    assert not archive.key_opens(tmp_path / "case_001.zip", "wrong")
    assert archive.find_zip_for_key(tmp_path, "k2") == tmp_path / "case_002.zip"
    out = tmp_path / "out"
    names = {p.name for p in archive.decrypt(tmp_path / "case_002.zip", "k2", out)}
    assert "evil.txt" in names and not (tmp_path.parent / "evil.txt").exists()
    assert all(p.parent == out for p in out.iterdir())


HEADER = """Invoice
INVOICE NO.
2026-0215
DATE
4 Apr 2026
DUE
18 Apr 2026
FROM
Trash to Treasure Recycling Ltd
3 Landfill Loop
34117 Binbrook
ITEMS
POS. DESCRIPTION AMOUNT UNIT TOTAL
"""
FOOTER = "INVOICE\nCreated on 21 Aug 2026 Page 1 / 1\n"


def test_table_ignores_header_dates_and_addresses():
    text = HEADER + "1 Disposal of shed roof timber removed from the\ndamaged garden building\n1 pcs\n" \
                    "2 Hole drilling 1 pcs\n" + FOOTER
    items = parse_line_items(text)
    assert [(li.index, li.quantity, li.unit) for li in items] == [(1, 1.0, "pcs"), (2, 1.0, "pcs")]
    assert items[0].description == "Disposal of shed roof timber removed from the damaged garden building"


def test_quantity_row_is_not_mistaken_for_the_next_item():
    # game 4: "3 pcs" is line 1's quantity, not line 3; "flat rate" is a unit
    text = HEADER + ("1 Recover stolen bicycle from secured location, incl.\n"
                     "locksmith call-out and cutting of seized lock\n3 pcs\n"
                     "2 Repair theft damage to bicycle (frame and brakes) 2 pcs\n"
                     "3 Labour and sundries 1 flat rate\n") + FOOTER
    items = parse_line_items(text)
    assert [(li.index, li.quantity, li.unit) for li in items] == [
        (1, 3.0, "pcs"), (2, 2.0, "pcs"), (3, 1.0, "flat rate")]
    assert items[2].description == "Labour and sundries"


def test_quantity_row_equal_to_next_index():
    # line 1's quantity "2 pcs" must not start line 2
    text = HEADER + "1 Long description that wraps\nonto a second row\n2 pcs\n2 Second item 1 pcs\n" + FOOTER
    items = parse_line_items(text)
    assert [(li.index, li.quantity) for li in items] == [(1, 2.0), (2, 1.0)]


def test_several_invoices_continue_numbering():
    # game 11: two invoices (pages), numbering continues 1-2 then 3
    text = (HEADER + "1 Glass pane 1 pcs\n2 Hole drilling 1 pcs\n" + FOOTER +
            HEADER + "3 Repair of dented side table (knocked over\nin the same fall)\n1 flat rate\n" + FOOTER)
    items = parse_line_items(text)
    assert [li.index for li in items] == [1, 2, 3]
    assert items[2].description == "Repair of dented side table (knocked over in the same fall)"
