"""script.yaml against the repo: the header the renderer needs, the length, and that every configuration excerpt on
screen is a real line of the real file (comments aside) and every number quoted is one a test here produces."""
from __future__ import annotations

import re

import yaml

from conftest import APP, EPISODE

SCRIPT = yaml.safe_load((EPISODE / "script.yaml").read_text(encoding="utf-8"))
SCENES = {s["id"]: s for s in SCRIPT["scenes"]}
SOURCES = {"props": "Directory.Build.props", "editorconfig": ".editorconfig", "quality-job": ".github/workflows/ci-cd.yml"}


def test_header_and_shape():
    assert (SCRIPT["episode"], SCRIPT["slug"], SCRIPT["series_label"]) == (6, "code-quality-tools", "DEV TOOLS")
    assert SCRIPT["file_prefix"] == "developer-tools" and SCRIPT["voice"] == "am_michael"
    title = SCRIPT["youtube"]["title"]
    assert len(title) <= 100 and "<" not in title and ">" not in title and title.endswith("| DEVLADLOG Dev Tools #6")
    assert SCRIPT["sources"] == ["https://www.devladlog.com/articles/developer-tools/2025-12-09-code-quality-tools-complete-guide-2025/"]
    scenes = SCRIPT["scenes"]
    assert 12 <= len(scenes) <= 16
    assert 750 <= sum(len(s["narration"].split()) for s in scenes) <= 900
    assert scenes[0]["type"] == "title" and scenes[0]["short"] == "hook"
    assert scenes[-1] == {**scenes[-1], "type": "outro", "heading": "Code on GitHub, guides on devladlog.com",
                          "sub": "github.com/devladlog/mg-lab"}
    assert len([s for s in scenes if s.get("short")]) == 3
    screens = [s for s in scenes if s["type"] == "screen"]
    assert 3 <= len(screens) <= 5
    assert all(s["image"] == f"screens/{s['id']}.jpg" and s["bar"] and s["demo"] for s in screens)
    assert all(not re.search(r"[*_`#]|[^\x00-ɏ]", s["narration"]) for s in scenes), "markdown or emoji in narration"


def test_code_scenes_are_at_most_16_lines():
    assert all(len(s["code"].rstrip().splitlines()) <= 16 for s in SCRIPT["scenes"] if s["type"] == "code")


def test_configuration_excerpts_are_real_lines_of_the_real_files():
    for scene_id, rel in SOURCES.items():
        real = {line.strip() for line in (APP / rel).read_text(encoding="utf-8").splitlines()}
        for line in SCENES[scene_id]["code"].splitlines():
            code = line.strip()
            if code and not code.startswith(("#", "<!--")):
                assert code in real, f"{scene_id}: {code!r} is not in {rel}"


def test_ruff_and_coverage_numbers_on_screen_are_the_ones_the_tests_assert():
    ruff, cov = SCENES["ruff"]["code"], SCENES["diffcov"]["code"]
    assert "Found 12 errors (6 fixed, 6 remaining)." in ruff and "1 file reformatted, 9 files left unchanged" in ruff
    assert 'select = ["E", "W", "F", "I", "B", "UP", "SIM", "S"]' in (APP / "ruff.toml").read_text() and \
        'select = ["E", "W", "F", "I", "B", "UP", "SIM", "S"]' in ruff
    for text in ("85/93", "91.4", "5/13", "38.5", "lines 7, 9, 12-17", "diff coverage 38.5% (5/13 changed lines) is below 80%"):
        assert text in cov
    assert "--min-line 90" in cov and "--min-diff 80" in cov


def test_the_gotcha_is_the_compiler_message_the_analyzer_test_asserts():
    gotcha = " ".join(SCENES["gotcha"]["code"].split())
    assert "error EnableGenerateDocumentationFile: Set MSBuild property 'GenerateDocumentationFile' to 'true'" in gotcha
