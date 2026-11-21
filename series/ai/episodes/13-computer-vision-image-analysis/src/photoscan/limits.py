"""Input limits, from Learn (Image Analysis overview and FAQ). Checked before any call is made."""
from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image

# Learn, overview-image-analysis, "Input requirements" (version 4.0)
V4_FORMATS = {"JPEG", "PNG", "GIF", "BMP", "WEBP", "ICO", "TIFF", "MPO"}
MAX_BYTES = 20 * 1024 * 1024            # "less than 20 megabytes"
MIN_SIDE = 50                           # "greater than 50 x 50 pixels"
MAX_SIDE = 16000                        # "less than 16,000 x 16,000 pixels"
# Learn, Vision FAQ: "client library SDKs can handle files up to 6 MB". We keep what we send under that.
SDK_SAFE_BYTES = 6 * 1024 * 1024
# Learn, Vision FAQ: the free tier allows 20 transactions per minute (S1: up to 20 per second).
F0_CALLS_PER_MINUTE = 20
# Learn, "Smart-cropped thumbnails": aspect ratios in [0.75, 1.80]
CROP_RATIO_MIN, CROP_RATIO_MAX = 0.75, 1.80


class ImageRejected(ValueError):
    pass


@dataclass
class ImageFacts:
    format: str
    width: int
    height: int
    bytes: int
    frames: int


def check_image(data: bytes, name: str = "image") -> ImageFacts:
    """Raise ImageRejected with a plain reason if the service would refuse this image."""
    if len(data) >= MAX_BYTES:
        raise ImageRejected(f"{name}: {len(data) / 1_048_576:.1f} MB, the service needs less than 20 MB")
    try:
        with Image.open(io.BytesIO(data)) as im:
            fmt, (w, h), frames = im.format, im.size, getattr(im, "n_frames", 1)
    except Exception as e:
        raise ImageRejected(f"{name}: not a readable image ({type(e).__name__})") from e
    if fmt not in V4_FORMATS:
        raise ImageRejected(f"{name}: format {fmt} is not in the supported list ({', '.join(sorted(V4_FORMATS))})")
    if w <= MIN_SIDE or h <= MIN_SIDE:
        raise ImageRejected(f"{name}: {w}x{h} px, each side must be greater than {MIN_SIDE}")
    if w >= MAX_SIDE or h >= MAX_SIDE:
        raise ImageRejected(f"{name}: {w}x{h} px, each side must be less than {MAX_SIDE}")
    return ImageFacts(fmt, w, h, len(data), frames)


def check_ratios(ratios: list[float]) -> list[float]:
    bad = [r for r in ratios if not CROP_RATIO_MIN <= r <= CROP_RATIO_MAX]
    if bad:
        raise ValueError(f"smart-crop aspect ratios must be within [{CROP_RATIO_MIN}, {CROP_RATIO_MAX}]: {bad}")
    return ratios
