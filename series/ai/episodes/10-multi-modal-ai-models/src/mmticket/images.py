"""Get an image ready for a vision model: check Learn's limits, drop metadata, shrink, send as a base64 data URL.

Learn (vision how-to): JPEG, PNG, GIF (first frame only) and WEBP; at most 20 MB per image and 10 images per request;
an image URL must be publicly reachable, so private screenshots travel as base64 data URLs instead."""
from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps

ALLOWED_FORMATS = {"JPEG", "PNG", "GIF", "WEBP"}
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_IMAGES = 10
DETAILS = ("low", "high", "auto")


class ImageError(ValueError):
    pass


@dataclass
class PreparedImage:
    name: str
    data_url: str
    width: int
    height: int
    bytes_in: int
    bytes_out: int
    metadata_removed: bool
    notes: list[str]


def has_metadata(data: bytes) -> bool:
    """True when the file carries EXIF (camera, GPS, time) or other info chunks that a re-encode would drop."""
    with Image.open(io.BytesIO(data)) as im:
        return bool(im.getexif()) or bool(im.info.get("exif")) or bool(getattr(im, "text", None))


def prepare_image(source: str | Path | bytes, name: str | None = None, max_side: int = 2048) -> PreparedImage:
    raw = Path(source).read_bytes() if isinstance(source, (str, Path)) else source
    name = name or (Path(source).name if isinstance(source, (str, Path)) else "image")
    if len(raw) > MAX_IMAGE_BYTES:
        raise ImageError(f"{name}: {len(raw) / 1_048_576:.1f} MB is over the 20 MB limit per image")
    try:
        im = Image.open(io.BytesIO(raw))
        im.load()
    except Exception as e:  # PIL raises several types for bad files
        raise ImageError(f"{name}: not a readable image ({type(e).__name__})") from e
    if im.format not in ALLOWED_FORMATS:
        raise ImageError(f"{name}: format {im.format} is not supported; use JPEG, PNG, GIF, or WEBP")
    notes: list[str] = []
    if getattr(im, "n_frames", 1) > 1:
        notes.append("animated: only the first frame is sent (Learn: GIF first frame only)")
    removed = has_metadata(raw)
    im = ImageOps.exif_transpose(im)          # honour the camera rotation BEFORE the metadata is dropped
    im = im.convert("RGB")
    if max(im.size) > max_side:
        im.thumbnail((max_side, max_side), Image.LANCZOS)
        notes.append(f"downscaled to {im.size[0]}x{im.size[1]}")
    out = io.BytesIO()
    im.save(out, format="PNG", optimize=True)   # a fresh file: no EXIF, no GPS, no comments, text stays crisp
    data = out.getvalue()
    if len(data) > MAX_IMAGE_BYTES:             # a huge photo can still be big as PNG
        out = io.BytesIO()
        im.save(out, format="JPEG", quality=90)
        data, mime = out.getvalue(), "image/jpeg"
        notes.append("re-encoded as JPEG to fit 20 MB")
    else:
        mime = "image/png"
    url = f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
    return PreparedImage(name, url, im.size[0], im.size[1], len(raw), len(data), removed, notes)


def check_batch(images: list) -> None:
    if not images:
        raise ImageError("no image given")
    if len(images) > MAX_IMAGES:
        raise ImageError(f"{len(images)} images in one request; the limit is {MAX_IMAGES}")


def content_parts(images: list[PreparedImage], detail: str) -> list[dict]:
    if detail not in DETAILS:
        raise ImageError(f"detail must be one of {DETAILS}, got {detail!r}")
    check_batch(images)
    return [{"type": "image_url", "image_url": {"url": i.data_url, "detail": detail}} for i in images]
