"""script.yaml follows the brief: 12-16 scenes, 750-900 words, 3 shorts, 3-5 screens with a demo field, real code excerpts, outro."""
import re
from pathlib import Path

import pytest
import yaml

EP = Path(__file__).resolve().parent.parent
SRC = EP / "src"
S = yaml.safe_load((EP / "script.yaml").read_text(encoding="utf-8"))
SCENES = S["scenes"]
SUFFIXES = {".py", ".tmdl", ".json", ".kql", ".cs"}


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", t.strip())


def _source_lines():
    out = set()
    for f in SRC.rglob("*"):
        if f.is_file() and f.suffix in SUFFIXES and not {"node_modules", "dist", "bin", "obj"} & set(f.parts):
            out.update(_norm(l) for l in f.read_text(encoding="utf-8", errors="ignore").split("\n"))
    return out


def test_header():
    assert S["series_label"] == "POWER BI" and S["series_name"] == "DEVLADLOG Power BI" and S["file_prefix"] == "power-bi"
    assert S["voice"] == "am_michael" and S["slug"] == EP.name.split("-", 1)[1]
    assert S["episode"] == int(EP.name[:2])
    t = S["youtube"]["title"]
    assert len(t) <= 100 and "<" not in t and ">" not in t and t.endswith(f"| DEVLADLOG Power BI #{S['episode']}")
    assert len(S["thumbnail_text"].split("\n")) == 3
    assert S["sources"][0].startswith("https://www.devladlog.com/articles/power-bi/")


def test_shape():
    assert 12 <= len(SCENES) <= 16
    words = sum(len(s["narration"].split()) for s in SCENES)
    assert 750 <= words <= 900, words
    assert SCENES[0]["type"] == "title" and SCENES[0]["short"] == "hook"
    assert len([s for s in SCENES if "short" in s]) == 3
    screens = [s for s in SCENES if s["type"] == "screen"]
    assert 3 <= len(screens) <= 5
    for s in screens:
        assert s["image"].startswith("screens/") and s["bar"] and s["demo"]
    last = SCENES[-1]
    assert last["type"] == "outro" and last["heading"] == "Code on GitHub, guides on devladlog.com" and last["sub"] == "github.com/devladlog/mg-lab"
    assert len({s["id"] for s in SCENES}) == len(SCENES)


def test_narration_is_plain_speech():
    for s in SCENES:
        n = s["narration"]
        assert not re.search(r"[`*#_<>{}\[\]]", n), s["id"]
        assert not re.search(r"[\U0001F300-\U0001FAFF]", n), s["id"]


def test_code_scenes_are_real_excerpts():
    lines = _source_lines()
    code = [s for s in SCENES if s["type"] == "code"]
    assert code
    for s in code:
        body = s["code"].rstrip().split("\n")
        assert len(body) <= 16, s["id"]
        for l in body:
            if l.strip():
                assert _norm(l) in lines, f"{s['id']}: not found in src: {l.strip()[:80]}"


def test_there_is_a_gotcha_scene():
    assert any("gotcha" in s["heading"].lower() or s["id"] == "gotcha" for s in SCENES)
