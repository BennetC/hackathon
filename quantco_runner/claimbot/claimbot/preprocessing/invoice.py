"""Invoice PDF text extraction and line-item parsing.

The case invoices (games 1-12) share one layout, as extracted by pypdf:

    ... header: INVOICE NO., DATE "4 Apr 2026", FROM "3 Landfill Loop" ...   <- not items
    ITEMS
    POS. DESCRIPTION AMOUNT UNIT TOTAL                                       <- table header
    1 Disposal of shed roof timber removed from the                          <- item 1 starts
    damaged garden building                                                  <- wrapped text
    1 pcs                                                                    <- its quantity
    2 Hole drilling 1 pcs                                                    <- one-row item
    INVOICE / Created on 21 Aug 2026 Page 1 / 1                              <- table end

A case can hold several invoices (one per page) whose numbering continues (5, 6, ...).
parse_line_items reads only the item tables. If no table header is found (another
layout), it falls back to the older row heuristic.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from pathlib import Path

from pypdf import PdfReader

from claimbot.models import LineItem

log = logging.getLogger("claimbot.invoice")

UNITS = (
    r"flat\s+rate|lump\s?sum|pcs\.?|pc\.?|pieces?|units?|hrs?\.?|hours?|sqm|sq\.?\s?m|days?|"
    r"nights?|visits?|trips?|jobs?|items?|sets?|flat|ls|kWh|MWh|Wh|"
    r"m²|m2|m³|m3|qm|lfm|lfdm|m|cm|mm|Std\.?|Stunden?|h|Stk\.?|Stück|St\.?|"
    r"psch\.?|pausch\.?|pauschal|Pauschale|kg|t|l|Liter|Satz|Tag(?:e)?|km|Set|x|Einh\.?"
)
NUMBER = r"\d{1,3}(?:[.,\s]\d{3})*(?:[.,]\d+)?|\d+(?:[.,]\d+)?"

# "3  Trocknungsgerät aufstellen   4,5  Tage"  /  "3. Leckortung 1 psch"
LINE_RE = re.compile(
    rf"^\s*(?:Pos\.?\s*)?(?P<idx>\d{{1,3}})[.)]?\s+(?P<desc>.+?)\s+"
    rf"(?P<qty>{NUMBER})\s*(?P<unit>{UNITS})\s*$",
    re.IGNORECASE,
)
# Quantity before description: "3  4,5 Std. Trocknung"
LINE_QTY_FIRST_RE = re.compile(
    rf"^\s*(?:Pos\.?\s*)?(?P<idx>\d{{1,3}})[.)]?\s+(?P<qty>{NUMBER})\s*"
    rf"(?P<unit>{UNITS})\s+(?P<desc>.+?)\s*$",
    re.IGNORECASE,
)
INDEX_ONLY_RE = re.compile(r"^\s*(?:Pos\.?\s*)?(?P<idx>\d{1,3})[.)]?\s+(?P<desc>[A-Za-zÄÖÜäöüß].{2,})$")


TABLE_HEADER_RE = re.compile(r"^\s*(POS\.?|Pos\.?|Position)\s+(DESCRIPTION|Beschreibung|Bezeichnung)\b",
                             re.IGNORECASE)
TABLE_END_RE = re.compile(r"^\s*(INVOICE\b|Created on\b|Page \d|Sub-?total\b|Total\b|"
                          r"VAT\b|Net\b|Summe\b|Zwischensumme\b|Gesamt|MwSt)", re.IGNORECASE)
ITEM_START_RE = re.compile(r"^\s*(?P<idx>\d{1,3})[.)]?\s+(?P<rest>\S.*)$")
# A row that is only a quantity + unit, e.g. "3 pcs", "1 flat rate", "2,5 hours".
QTY_ROW_RE = re.compile(rf"^\s*(?P<qty>{NUMBER})\s+(?P<unit>[^\d\s][^\d]{{0,24}}?)\s*$")
# Quantity + known unit at the end of a description row: "... (frame and brakes) 2 pcs".
TRAILING_QTY_RE = re.compile(rf"^(?P<desc>.*?\S)\s+(?P<qty>{NUMBER})\s+(?P<unit>{UNITS})\s*$",
                             re.IGNORECASE)


def _split_trailing_qty(text: str) -> tuple[str, float | None, str | None]:
    m = TRAILING_QTY_RE.match(text)
    if not m:
        return text, None, None
    return m.group("desc"), parse_number(m.group("qty")), m.group("unit")


def parse_item_tables(text: str) -> list[LineItem] | None:
    """Parse the ITEMS tables. Returns None if the text has no table header."""
    rows = [r.strip() for r in text.splitlines()]
    if not any(TABLE_HEADER_RE.match(r) for r in rows):
        return None
    items: list[LineItem] = []
    in_table = False
    cur: LineItem | None = None
    for row in rows:
        if not row:
            continue
        if TABLE_HEADER_RE.match(row):
            in_table, cur = True, None
            continue
        if not in_table:
            continue
        if TABLE_END_RE.match(row):
            in_table, cur = False, None
            continue
        # 1) quantity row for the current item ("3 pcs") - checked before "new item",
        #    because "3 pcs" also looks like "item 3".
        if cur is not None and cur.quantity is None:
            q = QTY_ROW_RE.match(row)
            if q:
                cur.quantity, cur.unit = parse_number(q.group("qty")), q.group("unit").strip()
                cur.raw += "\n" + row
                continue
        # 2) the next item in sequence
        m = ITEM_START_RE.match(row)
        expected = items[-1].index + 1 if items else 1
        if m and int(m.group("idx")) == expected:
            desc, qty, unit = _split_trailing_qty(m.group("rest"))
            cur = LineItem(index=expected, description=desc, quantity=qty, unit=unit, raw=row)
            items.append(cur)
            continue
        # 3) wrapped description of the current item (may end with its quantity)
        if cur is not None and cur.quantity is None:
            desc, qty, unit = _split_trailing_qty(row)
            cur.description = f"{cur.description} {desc}".strip()
            cur.quantity, cur.unit = qty, unit
            cur.raw += "\n" + row
            continue
        log.debug("invoice row ignored: %r", row)
    return items


def extract_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception as exc:  # malformed page: keep going
            log.warning("text extraction failed on a page of %s: %s", path.name, exc)
    text = "\n".join(pages)
    if not text.strip():
        log.warning("%s has no extractable text (scanned PDF? needs OCR)", path.name)
    return text


def extract_pdf_text_layout(path: Path) -> str:
    """Extract PDF text with `pdftotext -layout` (Daniil's exact extractor), falling back to pypdf."""
    pdftotext = shutil.which("pdftotext")
    if pdftotext:
        try:
            proc = subprocess.run(
                [pdftotext, "-layout", str(path), "-"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                return proc.stdout
        except Exception as exc:
            log.warning("pdftotext -layout failed on %s: %s (falling back to pypdf)", path.name, exc)
    return extract_pdf_text(path)


def parse_number(value: str) -> float | None:
    v = value.strip().replace(" ", "")
    if "," in v and "." in v:
        if v.rfind(".") > v.rfind(","):
            # English thousands comma + decimal dot: 2,412.1
            v = v.replace(",", "")
        else:
            # German thousands dot + decimal comma: 1.234,5
            v = v.replace(".", "").replace(",", ".")
    elif "," in v:
        # Comma-only: German decimal (4,5) unless thousands group (2,412)
        parts = v.split(",")
        if len(parts) > 1 and all(len(p) == 3 for p in parts[1:]):
            v = "".join(parts)
        else:
            v = v.replace(",", ".")
    try:
        return float(v)
    except ValueError:
        return None


def parse_line_items(text: str) -> list[LineItem]:
    """Invoice lines in order with unique indexes: item tables first, row heuristic as fallback."""
    table_items = parse_item_tables(text)
    if table_items:
        missing_qty = [li.index for li in table_items if li.quantity is None]
        if missing_qty:
            log.warning("invoice lines without a quantity: %s", missing_qty)
        log.info("parsed %d invoice line(s) from item tables: %s", len(table_items),
                 [(li.index, li.quantity, li.unit) for li in table_items])
        return table_items
    log.warning("no item table header found; using the row heuristic")
    return _parse_rows_heuristic(text)


def _parse_rows_heuristic(text: str) -> list[LineItem]:
    """Older fallback for layouts without a recognised table header."""
    items: dict[int, LineItem] = {}
    loose: dict[int, LineItem] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = LINE_RE.match(line) or LINE_QTY_FIRST_RE.match(line)
        if m:
            idx = int(m.group("idx"))
            if idx not in items:
                items[idx] = LineItem(
                    index=idx,
                    description=m.group("desc").strip(),
                    quantity=parse_number(m.group("qty")),
                    unit=m.group("unit"),
                    raw=line,
                )
            continue
        m = INDEX_ONLY_RE.match(line)
        if m:
            idx = int(m.group("idx"))
            loose.setdefault(idx, LineItem(index=idx, description=m.group("desc"), raw=line))

    # Index-only matches count only as a consecutive run 1..n (avoids dates, zip codes).
    # Merge with full matches so a wrapped description never drops a line.
    result = dict(items)
    i = 1
    while i in loose or i in items:
        if i not in result:
            result[i] = loose[i]
            log.warning("line %d has no quantity/unit on its row (wrapped?); kept index-only", i)
        i += 1
    lines = [result[k] for k in sorted(result)]
    log.info("parsed %d invoice line(s): indexes %s", len(lines), [li.index for li in lines])
    return lines
