"""The two PBIR reports: schema-valid, lint-clean against their model, and the before page really is the heavy one."""
import json
import subprocess
import sys

import pytest

import report_lint as rl
from conftest import AFTER, AFTER_REPORT, BEFORE, BEFORE_REPORT, SRC, schema_errors


def pbir_files(report):
    return sorted(p for p in report.rglob("*.json") if "StaticResources" not in p.parts)


ALL_JSON = pbir_files(BEFORE_REPORT) + pbir_files(AFTER_REPORT) + [
    SRC / "ContosoPerf.Before.pbip", SRC / "ContosoPerf.After.pbip",
    SRC / "ContosoPerf.Before.SemanticModel/definition.pbism", SRC / "ContosoPerf.After.SemanticModel/definition.pbism"]


def test_reports_match_the_layout_spec():
    r = subprocess.run([sys.executable, str(SRC / "tools" / "build_report.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout


@pytest.mark.parametrize("path", ALL_JSON, ids=lambda p: str(p.relative_to(SRC)))
def test_file_matches_its_published_schema(path):
    errors = schema_errors(json.loads(path.read_text(encoding="utf-8")))
    assert not errors, [e.message for e in errors]


def test_each_report_is_bound_to_the_model_next_to_it():
    for report, model in ((BEFORE_REPORT, "Before"), (AFTER_REPORT, "After")):
        d = json.loads((report / "definition.pbir").read_text(encoding="utf-8"))
        assert d["datasetReference"] == {"byPath": {"path": f"../ContosoPerf.{model}.SemanticModel"}}
    for model in ("Before", "After"):
        pbip = json.loads((SRC / f"ContosoPerf.{model}.pbip").read_text(encoding="utf-8"))
        assert pbip["artifacts"][0]["report"]["path"] == f"ContosoPerf.{model}.Report"


def test_after_report_is_lint_clean_and_before_only_breaks_the_page_limit():
    assert rl.lint(AFTER_REPORT, AFTER) == []
    assert [f["rule"] for f in rl.lint(BEFORE_REPORT, BEFORE)] == ["RL009"]


def test_the_reports_ask_the_same_questions():
    """Every field the after report uses is a field the before report uses too (the answers stay comparable)."""
    def fields(report):
        out = set()
        for vf in report.rglob("visual.json"):
            out |= set(rl.field_refs(json.loads(vf.read_text(encoding="utf-8"))["visual"]["query"]))
        return out
    only_after = fields(AFTER_REPORT) - fields(BEFORE_REPORT)
    assert only_after <= {("Date", "Date")}                      # the order lines page shows the date, not the timestamp


def test_the_heavy_visual_is_on_the_executive_page_before_and_on_its_own_page_after():
    pages = lambda r: {p.parent.name: len(list((p.parent / "visuals").glob("*/visual.json")))
                       for p in (r / "definition" / "pages").glob("*/page.json")}
    assert pages(BEFORE_REPORT) == {"executive": 13}
    assert pages(AFTER_REPORT) == {"executive": 7, "lines": 2}
    assert (BEFORE_REPORT / "definition/pages/executive/visuals/tableLines").exists()
    assert not (AFTER_REPORT / "definition/pages/executive/visuals/tableLines").exists()
