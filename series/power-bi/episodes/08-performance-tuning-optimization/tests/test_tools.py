"""perf-compare, the DAX query files, and the repository rules (no real names, no GUIDs, small)."""
import re
import subprocess
import sys

import pytest

import perf_compare as pc
from conftest import ROOT, SRC

SKIP_DIRS = {"node_modules", "dist", "bin", "obj", "__pycache__", ".pytest_cache", "schemas"}


def files():
    return [p for p in ROOT.rglob("*") if p.is_file() and not (set(p.relative_to(ROOT).parts) & SKIP_DIRS)]


def test_compare_ratios_and_problems():
    rows = [{"page": "p", "visual": "a", "before_ms": "1200", "after_ms": "300"},
            {"page": "p", "visual": "b", "before_ms": "50", "after_ms": "100"},
            {"page": "p", "visual": "c", "before_ms": "70", "after_ms": ""},
            {"page": "p", "visual": "d", "before_ms": "x", "after_ms": "1"}]
    out, problems = pc.compare(rows)
    assert [r[4] for r in out] == [4.0, 0.5, None]
    assert problems == ["p/b: slower after (50 ms -> 100 ms)", "p/d: not a number: 'x'"]


def test_compare_cli(tmp_path):
    f = tmp_path / "r.csv"
    f.write_text("page,visual,before_ms,after_ms\nexecutive,a,900,300\nexecutive,b,100,50\n", encoding="utf-8")
    r = subprocess.run([sys.executable, str(SRC / "tools" / "perf_compare.py"), str(f)], capture_output=True, text=True)
    assert r.returncode == 0 and "3.0x" in r.stdout and "2.0x" in r.stdout and "total" in r.stdout
    f.write_text("page,visual,before_ms,after_ms\nexecutive,a,100,300\n", encoding="utf-8")
    r = subprocess.run([sys.executable, str(SRC / "tools" / "perf_compare.py"), str(f)], capture_output=True, text=True)
    assert r.returncode == 1 and "slower after" in r.stdout


def test_the_template_lists_the_after_executive_visuals_and_is_empty():
    rows = pc.load(SRC / "results" / "performance-analyzer.template.csv")
    assert all(not r["before_ms"] and not r["after_ms"] for r in rows)     # numbers come from the real recording
    out, problems = pc.compare(rows)
    assert problems == [] and all(r[4] is None for r in out)
    visuals = {r["visual"] for r in rows}
    import glob
    before = {p.split("/")[-2] for p in glob.glob(str(SRC / "ContosoPerf.Before.Report/definition/pages/executive/visuals/*/visual.json"))}
    assert visuals <= before                                               # a before number exists for every row


@pytest.mark.parametrize("path", sorted((SRC / "queries").glob("*.dax")), ids=lambda p: p.name)
def test_dax_queries_are_marked_as_not_run_here_and_well_formed(path):
    text = path.read_text(encoding="utf-8")
    assert text.startswith("// NEEDS POWER BI DESKTOP")
    body = "\n".join(l for l in text.splitlines() if not l.startswith("//"))
    assert body.count("EVALUATE") >= 1 and body.count("(") == body.count(")")
    assert "DEFINE" not in body or body.index("DEFINE") < body.index("EVALUATE")


def test_dax_query_measures_exist_in_the_model():
    import perf_lint as pl
    from conftest import AFTER
    model = pl.read_model(AFTER)
    measures = {m["name"] for t in model.values() for m in t["measures"]}
    columns = {(t["name"], c["name"]) for t in model.values() for c in t["columns"]}
    for q in (SRC / "queries").glob("0[2-5]*.dax"):   # 04/05: DAX Studio Server Timings pair
        text = q.read_text(encoding="utf-8")
        for m in re.findall(r"(?<![\w'\]])\[([^\]]+)\]", re.sub(r'"[^"]*"', "", text)):
            assert m in measures or m == "Online Sales Filter" or m == "YoY Twice" or m in {c for _, c in columns}, m
        for tbl, col in re.findall(r"'([^']+)'\[([^\]]+)\]", text):
            assert (tbl, col) in columns, (tbl, col)


def test_no_real_names_and_no_guids():
    bad = re.compile(r"devladlog|momento|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
    for p in files():
        if p.suffix in {".csv", ".png", ".jpg"} or p.name == "test_tools.py":
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        if p.name in {"README.md", "script.yaml", "demo.md", "social.yaml"}:  # the blog URL and brand are references by design
            text = text.replace("https://www.devladlog.com/articles/power-bi/2025-07-09-performance-tuning-complete-guide-2025/", "")
            text = text.replace("devladlog/mg-lab", "").replace("devladlog.com", "").replace("DEVLADLOG", "").replace("Momento Galático", "")
        assert not bad.search(text), p.relative_to(ROOT)


def test_folder_stays_small():
    assert sum(p.stat().st_size for p in files()) < 5_000_000
