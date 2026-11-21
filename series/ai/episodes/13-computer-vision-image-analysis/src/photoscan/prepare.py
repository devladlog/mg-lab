"""Get a photo ready: honour camera rotation, drop metadata (EXIF, GPS), shrink to what we need.
All coordinates the service returns refer to THIS prepared image, so blurring and cropping use the same pixels."""
from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, ImageOps

from .limits import SDK_SAFE_BYTES, check_image, ImageFacts


@dataclass
class Prepared:
    data: bytes              # PNG, no metadata
    width: int
    height: int
    facts: ImageFacts        # of the ORIGINAL
    had_metadata: bool
    notes: list[str]


def prepare(raw: bytes, name: str = "image", max_side: int = 2048) -> Prepared:
    facts = check_image(raw, name)
    notes: list[str] = []
    with Image.open(io.BytesIO(raw)) as im:
        im.load()
        had_meta = bool(im.getexif()) or bool(im.info.get("exif")) or bool(getattr(im, "text", None))
        if facts.frames > 1:
            notes.append("animated: only the first frame is analysed")
        im = ImageOps.exif_transpose(im).convert("RGB")
    if max(im.size) > max_side:
        im.thumbnail((max_side, max_side), Image.LANCZOS)
        notes.append(f"downscaled to {im.size[0]}x{im.size[1]}")
    out = io.BytesIO()
    im.save(out, "PNG", optimize=True)
    data = out.getvalue()
    if len(data) > SDK_SAFE_BYTES:           # Learn FAQ: SDK handles files up to 6 MB
        out = io.BytesIO()
        im.save(out, "JPEG", quality=88)
        data = out.getvalue()
        notes.append("re-encoded as JPEG to stay under 6 MB")
    if had_meta:
        notes.append("metadata removed")
    return Prepared(data, im.size[0], im.size[1], facts, had_meta, notes)
