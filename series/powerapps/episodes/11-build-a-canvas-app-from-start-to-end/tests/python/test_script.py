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


def _corpus_lines():
    """Every stripped, non-blank line of the episode's own source and tests."""
    lines = set()
    for root, suffixes in ((EPISODE / "src", {".yaml", ".json", ".ps1", ".xml"}), (EPISODE / "tests", {".cs", ".py", ".ps1"})):
        for p in root.rglob("*"):
            if p.is_file() and p.suffix in suffixes and not {"bin", "obj", "__pycache__"} & set(p.parts):
                lines.update(line.strip() for line in p.read_text(encoding="utf-8-sig").splitlines() if line.strip())
    return lines


# Scenes that show a terminal, not a file: the plan output is checked against a real -PlanOnly run, the solution scene is the real
# pac commands plus the names of tests that exist.
TERMINAL_SCENES = {"provision", "solution"}


def test_code_scenes_are_short_real_lines_of_the_source(script):
    corpus = _corpus_lines()
    for s in script["scenes"]:
        if s["type"] != "code" or s["id"] in TERMINAL_SCENES:
            continue
        lines = [line.strip() for line in s["code"].rstrip().splitlines() if line.strip()]
        assert len(s["code"].rstrip().splitlines()) <= 9, s["id"]
        for line in lines:
            assert line in corpus, f"{s['id']}: not a line of src or tests: {line}"


def test_the_plan_scene_is_real_plan_output(script):
    from conftest import SCRIPTS, run
    scene = next(s for s in script["scenes"] if s["id"] == "provision")
    shown = scene["code"].rstrip().splitlines()
    assert len(shown) <= 9
    out = run("pwsh", "-NoProfile", "-NonInteractive", "-File", SCRIPTS / "Provision-ContosoInspections.ps1",
              "-EnvironmentUrl", "https://contoso-dev.crm4.dynamics.com", "-PlanOnly")
    assert out.code == 0, out
    real = {line.rstrip() for line in out.out.splitlines()}
    assert shown[0].startswith("> Provision-ContosoInspections.ps1 -EnvironmentUrl") and shown[0].endswith("-PlanOnly")
    for line in shown[1:]:
        assert line.rstrip() in real, f"not in the real plan output: {line}"


def test_the_solution_scene_names_real_tests_and_commands(script):
    corpus = _corpus_lines()
    scene = next(s for s in script["scenes"] if s["id"] == "solution")
    assert len(scene["code"].rstrip().splitlines()) <= 9
    for line in scene["code"].splitlines():
        line = line.strip()
        if line.startswith("Passed"):
            assert any(f"def {line.split()[-1]}(" in c for c in corpus), line
        elif line:
            assert line.startswith("pac solution "), line


def test_code_scenes_use_real_names(script):
    corpus = "\n".join(_corpus_lines())
    for s in script["scenes"]:
        if s["type"] != "code":
            continue
        for ident in re.findall(r"\b(?:Validate\w+|ResolveItem|icoSync|galInspections|conInspectionBody|test_\w+)\b", s["code"]):
            assert ident in corpus, f"{s['id']}: {ident} is not in src or tests"


def test_the_story_is_the_shared_one(script):
    text = (EPISODE / "script.yaml").read_text(encoding="utf-8")
    # Words from the old, unreconciled model: Finding, the Reviewed and Closed statuses, the old role, the typed reference number.
    for old in (r"\bfindings?\b", r"\bReviewed\b", r"\bClosed\b", r"Contoso Inspector", r"\breference number\b"):
        assert not re.search(old, text, re.I), old
    narration = " ".join(s["narration"] for s in script["scenes"])
    assert "model-driven" in narration and "back office" in narration
    assert "approved" in narration.lower() and "rejected" in narration.lower()
    ids = [s["id"] for s in script["scenes"]]
    assert "status-flow" in ids and ids.index("status-flow") < ids.index("item-screen")


def test_no_real_tenant_names(script):
    text = (EPISODE / "script.yaml").read_text(encoding="utf-8")
    assert "dynamics.com" not in text.replace("contoso.crm.dynamics.com", "")
