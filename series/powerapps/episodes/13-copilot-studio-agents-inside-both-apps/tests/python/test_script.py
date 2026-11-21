"""script.yaml follows the regular-length brief: scene counts, words, shorts, outro, and code scenes that are real excerpts."""
import re

import pytest
import yaml

from conftest import EPISODE


@pytest.fixture(scope="module")
def script():
    return yaml.safe_load((EPISODE / "script.yaml").read_text(encoding="utf-8"))


def test_header(script):
    assert script["episode"] == 13 and script["slug"] == "copilot-studio-agents-inside-both-apps"
    assert (script["series_label"], script["series_name"], script["file_prefix"], script["voice"]) == ("POWER APPS", "DEVLADLOG Power Apps", "powerapps", "am_michael")
    title = script["youtube"]["title"]
    assert len(title) <= 100 and title.endswith("| DEVLADLOG Power Apps #13") and not re.search("[<>]", title)
    assert script["youtube"]["tags"] and script["sources"]


def test_scene_counts_words_and_shorts(script):
    scenes = script["scenes"]
    assert 12 <= len(scenes) <= 16
    assert 3 <= sum(s["type"] == "screen" for s in scenes) <= 5
    assert sum("short" in s for s in scenes) == 3 and scenes[0]["short"] == "hook" and scenes[0]["type"] == "title"
    words = sum(len(s["narration"].split()) for s in scenes)
    assert 750 <= words <= 900, words
    assert len({s["id"] for s in scenes}) == len(scenes)


def test_outro_and_gotcha(script):
    last = script["scenes"][-1]
    assert (last["type"], last["heading"], last["sub"]) == ("outro", "Code on GitHub, guides on devladlog.com", "github.com/devladlog/mg-lab")
    assert any(s["id"] == "gotcha" for s in script["scenes"])


def test_narration_is_plain_spoken_english(script):
    for s in script["scenes"]:
        assert not re.search(r"[*_`#\[\]{}<>|]", s["narration"]), s["id"]
        assert not re.search(r"[☀-➿\U0001F300-\U0001FAFF]", s["narration"]), s["id"]


def test_screen_scenes_have_image_bar_demo(script):
    for s in script["scenes"]:
        if s["type"] == "screen":
            assert s["image"].startswith("screens/") and s["image"].endswith(".jpg") and s["bar"] and s["demo"]


def _corpus_lines():
    lines = set()
    for root, suffixes in ((EPISODE / "src", {".yaml", ".yml", ".json", ".ps1", ".py", ".js", ".md"}), (EPISODE / "tests", {".cs", ".py", ".js"})):
        for p in root.rglob("*"):
            if p.is_file() and p.suffix in suffixes and not {"bin", "obj", "__pycache__", ".pytest_cache"} & set(p.parts):
                lines.update(line.strip() for line in p.read_text(encoding="utf-8-sig").splitlines() if line.strip())
    return lines


def test_code_scenes_are_short_real_lines_of_the_source(script):
    corpus = _corpus_lines()
    for s in script["scenes"]:
        if s["type"] != "code":
            continue
        assert len(s["code"].rstrip().splitlines()) <= 16, s["id"]
        for line in (l.strip() for l in s["code"].rstrip().splitlines() if l.strip()):
            assert line in corpus, f"{s['id']}: not a line of src or tests: {line}"


def test_the_numbers_in_the_script_match_the_tests_that_exist(script):
    text = " ".join(s["narration"] for s in script["scenes"])
    assert "Thirty Power Fx tests, twenty three Python tests and six JavaScript tests" in text
    cs = (EPISODE / "tests" / "ContosoInspections.Agent.Tests" / "AgentTests.cs").read_text(encoding="utf-8")
    assert len(re.findall(r"\[Fact\]", cs)) + sum(len(re.findall(r"\[InlineData", blk)) for blk in re.split(r"\[Theory\]", cs)[1:]) >= 20
