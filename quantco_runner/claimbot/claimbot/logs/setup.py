"""Logging with UTC millisecond timestamps, to stderr and per-run log files."""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

FORMAT = "%(asctime)s.%(msecs)03dZ %(levelname)-5s %(name)s | %(message)s"
DATEFMT = "%Y-%m-%dT%H:%M:%S"


def _formatter() -> logging.Formatter:
    fmt = logging.Formatter(FORMAT, DATEFMT)
    fmt.converter = time.gmtime
    return fmt


def setup_logging(verbose: bool = False) -> None:
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    for h in list(root.handlers):
        root.removeHandler(h)
    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG if verbose else logging.INFO)
    console.setFormatter(_formatter())
    root.addHandler(console)
    # Third-party chatter stays at WARNING even in verbose mode.
    for noisy in ("urllib3", "pypdf", "anthropic", "httpx", "httpx2", "httpcore", "httpcore2", "PIL"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


@contextmanager
def run_log_file(path: Path) -> Iterator[None]:
    """Capture all DEBUG+ records into `path` for the duration of a run."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(_formatter())
    root = logging.getLogger()
    previous_level = root.level
    root.setLevel(logging.DEBUG)  # console handlers keep their own, higher level
    root.addHandler(handler)
    try:
        yield
    finally:
        root.removeHandler(handler)
        root.setLevel(previous_level)
        handler.close()
