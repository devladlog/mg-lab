"""Draw fictional error screenshots with Pillow. No real product, person, or data: everything is made up.

data/cases.json holds the ground truth for each picture and the text of its voice note. The pictures are generated,
not committed, so the repo stays small and nobody can mistake them for real screenshots."""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

DATA = Path(__file__).resolve().parents[2] / "data" / "cases.json"
LOOKS = {
    "light": dict(bg=(240, 240, 240), panel=(255, 255, 255), title=(32, 84, 160), text=(20, 20, 20), accent=(180, 30, 30)),
    "dark": dict(bg=(24, 24, 28), panel=(40, 40, 46), title=(70, 70, 90), text=(225, 225, 225), accent=(255, 110, 110)),
}


def load_cases(path: str | Path = DATA) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _font(size: int):
    return ImageFont.load_default(size=size)    # Pillow's bundled font: Latin text with accents is covered


def render(case: dict) -> Image.Image:
    look = LOOKS[case.get("look", "light")]
    w, h = case.get("size", [1000, 560])
    fs = case.get("font", 26)
    im = Image.new("RGB", (w, h), look["bg"])
    d = ImageDraw.Draw(im)
    d.rectangle([20, 20, w - 20, h - 20], fill=look["panel"])
    d.rectangle([20, 20, w - 20, 70], fill=look["title"])
    d.text((36, 30), case["window_title"], font=_font(24), fill=(255, 255, 255))
    y = 100
    for i, line in enumerate(case["lines"]):
        color = look["accent"] if i == 0 else look["text"]
        d.text((40, y), line, font=_font(fs), fill=color)
        y += int(fs * 1.5)
    if case.get("hidden_text"):        # the prompt-injection case: low-contrast text a person would not notice
        faint = tuple(int(c * 0.9 + p * 0.1) for c, p in zip(look["panel"], look["text"]))
        d.text((40, h - 70), case["hidden_text"], font=_font(max(12, fs - 8)), fill=faint)
    return im


def write_all(out_dir: str | Path, cases: list[dict] | None = None) -> list[Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for c in cases or load_cases():
        p = out / f"{c['id']}.png"
        render(c).save(p)
        paths.append(p)
    return paths
