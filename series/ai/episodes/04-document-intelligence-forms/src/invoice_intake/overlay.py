"""Draw what the model read on top of the document: one box per extracted field, coloured by confidence.

    PYTHONPATH=src python -m invoice_intake.overlay samples/04-adventure-works-faded.png results/04-adventure-works-faded.json

Each DocumentField carries boundingRegions [{pageNumber, polygon: [x1, y1, x2, y2, ...]}]; for images the
polygon unit is pixels (the page's `unit` says so), so the polygon can be drawn straight onto the image.
Green = at or above the field's threshold, amber = below (goes to review), so reviewers see *where* to look.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from PIL import Image, ImageDraw, ImageFont

from .decide import THRESHOLDS
from .fields import HEADER_FIELDS

GREEN, AMBER = (22, 163, 74), (217, 119, 6)
DEFAULT_THRESHOLD = 0.80


def field_boxes(analyze_result: Mapping[str, Any], page: int = 1) -> list[tuple[str, float, list[float]]]:
    """[(field name, confidence, polygon)] for the header fields found on `page`."""
    doc = (analyze_result.get("documents") or [{}])[0]
    pages = {p.get("pageNumber"): p for p in analyze_result.get("pages") or []}
    if pages.get(page, {}).get("unit") not in (None, "pixel"):
        raise ValueError("polygons are not in pixels (PDF pages use inches); render the page to an image first")
    out = []
    for name in HEADER_FIELDS:
        f = (doc.get("fields") or {}).get(name)
        if not f:
            continue
        for region in f.get("boundingRegions") or []:
            if region.get("pageNumber") == page and region.get("polygon"):
                out.append((name, float(f.get("confidence") or 0.0), list(region["polygon"])))
    return out


def draw_overlay(image_path: str | Path, analyze_result: Mapping[str, Any], out_path: str | Path) -> Path:
    im = Image.open(image_path).convert("RGB")
    d = ImageDraw.Draw(im)
    font = ImageFont.load_default(size=20)
    for name, conf, poly in field_boxes(analyze_result):
        ok = conf >= THRESHOLDS.get(name, DEFAULT_THRESHOLD)
        colour = GREEN if ok else AMBER
        points = list(zip(poly[0::2], poly[1::2]))
        d.polygon(points, outline=colour, width=4)
        x, y = min(p[0] for p in points), min(p[1] for p in points)
        label = f"{name} {conf:.2f}"
        w = d.textlength(label, font=font)
        d.rectangle((x, y - 26, x + w + 8, y - 2), fill=colour)
        d.text((x + 4, y - 25), label, font=font, fill="white")
    out_path = Path(out_path)
    im.save(out_path)
    return out_path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="invoice_intake.overlay", description="Draw field boxes and confidences.")
    ap.add_argument("image")
    ap.add_argument("result_json")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    out = a.out or str(Path(a.image).with_suffix("")) + "-overlay.png"
    print(draw_overlay(a.image, json.loads(Path(a.result_json).read_text(encoding="utf-8")), out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
