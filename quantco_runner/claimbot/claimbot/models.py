"""Plain data types shared across the bot."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple


@dataclass
class LineItem:
    """One invoice line. Prices are never on the invoice; we only know what and how much."""

    index: int
    description: str
    quantity: float | None = None
    unit: str | None = None
    raw: str = ""


@dataclass
class Case:
    game_id: int
    directory: Path
    policy: str
    description: str
    invoice_text: str
    lines: list[LineItem]
    photos: list[Path] = field(default_factory=list)


class LinePrice(NamedTuple):
    """What a strategy returns per invoice line: (index, a, b).

    a = charge price (what we bill other teams), b = acceptance limit (the most we pay).
    Both are GROSS line totals in EUR (quantity x unit price incl. VAT).
    A plain tuple (index, a, b) works too; see as_line_price.
    """

    index: int
    a: float
    b: float

    def to_api(self) -> dict:
        return {"index": int(self.index), "charge_price": _money(self.a),
                "acceptance_limit": _money(self.b)}


def as_line_price(item) -> LinePrice:
    """Accept LinePrice, a (index, a, b) tuple/list, or a dict with index/a/b keys."""
    if isinstance(item, dict):
        return LinePrice(int(item["index"]), item["a"], item["b"])
    index, a, b = item
    return LinePrice(int(index), a, b)


def _money(value: float) -> float:
    """The API rejects negative or non-finite values (422); clamp instead of failing."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(v) or v < 0:
        return 0.0
    return round(v, 2)
