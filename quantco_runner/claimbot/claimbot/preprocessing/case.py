"""Turn a decrypted case folder into a Case: texts, invoice lines and photo paths."""

from __future__ import annotations

import logging
from pathlib import Path

from claimbot.models import Case
from claimbot.preprocessing.invoice import extract_pdf_text, parse_line_items

log = logging.getLogger("claimbot.case")

PHOTO_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def _read_text(path: Path) -> str:
    if not path.exists():
        log.warning("missing %s", path.name)
        return ""
    raw = path.read_bytes()
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def load_case(game_id: int, case_dir: Path) -> Case:
    invoice_pdf = case_dir / "invoices.pdf"
    invoice_text = ""
    if not invoice_pdf.exists():
        log.error("invoices.pdf missing in %s", case_dir)
    else:
        try:
            invoice_text = extract_pdf_text(invoice_pdf)
        except Exception as exc:  # keep policy/description usable even if the PDF is broken
            log.error("could not read invoices.pdf: %s", exc)
    lines = parse_line_items(invoice_text)
    # Photo names vary (photo.jpg, photo1.png, ...), so match by suffix.
    photos = sorted(p for p in case_dir.iterdir() if p.suffix.lower() in PHOTO_SUFFIXES)
    return Case(
        game_id=game_id,
        directory=case_dir,
        policy=_read_text(case_dir / "policy.txt"),
        description=_read_text(case_dir / "description.txt"),
        invoice_text=invoice_text,
        lines=lines,
        photos=photos,
    )
