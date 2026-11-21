"""script.yaml is a draft for pipeline/make_episode.py: check the shape, and that code scenes quote real files."""
import re

import yaml

from conftest import ROOT

SCRIPT = yaml.safe_load((ROOT / "script.yaml").read_text())
SCENES = SCRIPT["scenes"]
SOURCE_SUFFIXES = {".cs", ".bicep", ".sh", ".yaml", ".csproj", ".py", ".json"}


def words(scene) -> int:
    return len(re.findall(r"\S+", scene.get("narration", "")))


def test_header_follows_the_brief():
    assert SCRIPT["episode"] == 8 and SCRIPT["slug"] == "container-apps-aks"
    assert SCRIPT["series_label"] == "AZURE" and SCRIPT["file_prefix"] == "azure"
    title = SCRIPT["youtube"]["title"]
    assert len(title) <= 100 and "<" not in title and ">" not in title and title.endswith("| DEVLADLOG Azure #8")
    assert SCRIPT["sources"] == ["https://www.devladlog.com/articles/azure/2026-02-03-container-apps-aks-complete-guide-2026/"]


def test_scene_count_length_and_structure():
    assert 12 <= len(SCENES) <= 16
    assert SCENES[0]["type"] == "title" and SCENES[-1]["type"] == "outro"
    assert SCENES[-1]["heading"] == "Code on GitHub, guides on devladlog.com" and SCENES[-1]["sub"] == "github.com/devladlog/mg-lab"
    assert 750 <= sum(words(s) for s in SCENES) <= 900
    screens = [s for s in SCENES if s["type"] == "screen"]
    assert 3 <= len(screens) <= 5
    assert all(s["image"].startswith("screens/") and s["bar"] and s["demo"] for s in screens)
    assert len([s for s in SCENES if "short" in s]) == 3


def test_narration_is_plain_speech():
    for s in SCENES:
        assert not re.search(r"[`*#_<>{}/\d]", s["narration"]), s["id"]


def test_code_scenes_are_short_real_excerpts():
    files = [p for p in ROOT.rglob("*") if p.suffix in SOURCE_SUFFIXES and p.is_file()
             and not {"bin", "obj", "__pycache__"} & set(p.parts) and p.name != "script.yaml"]
    corpus = {line.strip() for p in files for line in p.read_text(errors="ignore").splitlines()}
    for s in (s for s in SCENES if s["type"] == "code" and s["lang"] != "text"):
        lines = [l for l in s["code"].splitlines() if l.strip()]
        assert len(lines) <= 16, s["id"]
        missing = [l for l in lines if l.strip() not in corpus]
        assert not missing, f"{s['id']}: not found in the folder: {missing}"


def test_no_real_identifiers():
    text = (ROOT / "script.yaml").read_text().lower()
    assert "devladlog.com" in text and "devladlog.onmicrosoft" not in text
