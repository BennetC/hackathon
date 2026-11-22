"""Find and decrypt case archives.

Case zips are WinZip-AES encrypted, which the stdlib cannot read, so we use pyzipper.
Archive contents are untrusted: members are flattened to their base name on extraction.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pyzipper

log = logging.getLogger("claimbot.archive")

MAX_MEMBER_BYTES = 200 * 1024 * 1024


def expected_zip(cases_dir: Path, template: str, game_id: int) -> Path:
    return cases_dir / template.format(game_id=game_id)


def key_opens(zip_path: Path, key: str) -> bool:
    """True if `key` decrypts the smallest member of `zip_path`."""
    try:
        with pyzipper.AESZipFile(zip_path) as zf:
            infos = [i for i in zf.infolist() if not i.is_dir()]
            if not infos:
                return False
            smallest = min(infos, key=lambda i: i.file_size)
            zf.read(smallest, pwd=key.encode())
            return True
    except Exception:  # wrong password raises RuntimeError / BadZipFile
        return False


def find_zip_for_key(cases_dir: Path, key: str, skip: Path | None = None) -> Path | None:
    """Fallback when game N is not case_NNN.zip: try the key on every local archive."""
    for path in sorted(cases_dir.glob("*.zip")):
        if skip is not None and path.resolve() == skip.resolve():
            continue
        if key_opens(path, key):
            return path
    return None


def decrypt(zip_path: Path, key: str, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    with pyzipper.AESZipFile(zip_path) as zf:
        zf.setpassword(key.encode())
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = Path(info.filename.replace("\\", "/")).name
            if not name or name.startswith("."):
                log.warning("skipping odd archive member %r", info.filename)
                continue
            if info.file_size > MAX_MEMBER_BYTES:
                log.warning("skipping oversized member %r (%d bytes)", name, info.file_size)
                continue
            target = out_dir / name
            target.write_bytes(zf.read(info))
            written.append(target)
    return written
