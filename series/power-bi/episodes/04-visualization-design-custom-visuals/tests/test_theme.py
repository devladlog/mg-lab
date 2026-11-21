"""The Contoso Bikes report theme: valid for Power BI Desktop's theme schema and accessible."""
import json
import re

import pytest
from jsonschema import Draft7Validator

import theme_check as tc
from conftest import SCHEMAS, SRC

# Learn's "Set theme colors" example (close to the default palette) - our "before"
LEARN_EXAMPLE = {"name": "Custom Theme", "background": "#FFFFFF",
                 "dataColors": ["#118DFF", "#12239E", "#E66C37", "#6B007B", "#E044A7", "#744EC2",
                                "#D9B300", "#D64550", "#197278", "#1AAB40"],
                 "good": "#1AAB40", "neutral": "#D9B300", "bad": "#D64554"}


def test_theme_matches_the_desktop_theme_schema(theme):
    schema = json.loads((SCHEMAS / "reportThemeSchema-2.159.json").read_text(encoding="utf-8"))
    errors = list(Draft7Validator(schema).iter_errors(theme))
    assert not errors, [e.message for e in errors]


def test_schema_rejects_an_unknown_property(theme):
    schema = json.loads((SCHEMAS / "reportThemeSchema-2.159.json").read_text(encoding="utf-8"))
    bad = {**theme, "dataColours": ["#000000"]}
    assert any("dataColours" in e.message for e in Draft7Validator(schema).iter_errors(bad))


def test_episode_theme_has_no_findings(theme):
    assert tc.check(theme) == []


def test_text_contrast_is_at_least_4_5(theme):
    s = tc.summary(theme)
    assert min(s["text_contrast"].values()) >= 4.5
    assert min(s["data_contrast"]) >= 3.0


def test_learn_example_good_and_bad_collide_for_deuteranopia():
    findings = tc.check(LEARN_EXAMPLE)
    tc003 = [f for f in findings if f["rule"] == "TC003"]
    assert len(tc003) == 1 and "deuteranopia" in tc003[0]["message"]
    assert round(tc.delta_e("#1AAB40", "#D64554", "deuteranopia"), 1) == 5.6
    assert round(tc.delta_e("#1AAB40", "#D64554"), 1) == 74.0          # obvious with normal vision


def test_contrast_ratio_reference_values():
    assert round(tc.contrast("#000000", "#FFFFFF"), 2) == 21.0
    assert round(tc.contrast("#767676", "#FFFFFF"), 2) == 4.54           # the classic 4.5:1 grey
    assert tc.contrast("#FFFFFF", "#FFFFFF") == 1.0


@pytest.mark.parametrize("lab1,lab2,expected", [            # Sharma, Wu, Dalal (2005) test data
    ((50.0, 2.6772, -79.7751), (50.0, 0.0, -82.7485), 2.0425),
    ((50.0, -1.0, 2.0), (50.0, 0.0, 0.0), 2.3669),
    ((50.0, 2.5, 0.0), (73.0, 25.0, -18.0), 27.1492),
    ((2.0776, 0.0795, -1.1350), (0.9033, -0.0636, -0.5514), 0.9082),
])
def test_ciede2000_matches_published_test_data(lab1, lab2, expected):
    assert round(tc.ciede2000(lab1, lab2), 4) == expected


def test_cvd_simulation_keeps_greys_grey():
    for g in ("#000000", "#808080", "#FFFFFF"):
        for kind in tc.CVD:
            assert tc.delta_e(g, tc.simulate(g, kind)) < 1.0


def test_registered_theme_in_the_report_is_the_theme_file():
    a = (SRC / "themes" / "ContosoBikes.json").read_text(encoding="utf-8")
    b = (SRC / "ContosoSales.Report/StaticResources/RegisteredResources/ContosoBikes.json").read_text(encoding="utf-8")
    assert a == b


def test_custom_visual_defaults_are_the_theme_sentiment_colours(theme):
    ts = (SRC / "target-bullet/src/settings.ts").read_text(encoding="utf-8")
    defaults = dict(re.findall(r'export const DEFAULT_(\w+) = "(#[0-9A-F]{6})"', ts))
    assert defaults == {"ABOVE": theme["good"], "NEAR": theme["neutral"], "BELOW": theme["bad"]}
    assert all(tc.contrast(c, theme["background"]) >= 3.0 for c in defaults.values())
