"""script.yaml against the repo: the header the renderer needs, the length, that every code excerpt that is a source file
is made of real lines of that file, and that the numbers and outputs on screen are the ones the other tests assert."""
from __future__ import annotations

import re

import yaml

from conftest import APP, EPISODE

SCRIPT = yaml.safe_load((EPISODE / "script.yaml").read_text(encoding="utf-8"))
SCENES = {s["id"]: s for s in SCRIPT["scenes"]}
API = "src/Contoso.Orders.Api"
SOURCES = {
    "repro": "tests/Contoso.Orders.Api.Tests/ReportsTests.cs",
    "skip": "scripts/bisect-repro.sh",
    "launch": ".vscode/launch.json",
}


def real_lines(*relative: str) -> set[str]:
    return {line.strip() for rel in relative for line in (APP / rel).read_text(encoding="utf-8").splitlines()}


def test_header_and_shape():
    assert (SCRIPT["episode"], SCRIPT["slug"], SCRIPT["series_label"]) == (9, "debugging-techniques", "DEV TOOLS")
    assert SCRIPT["file_prefix"] == "developer-tools" and SCRIPT["voice"] == "am_michael"
    title = SCRIPT["youtube"]["title"]
    assert len(title) <= 100 and "<" not in title and ">" not in title and title.endswith("| DEVLADLOG Dev Tools #9")
    assert SCRIPT["sources"] == ["https://www.devladlog.com/articles/developer-tools/2025-12-13-debugging-techniques-complete-guide-2025/"]
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
    assert len({s["id"] for s in scenes}) == len(scenes)


def test_code_scenes_are_at_most_16_lines():
    assert all(len(s["code"].rstrip().splitlines()) <= 16 for s in SCRIPT["scenes"] if s["type"] == "code")


def test_source_excerpts_are_real_lines_of_the_real_files():
    for scene_id, rel in SOURCES.items():
        real = real_lines(rel)
        for line in SCENES[scene_id]["code"].splitlines():
            code = line.strip()
            if code and not code.startswith(("//", "#", "...")):
                assert code in real, f"{scene_id}: {code!r} is not in {rel}"


def test_the_fix_scene_shows_the_shipped_code():
    reports, orders = real_lines(f"{API}/Reports.cs"), real_lines(f"{API}/Orders.cs")
    for line in SCENES["fix"]["code"].splitlines():
        code = line.strip()
        if code:
            assert code in reports | orders, code


def test_bisect_scene_matches_what_the_bisect_test_asserts():
    code = SCENES["bisect"]["code"]
    for text in ("git bisect run scripts/bisect-repro.sh", "is the first bad commit",
                 "refactor(reports): compute the last day of the month once", "Reports.cs | 5 ++---"):
        assert text in code
    # the narration says "five lines in one file": 2 insertions + 3 deletions in the patch
    patch = (EPISODE / "bugs/01-month-end-off-by-one.patch").read_text()
    changed = [line for line in patch.splitlines() if re.match(r"[+-][^+-]", line)]
    assert len(changed) == 5 and "five lines in one file" in SCENES["bisect"]["narration"]


def test_repro_numbers_are_the_ones_the_bug_test_asserts():
    assert "Expected: 30" in SCENES["repro"]["code"] and "Actual:   29" in SCENES["repro"]["code"]
    narration = SCENES["repro"]["narration"]
    assert "Expected thirty, actual twenty nine" in narration and "seven of two hundred thirty seven" in narration
    # test_bugs.py asserts Expected: 237 / Actual: 230 for the whole year
    assert 237 - 230 == 7


def test_the_trace_id_gotcha_is_what_the_logging_tests_assert():
    code = SCENES["traceid"]["code"]
    body = re.search(r'"traceId": "(00-([0-9a-f]{32})-[0-9a-f]{16}-01)"', code)
    scope = re.search(r'"TraceId":"([0-9a-f]{32})"', code)
    assert body and scope and body.group(2) == scope.group(1)
    assert body.group(1) in code.split("$ python3 tools/trace_lines.py ")[1]
    assert "Warning     Contoso.Orders.Reports: Rejected month 2026-13: expected yyyy-MM" in code


def test_triage_scene_has_the_two_waiting_methods_and_two_lock_owners():
    code = SCENES["triage"]["code"]
    assert "ReportCache.Invalidate()" in code and "ReportCache.Snapshot()" in code
    assert code.count("Monitor.Enter(") == 2
    owners = re.findall(r"^\s+\d+ [0-9A-F]{16}\s+3\s+1 [0-9A-Fa-f]+ [0-9a-f]+\s+(\d+)$", code, flags=re.M)
    assert len(owners) == 2 and len(set(owners)) == 2
    for method in ("Invalidate", "Snapshot"):
        assert re.search(rf"ReportCache\.{method}\(\) \[Reports\.cs @ \d+\]", code)
