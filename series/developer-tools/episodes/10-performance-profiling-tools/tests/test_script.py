"""script.yaml against the repo: the header the renderer needs, the length, that every code excerpt is made of real lines of
real files, and that the numbers on screen are the ones the fixture and the other tests produce."""
from __future__ import annotations

import json
import re

import yaml

import counters_summary
from conftest import APP, BUGS, EPISODE, TESTS

SCRIPT = yaml.safe_load((EPISODE / "script.yaml").read_text(encoding="utf-8"))
SCENES = {s["id"]: s for s in SCRIPT["scenes"]}
API = "src/Contoso.Orders.Api"


def real_lines(*relative: str) -> set[str]:
    return {line.strip() for rel in relative for line in (APP / rel).read_text(encoding="utf-8").splitlines()}


def patch_added_lines() -> set[str]:
    return {line[1:].strip() for line in (BUGS / "01-load-everything.patch").read_text().splitlines()
            if line[:1] in "+ " and not line.startswith("+++")}


def test_header_and_shape():
    assert (SCRIPT["episode"], SCRIPT["slug"], SCRIPT["series_label"]) == (10, "performance-profiling-tools", "DEV TOOLS")
    assert SCRIPT["series_name"] == "DEVLADLOG Dev Tools" and SCRIPT["file_prefix"] == "developer-tools" and SCRIPT["voice"] == "am_michael"
    title = SCRIPT["youtube"]["title"]
    assert len(title) <= 100 and "<" not in title and ">" not in title and title.endswith("| DEVLADLOG Dev Tools #10")
    assert SCRIPT["sources"] == ["https://www.devladlog.com/articles/developer-tools/2025-12-20-performance-profiling-tools-complete-guide-2025/"]
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
    assert sum(1 for s in scenes if "gotcha" in s.get("heading", "").lower()) == 1


def test_code_scenes_are_at_most_16_lines():
    assert all(len(s["code"].rstrip().splitlines()) <= 16 for s in SCRIPT["scenes"] if s["type"] == "code")


def test_before_scene_is_the_patch_and_after_scene_is_the_shipped_code():
    added = patch_added_lines()
    for line in SCENES["before"]["code"].splitlines():
        assert line.strip() in added, line
    reports = real_lines(f"{API}/Reports.cs")
    for line in SCENES["fix"]["code"].splitlines():
        assert line.strip() in reports, line


def test_guard_scene_is_made_of_real_test_lines():
    real = real_lines("tests/Contoso.Orders.Api.Tests/ReportPerformanceTests.cs")
    for line in SCENES["guard"]["code"].splitlines():
        if line.strip() and not line.strip().startswith("..."):
            assert line.strip() in real, line


def test_counters_scene_is_what_the_summary_tool_prints_for_the_fixture():
    doc = json.loads((TESTS / "fixtures" / "counters-slow.json").read_text())
    s = counters_summary.summarize(doc)
    code = SCENES["countersout"]["code"]
    assert (f"window {s['seconds']} s: CPU {s['cpu_s']} s, allocated {s['allocated_mb']} MB ({s['alloc_mb_per_s']} MB/s), "
            f"GC pause {s['gc_pause_s']} s, collections gen0/gen1/gen2 {s['gen0']}/{s['gen1']}/{s['gen2']}, "
            f"working set max {s['working_set_mb']} MB") in code
    assert f"server-side p50 about {s['request_p50_ms']} ms, worst p95 {s['request_p95_ms']} ms" in code
    narration = SCENES["countersout"]["narration"]
    assert "more than eight hundred megabytes" in narration and "five and a half seconds" in narration


def test_result_table_and_narration_agree():
    code, narration = SCENES["result"]["code"], SCENES["result"]["narration"]
    assert "1846 ms   2908 ms" in code and "20 ms     50 ms" in code and "128 ms    271 ms" in code
    assert "one hundred twenty eight" in narration and "gives twenty" in narration
    assert "one point eight seconds" in SCENES["load"]["narration"] and "1846 ms" in SCENES["load"]["code"]
    assert "twenty milliseconds" in SCENES["after"]["narration"] and "ninety times" in SCENES["after"]["narration"]
    assert 1846 / 20 > 90 * 0.9           # "about ninety times faster at the median"


def test_the_gotcha_says_what_the_trace_said():
    code = SCENES["hunch"]["code"]
    assert "Busy thread time in the trace: 31.5 s" in code
    assert "84.2%  EntityFrameworkCore.EntityFrameworkQueryableExtensions.ToListAsync" in code
    assert "0.1%  System.DateOnly.ToString" in code
    narration = SCENES["hunch"]["narration"]
    assert "Eighty four percent" in narration and "a tenth of a percent" in narration


def test_the_allocation_numbers_in_the_guard_narration_match_the_test_budget():
    narration = SCENES["guard"]["narration"]
    source = (APP / "tests/Contoso.Orders.Api.Tests/ReportPerformanceTests.cs").read_text()
    assert "AllocationBudgetBytes = 1_000_000" in source and "budget of one megabyte" in narration
