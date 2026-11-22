"""Read and validate the organizer's position-numbered invoice grid."""

import re
from decimal import Decimal
from itertools import groupby

import pymupdf


HEADER = ("POS.", "DESCRIPTION", "AMOUNT", "UNIT", "TOTAL")
DEFAULT_VAT_RATE = Decimal("0.19")
HOURLY_UNITS = {"h", "hr", "hrs", "hour", "hours", "std"}
NET_HOURLY_BAND = [5_000, 7_500, 10_000]
NET_OTHER_UNIT_BAND = [1_500, 4_000, 8_000]


def checked_vat(value):
    if not value.is_finite() or not 0 <= value <= 1:
        raise ValueError("VAT rate must be a fraction from 0 to 1")
    return value


def _lines(words):
    """Group words on a visual line, regardless of PDF text stream order."""
    lines = []
    for word in sorted(words, key=lambda word: (word[1], word[0])):
        if not lines or word[1] - lines[-1][0][1] > 2:
            lines.append([])
        lines[-1].append(word)
    return [sorted(line, key=lambda word: word[0]) for line in lines]


def _grid(page, header):
    segments = []
    for drawing in page.get_drawings():
        for operation, *points in drawing["items"]:
            if operation == "l":
                start, end = points
                if abs(start.y - end.y) < 0.1:
                    left, right = sorted((start.x, end.x))
                    segments.append((round(start.y, 1), round(left, 1), round(right, 1)))
    rules = []
    for y, group in groupby(sorted(set(segments)), key=lambda segment: segment[0]):
        if y <= max(word[3] for word in header):
            continue
        cells = [(left, right) for _, left, right in group]
        # The sponsor draws the horizontal rule in one segment per cell.
        if len(cells) != len(header):
            continue
        if all(left <= word[0] < word[2] <= right for (left, right), word in zip(cells, header)):
            rules.append((y, cells))
    if len(rules) < 2 or any(cells != rules[0][1] for _, cells in rules):
        raise ValueError("invoice row rules are missing or inconsistent")
    columns = rules[0][1]
    if any(left != previous_right for (_, previous_right), (left, _) in zip(columns, columns[1:])):
        raise ValueError("invoice column rules do not meet")
    return [y for y, _ in rules], columns


def invoice_items(path, *, vat_rate=DEFAULT_VAT_RATE):
    """Parse every row in page order, or fail if any page cannot be validated."""
    rate = str(checked_vat(vat_rate))
    items = []
    with pymupdf.open(path) as pdf:
        for page in pdf:
            words = page.get_text("words")
            headers = [line for line in _lines(words) if tuple(word[4].upper() for word in line) == HEADER]
            if len(headers) != 1:
                raise ValueError(f"invoice page {page.number + 1} has no unique supported table header")
            rules, columns = _grid(page, headers[0])
            # Check for a position row that fell outside the ruled table (e.g. a missing final rule).
            position_x = headers[0][0][0]
            for word in words:
                middle_y = (word[1] + word[3]) / 2
                if abs(word[0] - position_x) <= 3 and word[4].isascii() and word[4].isdecimal():
                    if middle_y > headers[0][0][3] and not rules[0] < middle_y < rules[-1]:
                        raise ValueError("invoice position appears outside the ruled rows")
            for top, bottom in zip(rules, rules[1:]):
                row_words = [word for word in words if top <= (word[1] + word[3]) / 2 < bottom]
                fields = [
                    " ".join(word[4] for line in _lines(
                        word for word in row_words if left <= (word[0] + word[2]) / 2 < right
                    ) for word in line)
                    for left, right in columns
                ]
                position, description, amount, unit, total = fields
                if not re.fullmatch(r"[0-9]+", position) or int(position) != len(items) + 1:
                    raise ValueError("invoice positions must be consecutive and ordered from 1")
                if not re.fullmatch(r"[0-9]+(?:[.,][0-9]+)?", amount):
                    raise ValueError("invoice quantity must be a plain decimal")
                quantity = Decimal(amount.replace(",", "."))
                if quantity <= 0 or not description or not unit or total:
                    raise ValueError("expected a positive quantity, description, unit and blank total")
                items.append({
                    "item_id": int(position),
                    "description": description,
                    "quantity": str(quantity),
                    "unit": unit,
                    "vat_rate": rate,
                })
    if not items:
        raise ValueError("invoice contains no positions")
    return items


def invoice_manifest(path, game_id, *, vat_rate=DEFAULT_VAT_RATE):
    items = invoice_items(path, vat_rate=vat_rate)
    for item in items:
        hourly = item["unit"].casefold().rstrip(".") in HOURLY_UNITS
        item.update(
            coverage="uncertain",
            relevance="uncertain",
            eligible_samples=85,
            unit_price_band_net_cents=NET_HOURLY_BAND.copy() if hourly else NET_OTHER_UNIT_BAND.copy(),
            evidence="Fixed unit-based fallback. Coverage, relevance and market prices are unverified.",
        )
    return {
        "game_id": game_id,
        "expected_item_ids": [item["item_id"] for item in items],
        "items": items,
    }
