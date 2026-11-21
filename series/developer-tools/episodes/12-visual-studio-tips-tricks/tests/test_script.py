"""script.yaml against the repository: the header the renderer needs, the length, that every configuration excerpt on screen is a
real line of a real file, and that every command output on screen is one the tools really print."""

from __future__ import annotations

import re
import shutil

import yaml
from conftest import APP, EPISODE, tool

SCRIPT = yaml.safe_load((EPISODE / "script.yaml").read_text(encoding="utf-8"))
SCENES = {s["id"]: s for s in SCRIPT["scenes"]}
OUTPUT = (EPISODE / "tests" / "fixtures" / "command-output.txt").read_text(encoding="utf-8")
OUTPUT_LINES = [" ".join(line.split()) for line in OUTPUT.splitlines()]
# scene id -> files its configuration lines come from
SOURCES = {
    "vsconfig": [".vsconfig"],
    "slnf": ["OrdersApp.Api.slnf"],
    "snippet": ["snippets/ordtest.snippet"],
    "runsettings": [".runsettings", "Directory.Build.props"],
    "profile": ["src/Contoso.Orders.Api/Properties/launchSettings.json"],
}


def norm(line: str) -> str:
    return " ".join(line.split())


def test_header_and_shape():
    assert (SCRIPT["episode"], SCRIPT["slug"], SCRIPT["series_label"]) == (12, "visual-studio-tips-tricks", "DEV TOOLS")
    assert SCRIPT["file_prefix"] == "developer-tools" and SCRIPT["voice"] == "am_michael"
    title = SCRIPT["youtube"]["title"]
    assert len(title) <= 100 and "<" not in title and ">" not in title and title.endswith("| DEVLADLOG Dev Tools #12")
    assert SCRIPT["sources"] == [
        "https://www.devladlog.com/articles/developer-tools/2025-11-21-visual-studio-tips-tricks-complete-guide-2025/"
    ]
    scenes = SCRIPT["scenes"]
    assert 12 <= len(scenes) <= 16
    assert 750 <= sum(len(s["narration"].split()) for s in scenes) <= 900
    assert scenes[0]["type"] == "title" and scenes[0]["short"] == "hook"
    assert scenes[-1]["type"] == "outro" and scenes[-1]["sub"] == "github.com/devladlog/mg-lab"
    assert scenes[-1]["heading"] == "Code on GitHub, guides on devladlog.com"
    assert len([s for s in scenes if s.get("short")]) == 3
    screens = [s for s in scenes if s["type"] == "screen"]
    assert 3 <= len(screens) <= 5
    assert all(s["image"] == f"screens/{s['id']}.jpg" and s["bar"] and s["demo"] for s in screens)
    assert all(not re.search(r"[*_`#]|[^\x00-ɏ]", s["narration"]) for s in scenes), "markdown or emoji in narration"
    assert any(s["id"] == "gotcha" for s in scenes)


def test_code_scenes_are_at_most_16_lines():
    assert all(len(s["code"].rstrip().splitlines()) <= 16 for s in SCRIPT["scenes"] if s["type"] == "code")


def test_no_real_tenant_name_anywhere_in_the_episode_text():
    for name in ("script.yaml", "demo.md", "README.md"):
        text = (EPISODE / name).read_text(encoding="utf-8").lower()
        assert "devladlog." not in text.replace("devladlog.com", "").replace("github.com/devladlog", "")
        assert "dev.azure.com/devladlog" not in text


def test_configuration_excerpts_are_real_lines_of_the_real_files():
    for scene_id, rels in SOURCES.items():
        real = {norm(line) for rel in rels for line in (APP / rel).read_text(encoding="utf-8").splitlines()}
        for line in SCENES[scene_id]["code"].splitlines():
            code = norm(line)
            if not code or code.startswith(("#", "//", "<!--", "$")):
                continue
            if scene_id in ("slnf", "snippet") and code in OUTPUT_LINES:
                continue  # command output, checked below
            if scene_id == "snippet" and code.startswith("var response") and "/orders/99999" in code:
                continue  # expansion, checked below
            if scene_id == "snippet" and code.startswith("Assert.Equal(HttpStatusCode.NotFound"):
                continue
            assert code in real, f"{scene_id}: {code!r} is not in {rels}"


def test_command_output_on_screen_is_what_the_commands_printed():
    for scene_id in ("slnf", "gotcha", "guard"):
        for line in SCENES[scene_id]["code"].splitlines():
            code = norm(line)
            if scene_id == "guard" and not code.startswith("$"):
                continue  # the guard's problem lines are checked against a real run below
            if not code or code.startswith("#") or (scene_id == "slnf" and not (code.startswith("$") or "->" in code)):
                continue
            if code.endswith(" ..."):
                assert any(candidate.startswith(code[:-4]) for candidate in OUTPUT_LINES), f"{scene_id}: {code!r}"
            else:
                assert code in OUTPUT_LINES, f"{scene_id}: {code!r} is not in tests/fixtures/command-output.txt"


def test_the_expansion_on_screen_is_what_the_expander_prints():
    lines = SCENES["snippet"]["code"].splitlines()
    command = next(line for line in lines if line.startswith("$ python tools/vs_files.py expand"))
    values = re.findall(r"--set (\S+)", command)
    code, out = tool("expand", APP / "snippets" / "ordtest.snippet", *[a for v in values for a in ("--set", v)])
    assert code == 0
    shown = [norm(line) for line in lines[lines.index("# expands to:") + 1 :]]
    assert shown and all(line in [norm(o) for o in out.splitlines()] for line in shown)


def test_the_guard_messages_on_screen_are_what_the_check_prints(tmp_path):
    """Make the three mistakes from the script in a copy and compare the check's output with the lines on screen."""
    repo = tmp_path / "orders-app"
    shutil.copytree(APP, repo, ignore=shutil.ignore_patterns("bin", "obj", "__pycache__", ".ruff_cache"))
    (repo / ".runsettings").write_text((repo / ".runsettings").read_text().replace("MaxCpuCount", "MaxCPUCount"))
    slnf = repo / "OrdersApp.Api.slnf"
    slnf.write_text(slnf.read_text().replace("Contoso.Orders.Api", "B").replace("src\\\\B\\\\B.csproj", "src\\\\B\\\\B.csproj"))
    snippet = repo / "snippets" / "ordtest.snippet"
    snippet.write_text(snippet.read_text().replace("$end$", "$end$ $missing$"))
    code, out = tool("check", repo, "--known-ids", EPISODE / "tests" / "fixtures" / "learn-component-ids.txt")
    assert code == 1
    printed = [norm(line) for line in out.splitlines()]
    shown = [norm(line) for line in SCENES["guard"]["code"].splitlines() if line.startswith((".runsettings:", "OrdersApp.Api.slnf:", "snippets/"))]
    assert len(shown) == 3
    for line in shown:
        assert line in printed, f"{line!r} not printed; printed: {printed}"


def test_numbers_and_names_on_screen_are_the_ones_the_other_tests_assert():
    tests = "".join(p.read_text() for p in (EPISODE / "tests").glob("test_*.py") if p.name != "test_script.py")
    for text in ('"vs-profile"', '== 20', '== 237', '"dev"', "Passed:\\s+36, Skipped:\\s+4", "Restart is needed to apply the changes",
                 "test run timeout of 8000 milliseconds exceeded", "CONTOSO_REGION is '(not set)'", "Hot reload succeeded"):
        assert text in tests, text
    narration = " ".join(s["narration"] for s in SCRIPT["scenes"])
    assert "twenty orders" in narration and "two hundred thirty seven" in narration
    assert "eight seconds" in narration and "five minutes" in narration and "four smoke tests" in narration
    assert (APP / ".runsettings").read_text().count("<TestSessionTimeout>300000</TestSessionTimeout>") == 1
