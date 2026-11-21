"""script.yaml checks: the structure the renderer needs, the brief's limits, and that every code excerpt is real code from this
episode (each non-elided line appears in src/ or setup/)."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = yaml.safe_load((ROOT / "script.yaml").read_text(encoding="utf-8"))
SOURCES = "\n".join(p.read_text(encoding="utf-8") for p in [*(ROOT / "src").rglob("*.py"), *(ROOT / "setup").glob("*.ps1")])
SOURCE_LINES = {ln.strip() for ln in SOURCES.splitlines()}


def test_header_and_counts():
    s = SCRIPT
    assert s["episode"] == 12 and s["slug"] == "finance-operations" and s["title"] == "Finance & Operations with Business Central"
    assert 12 <= len(s["scenes"]) <= 16
    assert len(s["youtube"]["title"]) <= 100 and s["youtube"]["title"].endswith("| DEVLADLOG Dynamics 365 #12")
    assert not set("<>") & set(s["youtube"]["title"])
    words = sum(len(sc["narration"].split()) for sc in s["scenes"])
    assert 750 <= words <= 900, words


def test_shape_of_scenes():
    scenes = SCRIPT["scenes"]
    assert scenes[0]["type"] == "title" and scenes[0].get("short") == "hook"
    assert scenes[-1]["type"] == "outro" and scenes[-1]["heading"] == "Code on GitHub, guides on devladlog.com"
    assert scenes[-1]["sub"] == "github.com/devladlog/mg-lab"
    assert sum("short" in sc for sc in scenes) == 3
    screens = [sc for sc in scenes if sc["type"] == "screen"]
    assert 3 <= len(screens) <= 5
    for sc in screens:
        assert sc["image"].startswith("screens/") and sc["bar"] and sc["demo"]
    assert len({sc["id"] for sc in scenes}) == len(scenes)


def test_code_scenes_are_short_and_real():
    for sc in (s for s in SCRIPT["scenes"] if s["type"] == "code"):
        lines = sc["code"].rstrip("\n").splitlines()
        assert len(lines) <= 16
        for ln in lines:
            t = ln.strip()
            if not t or t.startswith("# ..."):
                continue
            assert t in SOURCE_LINES, f"{sc['id']}: not found in the sources: {t}"


def test_narration_is_plain_speech():
    for sc in SCRIPT["scenes"]:
        n = sc["narration"]
        assert not any(c in n for c in "*#`_<>{}[]|"), sc["id"]


def test_the_change_is_stated_honestly():
    hook = SCRIPT["scenes"][0]["narration"]
    assert "no Dynamics 365 Finance trial" in hook and "Business Central" in hook
    arch = next(s for s in SCRIPT["scenes"] if s["id"] == "architecture")
    assert arch["heading"].startswith("Architecture")
