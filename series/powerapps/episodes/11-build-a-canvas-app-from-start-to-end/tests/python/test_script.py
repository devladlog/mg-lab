"""script.yaml follows the long-form brief: scene counts, words, shorts, outro, and code scenes that are real excerpts."""
import re

import pytest
import yaml

from conftest import EPISODE


@pytest.fixture(scope="module")
def script():
    return yaml.safe_load((EPISODE / "script.yaml").read_text(encoding="utf-8"))


def test_header(script):
    assert script["episode"] == 11
    assert script["series_label"] == "POWER APPS"
    assert script["series_name"] == "DEVLADLOG Power Apps"
    assert script["file_prefix"] == "powerapps"
    assert script["voice"] == "am_michael"
    title = script["youtube"]["title"]
    assert len(title) <= 100 and title.endswith("| DEVLADLOG Power Apps #11")
    assert script["youtube"]["tags"] and script["sources"]


def test_scene_counts_and_words(script):
    scenes = script["scenes"]
    assert 30 <= len(scenes) <= 40
    assert 8 <= sum(s["type"] == "screen" for s in scenes) <= 14
    assert sum("short" in s for s in scenes) == 3
    words = sum(len(s["narration"].split()) for s in scenes)
    assert 2200 <= words <= 3200, words
    assert len({s["id"] for s in scenes}) == len(scenes)


def test_outro_and_gotcha(script):
    last = script["scenes"][-1]
    assert last["type"] == "outro"
    assert last["heading"] == "Code on GitHub, guides on devladlog.com"
    assert last["sub"] == "github.com/devladlog/mg-lab"
    assert any(s["id"] == "gotcha" for s in script["scenes"])


def test_narration_is_plain_spoken_english(script):
    for s in script["scenes"]:
        n = s["narration"]
        assert not re.search(r"[*_`#\[\]{}<>|]", n), s["id"]
        assert not re.search(r"[☀-➿\U0001F300-\U0001FAFF]", n), s["id"]


def test_screen_scenes_have_image_bar_demo(script):
    for s in script["scenes"]:
        if s["type"] == "screen":
            assert s["image"].startswith("screens/") and s["image"].endswith(".jpg")
            assert s["bar"] and s["demo"]


def test_code_scenes_are_short_and_use_real_names(script):
    corpus = ""
    for p in (EPISODE / "src").rglob("*"):
        if p.is_file() and p.suffix in {".yaml", ".json", ".ps1", ".xml"}:
            corpus += p.read_text(encoding="utf-8-sig")
    for p in (EPISODE / "tests").rglob("*"):
        if p.is_file() and p.suffix in {".cs", ".py", ".ps1"}:
            corpus += p.read_text(encoding="utf-8")
    for s in script["scenes"]:
        if s["type"] != "code":
            continue
        assert len(s["code"].rstrip().splitlines()) <= 16, s["id"]
        for ident in re.findall(r"\b(?:Validate\w+|ResolveFinding|InspectionRef|icoSync|galInspections|camFinding|conInspectionBody|"
                                r"test_\w+|[A-Z][a-z]+_[A-Za-z_]+)\b", s["code"]):
            assert ident in corpus, f"{s['id']}: {ident} is not in src or tests"


def test_no_real_tenant_names(script):
    text = (EPISODE / "script.yaml").read_text(encoding="utf-8")
    assert "dynamics.com" not in text.replace("contoso.crm.dynamics.com", "")
