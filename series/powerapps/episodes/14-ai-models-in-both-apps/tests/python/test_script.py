"""script.yaml follows the regular-length brief: scene counts, words, shorts, outro, and code scenes that are real excerpts."""
import re

import pytest
import yaml

from conftest import EPISODE


@pytest.fixture(scope="module")
def script():
    return yaml.safe_load((EPISODE / "script.yaml").read_text(encoding="utf-8"))


def test_header(script):
    assert script["episode"] == 14 and script["slug"] == "ai-models-in-both-apps"
    assert (script["series_label"], script["series_name"], script["file_prefix"], script["voice"]) == ("POWER APPS", "DEVLADLOG Power Apps", "powerapps", "am_michael")
    title = script["youtube"]["title"]
    assert len(title) <= 100 and title.endswith("| DEVLADLOG Power Apps #14") and not re.search("[<>]", title)
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
    for root, suffixes in ((EPISODE / "src", {".yaml", ".yml", ".json", ".jsonl", ".bicep", ".py"}), (EPISODE / "tests", {".cs", ".py"})):
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


def test_the_story_claims_match_the_repo(script):
    text = " ".join(s["narration"] for s in script["scenes"])
    assert "Thirteen labelled notes" in text
    import json
    from conftest import SRC
    assert len((SRC / "eval" / "golden.jsonl").read_text(encoding="utf-8").splitlines()) == 13
    ext = json.loads((SRC / "solution" / "extension.schema.json").read_text(encoding="utf-8"))
    assert len(ext["tables"][0]["columns"]) == 5 and "five" in text
    assert "thirty euros" in text and "cents" in text
