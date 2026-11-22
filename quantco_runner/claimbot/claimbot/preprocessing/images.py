"""Photo preparation for LLM backends.

- `encode_image`: downscales to JPEG (max 1280 px) for standard API/CLI backends.
- `prepare_daniil_image` & `stage_daniil_images`: exact mirror of Daniil's image
  handling (Warroom @artifact:daniil-live-opus-spec §5):
    * Every image file (.png .jpg .jpeg .webp .gif) sorted by path, no count limit.
    * Raw bytes preserved verbatim when base64 size <= 5 MB.
    * Only when base64 exceeds 5 MB: convert to RGB with PIL, thumbnail((1568, 1568)),
      and save as JPEG quality 88.
"""

from __future__ import annotations

import base64
import io
from pathlib import Path

MAX_SIDE = 1280
JPEG_QUALITY = 80

DANIIL_MAX_B64_BYTES = 5 * 1024 * 1024
DANIIL_MAX_SIDE = 1568
DANIIL_JPEG_QUALITY = 88

MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


def encode_image(path: Path, max_side: int = MAX_SIDE) -> tuple[str, str]:
    """Return (media_type, base64 data) of a downscaled JPEG copy of `path`.

    A JPEG that is already within `max_side` (e.g. from `prepare_photos`) is sent byte for
    byte, so every backend sends the same base64 for the same photo."""
    from PIL import Image

    with Image.open(path) as im:
        if im.format == "JPEG" and max(im.size) <= max_side:
            return "image/jpeg", base64.standard_b64encode(path.read_bytes()).decode("ascii")
        im = im.convert("RGB")
        im.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=JPEG_QUALITY)
    return "image/jpeg", base64.standard_b64encode(buf.getvalue()).decode("ascii")


def prepare_photos(photos: list[Path], dest_dir: Path, max_side: int = MAX_SIDE) -> list[Path]:
    """One downscaled JPEG per photo, prepared once per case and shared by all models: the
    base64 every backend sends is then identical (and small)."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for i, photo in enumerate(photos):
        try:
            _, data = encode_image(photo, max_side)
        except Exception:
            continue  # unreadable image: skip it rather than fail the agents
        target = dest_dir / f"photo{i:02d}.jpg"
        target.write_bytes(base64.standard_b64decode(data))
        out.append(target)
    return out


def prepare_daniil_image(
    path: Path,
    *,
    max_b64_bytes: int = DANIIL_MAX_B64_BYTES,
    max_side: int = DANIIL_MAX_SIDE,
    jpeg_quality: int = DANIIL_JPEG_QUALITY,
) -> tuple[str, bytes, str]:
    """Prepare one case photo using Daniil's exact 5 MB base64 rule.

    Returns (media_type, image_bytes, suffix). If the raw image is a supported
    format and its base64 length is <= 5 MB, the original bytes are returned
    unchanged. Otherwise it is converted to RGB, downscaled to <= 1568 px, and
    re-encoded as JPEG quality 88.
    """
    suffix = path.suffix.lower()
    raw = path.read_bytes()
    b64_len = ((len(raw) + 2) // 3) * 4
    if suffix in MEDIA_TYPES and b64_len <= max_b64_bytes:
        return MEDIA_TYPES[suffix], raw, suffix

    from PIL import Image

    with Image.open(io.BytesIO(raw)) as im:
        im = im.convert("RGB")
        im.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=jpeg_quality)
    return "image/jpeg", buf.getvalue(), ".jpg"


def stage_daniil_images(
    photos: list[Path],
    dest_dir: Path,
    *,
    base_dir: Path | None = None,
) -> list[tuple[str, Path]]:
    """Stage ALL case photos (sorted by path, no count limit) into `dest_dir`.

    Returns [(display_relative_name, staged_abs_path), ...] preserving order.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    staged: list[tuple[str, Path]] = []
    for idx, photo in enumerate(sorted(photos, key=lambda p: str(p))):
        _, data, ext = prepare_daniil_image(photo)
        if base_dir is not None:
            try:
                rel = str(photo.relative_to(base_dir))
            except ValueError:
                rel = photo.name
        else:
            rel = photo.name
        safe_stem = f"{idx:02d}_{photo.stem}"
        target = dest_dir / f"{safe_stem}{ext}"
        target.write_bytes(data)
        staged.append((rel, target.resolve()))
    return staged
