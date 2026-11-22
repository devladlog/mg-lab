"""The PBIR report: generated from the layout spec, valid against Microsoft's schemas, and lint-clean."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

import report_lint as rl
from conftest import ROOT, SRC, schema_errors

REPORT = SRC / "ContosoSales.Report"
MODEL = SRC / "ContosoSales.SemanticModel" / "definition"
MESSY = ROOT / "tests" / "fixtures" / "messy-report"
PBIR_FILES = sorted(p for p in REPORT.rglob("*.json") if "StaticResources" not in p.parts)


def test_report_matches_the_layout_spec():
    r = subprocess.run([sys.executable, str(SRC / "tools" / "build_report.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout


@pytest.mark.parametrize("path", PBIR_FILES + [SRC / "ContosoSales.pbip", SRC / "ContosoSales.SemanticModel/definition.pbism"],
                         ids=lambda p: str(p.relative_to(SRC)))
def test_file_matches_its_published_schema(path):
    errors = schema_errors(json.loads(path.read_text(encoding="utf-8")))
    assert not errors, [e.message for e in errors]


def test_schema_catches_a_broken_field_reference():
    doc = json.loads((REPORT / "definition/pages/overview/visuals/kpiSales/visual.json").read_text())
    del doc["visual"]["query"]["queryState"]["Values"]["projections"][0]["field"]["Measure"]["Property"]
    assert schema_errors(doc)


def test_messy_fixture_is_schema_valid_but_badly_designed():
    for p in MESSY.rglob("*.json"):
        assert not schema_errors(json.loads(p.read_text())), p
    rules = sorted({f["rule"] for f in rl.lint(MESSY, MODEL, max_visuals=2)})
    assert rules == [f"RL{n:03d}" for n in range(1, 11)]


def test_episode_report_has_no_findings():
    assert rl.lint(REPORT, MODEL) == []


def test_every_data_visual_has_alt_text_title_and_tab_order():
    for vf in REPORT.glob("definition/pages/*/visuals/*/visual.json"):
        v = json.loads(vf.read_text())
        objs = v["visual"]["visualContainerObjects"]
        alt = rl.literal_text(objs, "general", "altText")
        assert alt and len(alt) <= 250
        assert rl.literal_text(objs, "title", "text")
        assert "tabOrder" in v["position"]


def test_layout_is_a_12_column_grid_with_room_for_the_custom_visual():
    boxes = [json.loads(vf.read_text())["position"] for vf in REPORT.glob("definition/pages/overview/visuals/*/visual.json")]
    assert len(boxes) == 7
    assert {b["x"] for b in boxes} <= {24 + 104 * c for c in range(12)}
    free = {"x": 24 + 104 * 6, "y": 432, "width": 6 * 104 - 16, "height": 264}
    for b in boxes:
        assert not (b["x"] < free["x"] + free["width"] and free["x"] < b["x"] + b["width"]
                    and b["y"] < free["y"] + free["height"] and free["y"] < b["y"] + b["height"])


def test_report_registers_the_custom_theme():
    report = json.loads((REPORT / "definition/report.json").read_text())
    assert report["themeCollection"]["customTheme"]["name"] == "ContosoBikes.json"
    items = [i for p in report["resourcePackages"] for i in p["items"]]
    assert {"name": "ContosoBikes.json", "path": "ContosoBikes.json", "type": "CustomTheme"} in items
    assert (REPORT / "StaticResources/RegisteredResources/ContosoBikes.json").exists()


def test_report_points_to_the_semantic_model_by_relative_path():
    pbir = json.loads((REPORT / "definition.pbir").read_text())
    target = (REPORT / pbir["datasetReference"]["byPath"]["path"]).resolve()
    assert (target / "definition" / "model.tmdl").exists()
