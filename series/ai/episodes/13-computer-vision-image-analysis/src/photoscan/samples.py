"""Draw the fictional asset-label photos. Generated at run time, not committed. The Learn sample photo (a person at a
meeting-room display) is downloaded by `fetch-sample`, because a drawing cannot test people detection."""
from __future__ import annotations

import io
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

LEARN_SAMPLE_URL = "https://learn.microsoft.com/azure/ai-services/computer-vision/media/quickstarts/presentation.png"


def _font(size: int):
    return ImageFont.load_default(size=size)


def label(tag_text: str, canvas=(1200, 800), fg=(20, 20, 20), bg=(245, 245, 245), scale=1.0) -> Image.Image:
    im = Image.new("RGB", canvas, (120, 125, 130))                   # a grey laptop lid
    d = ImageDraw.Draw(im)
    w, h = int(canvas[0] * 0.7), int(canvas[1] * 0.45)
    x, y = (canvas[0] - w) // 2, (canvas[1] - h) // 2
    d.rectangle((x, y, x + w, y + h), fill=bg)
    big, small = int(110 * scale), int(44 * scale)
    d.text((x + 40, y + 30), "CONTOSO PORTO", font=_font(small), fill=fg)
    d.text((x + 40, y + 30 + int(70 * scale)), tag_text, font=_font(big), fill=fg)
    d.text((x + 40, y + 30 + int(220 * scale)), "IT ASSET - DO NOT REMOVE", font=_font(small), fill=fg)
    return im


def png(im: Image.Image) -> bytes:
    b = io.BytesIO()
    im.save(b, "PNG")
    return b.getvalue()


def rotated_jpeg_with_exif(im: Image.Image) -> bytes:
    """A phone photo: pixels stored sideways, EXIF orientation 6, plus a (fictional) GPS block."""
    sideways = im.rotate(90, expand=True)           # stored rotated; orientation 6 tells viewers to rotate back
    exif = Image.Exif()
    exif[0x0112] = 6
    exif[0x010F] = "ContosoPhone"
    gps = exif.get_ifd(0x8825)
    gps[1], gps[2], gps[3], gps[4] = "N", (41.0, 9.0, 0.0), "W", (8.0, 36.0, 0.0)   # near Porto; fictional use
    b = io.BytesIO()
    sideways.save(b, "JPEG", quality=92, exif=exif)
    return b.getvalue()


def generate() -> dict[str, bytes]:
    out = {
        "label-clean": png(label("CON-48213")),
        "label-small": png(label("CON-30571", canvas=(3200, 2200), scale=0.45)),
        "label-lookalike": png(label("CON-4821O")),
        "label-lowcontrast": png(label("CON-77120", fg=(205, 205, 205), bg=(235, 235, 235))),
        "label-phone-rotated": rotated_jpeg_with_exif(label("CON-55306")),
        "no-tag": png(_no_tag()),
    }
    return out


def _no_tag() -> Image.Image:
    im = Image.new("RGB", (1200, 800), (90, 110, 130))
    d = ImageDraw.Draw(im)
    d.rectangle((300, 250, 900, 600), fill=(60, 60, 70))
    d.text((340, 280), "FRAGILE", font=_font(90), fill=(240, 240, 240))
    return im


def fetch_sample(dest: Path) -> Path:
    """Download the Learn quickstart photo. Untrusted bytes: only ever opened with Pillow."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(LEARN_SAMPLE_URL, timeout=30) as r:        # follows the redirect to the en-us path
        data = r.read(25 * 1024 * 1024)
    Image.open(io.BytesIO(data)).verify()
    dest.write_bytes(data)
    return dest
