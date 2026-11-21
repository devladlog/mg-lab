"""script.yaml: the shape make_episode.py and the brief expect, and code scenes that are real excerpts."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = yaml.safe_load((ROOT / "script.yaml").read_text(encoding="utf-8"))
SCENES = SCRIPT["scenes"]
SOURCE_LINES = {ln.strip() for f in (ROOT / "src").rglob("*") if f.suffix in (".sql", ".py", ".ps1", ".dtsx", ".rdl")
                for ln in f.read_text(encoding="utf-8").splitlines() if ln.strip()}


def test_header():
    for key in ("episode", "slug", "series_label", "series_name", "file_prefix", "title", "subtitle", "voice",
                "thumbnail_text", "youtube", "sources"):
        assert SCRIPT.get(key), key
    assert SCRIPT["series_label"] == "SQL" and SCRIPT["file_prefix"] == "sql" and SCRIPT["voice"] == "am_michael"
    assert ROOT.name == f"{SCRIPT['episode']:02d}-{SCRIPT['slug']}"
    title = SCRIPT["youtube"]["title"]
    assert len(title) <= 100 and "<" not in title and ">" not in title
    assert title.endswith(f"| DEVLADLOG SQL #{SCRIPT['episode']}")
    assert any("devladlog.com/articles/sql/" in s for s in SCRIPT["sources"])


def test_scenes_shape_and_length():
    assert 12 <= len(SCENES) <= 16
    assert SCENES[0]["type"] == "title" and SCENES[0].get("short") == "hook"
    assert SCENES[-1] == {**SCENES[-1], "type": "outro", "heading": "Code on GitHub, guides on devladlog.com",
                          "sub": "github.com/devladlog/mg-lab"}
    assert len([s for s in SCENES if s.get("short")]) == 3
    screens = [s for s in SCENES if s["type"] == "screen"]
    assert 3 <= len(screens) <= 5
    for s in screens:
        assert s["image"].startswith("screens/") and s["bar"] and len(s["demo"]) > 80
    words = sum(len(s["narration"].split()) for s in SCENES)
    assert 750 <= words <= 900, words
    assert len({s["id"] for s in SCENES}) == len(SCENES)


def test_narration_is_plain_speech():
    for s in SCENES:
        assert not re.search(r"[`*#_<>]|https?://", s["narration"]), s["id"]


@pytest.mark.parametrize("scene", [s for s in SCENES if s["type"] == "code"], ids=lambda s: s["id"])
def test_code_scenes_are_real_excerpts(scene):
    lines = scene["code"].rstrip("\n").split("\n")
    assert len(lines) <= 16
    if scene.get("lang") in ("sql", "python", "xml", "powershell"):
        for ln in lines:
            if ln.strip() and not re.match(r"\s*(--|#) \.\.\.", ln):
                assert ln.strip() in SOURCE_LINES, f"{scene['id']}: not in src/: {ln.strip()}"
