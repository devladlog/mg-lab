"""People in a photo: pixelate every detected person, then build thumbnails from the pixelated copy only.
The people feature returns boxes and confidences, not identities (Learn). It does NOT see text that names someone,
so a name on a badge or a screen survives: see decide.py."""
from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image

from .model import Box, Crop, Person

PERSON_THRESHOLD = 0.20      # deliberately low: Learn's own example returns a clearly visible person at 0.27
MARGIN = 0.05                # grow each box by 5 % of its size
BLOCKS = 12                  # the box is reduced to about 12 blocks across its longest side


@dataclass
class Redacted:
    data: bytes
    blurred: list[Box]
    ignored: int             # people below the threshold: not blurred


def grow(b: Box, w: int, h: int, margin: float = MARGIN) -> Box:
    dx, dy = int(b.w * margin), int(b.h * margin)
    x0, y0 = max(0, b.x - dx), max(0, b.y - dy)
    x1, y1 = min(w, b.x + b.w + dx), min(h, b.y + b.h + dy)
    return Box(x0, y0, max(0, x1 - x0), max(0, y1 - y0))


def pixelate_region(im: Image.Image, b: Box) -> None:
    if b.w <= 0 or b.h <= 0:
        return
    region = im.crop((b.x, b.y, b.x + b.w, b.y + b.h))
    step = max(1, max(b.w, b.h) // BLOCKS)
    small = region.resize((max(1, b.w // step), max(1, b.h // step)), Image.BILINEAR)
    im.paste(small.resize(region.size, Image.NEAREST), (b.x, b.y))


def redact_people(png: bytes, people: list[Person], threshold: float = PERSON_THRESHOLD) -> Redacted:
    im = Image.open(io.BytesIO(png)).convert("RGB")
    done, ignored = [], 0
    for p in people:
        if p.confidence < threshold:
            ignored += 1
            continue
        g = grow(p.box, *im.size)
        pixelate_region(im, g)
        done.append(g)
    out = io.BytesIO()
    im.save(out, "PNG")
    return Redacted(out.getvalue(), done, ignored)


def thumbnail(png: bytes, crop: Crop, size: int = 256) -> bytes:
    im = Image.open(io.BytesIO(png)).convert("RGB")
    b = crop.box
    t = im.crop((b.x, b.y, b.x + b.w, b.y + b.h))
    t.thumbnail((size * 2, size))
    out = io.BytesIO()
    t.save(out, "PNG")
    return out.getvalue()


def region_changed(before: bytes, after: bytes, b: Box) -> bool:
    """True if the pixels inside the box differ between two images (used by the evaluation: did the blur really happen?)"""
    a = Image.open(io.BytesIO(before)).convert("RGB").crop((b.x, b.y, b.x + b.w, b.y + b.h))
    c = Image.open(io.BytesIO(after)).convert("RGB").crop((b.x, b.y, b.x + b.w, b.y + b.h))
    return a.tobytes() != c.tobytes()
