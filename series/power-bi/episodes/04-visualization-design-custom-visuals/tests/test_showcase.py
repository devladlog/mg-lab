"""The Showcase page (1280 x 720, 24 px grid) and the Contoso Night Ride theme it is shown with."""
import json

import pytest
from jsonschema import Draft7Validator

import build_report as br
import report_lint as rl
import theme_check as tc
from conftest import SCHEMAS, SRC, schema_errors

REPORT = SRC / "ContosoSales.Report"
PAGE = REPORT / "definition" / "pages" / "showcase"
MODEL = SRC / "ContosoSales.SemanticModel" / "definition"
NIGHT_RIDE = SRC / "themes" / "ContosoNightRide.json"
THEME_SCHEMA = SCHEMAS / "reportThemeSchema-2.159.json"
PBIVIZ = json.loads((SRC / "target-bullet" / "pbiviz.json").read_text(encoding="utf-8"))
CAPABILITIES = json.loads((SRC / "target-bullet" / "capabilities.json").read_text(encoding="utf-8"))
GUID = PBIVIZ["visual"]["guid"]


def visuals():
    return {vf.parent.name: json.loads(vf.read_text(encoding="utf-8")) for vf in sorted(PAGE.glob("visuals/*/visual.json"))}


@pytest.fixture(scope="module")
def night_ride():
    return json.loads(NIGHT_RIDE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def theme_schema():
    if not THEME_SCHEMA.exists():
        pytest.skip("theme schema not vendored (run tests/schemas/fetch_schemas.py)")
    return json.loads(THEME_SCHEMA.read_text(encoding="utf-8"))


# ---- the page --------------------------------------------------------------------------------------------------

def test_showcase_page_parses_has_the_overview_size_and_comes_second():
    page = json.loads((PAGE / "page.json").read_text(encoding="utf-8"))
    overview = json.loads((REPORT / "definition/pages/overview/page.json").read_text(encoding="utf-8"))
    assert (page["name"], page["displayName"]) == ("showcase", "Showcase")
    assert (page["width"], page["height"]) == (overview["width"], overview["height"]) == (1280, 720)
    assert not schema_errors(page)
    order = json.loads((REPORT / "definition/pages/pages.json").read_text(encoding="utf-8"))
    assert order["pageOrder"] == ["overview", "showcase"]
    assert order["activePageName"] == "overview"          # the report still opens on Sales overview


def test_every_showcase_visual_matches_its_schema():
    vs = visuals()
    assert vs
    for name, v in vs.items():
        assert not schema_errors(v), name


def test_showcase_has_the_planned_visuals():
    types = {name: v["visual"]["visualType"] for name, v in visuals().items()}
    assert types == {"scHeader": "textbox", "scYear": "slicer", "scSales": "card", "scGrowth": "card",
                     "scOrders": "card", "scUnits": "card", "scBullet": GUID, "scTrend": "lineChart",
                     "scCategory": "clusteredBarChart", "scProducts": "tableEx"}


def test_showcase_uses_only_visual_types_the_overview_or_the_episode_already_uses():
    known = {json.loads(vf.read_text())["visual"]["visualType"]
             for vf in REPORT.glob("definition/pages/overview/visuals/*/visual.json")} | {GUID, "textbox"}
    assert {v["visual"]["visualType"] for v in visuals().values()} <= known


def test_showcase_binds_only_to_fields_in_the_model():
    fields = rl.model_fields(MODEL)
    used = {ref for v in visuals().values() for ref in rl.field_refs(v["visual"].get("query", {}))}
    missing = sorted(f"'{t}'[{p}]" for t, p in used if p not in fields.get(t, set()))
    assert not missing
    assert used == {("Sales", "Sales Amount"), ("Sales", "Sales YoY %"), ("Sales", "Orders"), ("Sales", "Units"),
                    ("Sales", "Sales PY"), ("Sales", "Product Rank"), ("Date", "Year"), ("Date", "Month"),
                    ("Product", "Category"), ("Product", "Product")}


def test_target_bullet_uses_the_packaged_visual_and_the_sales_overview_binding():
    v = visuals()["scBullet"]["visual"]
    roles = {r["name"] for r in CAPABILITIES["dataRoles"]}
    assert set(v["query"]["queryState"]) == roles
    bound = {role: [p["field"][k]["Property"] for p in s["projections"] for k in ("Column", "Measure") if k in p["field"]]
             for role, s in v["query"]["queryState"].items()}
    assert bound == {"category": ["Category"], "actual": ["Sales Amount"], "target": ["Sales PY"]}   # demo.md step 5


def test_showcase_sits_on_a_24_px_grid_inside_the_page_without_overlaps():
    boxes = {name: v["position"] for name, v in visuals().items()}
    for name, p in boxes.items():
        assert all(p[k] % 24 == 0 for k in ("x", "y", "width", "height")), name
        assert p["x"] >= 24 and p["x"] + p["width"] <= 1280 - 24, name
        assert p["y"] >= 24 and p["y"] + p["height"] <= 720 - 24, name
    assert max(p["x"] + p["width"] for p in boxes.values()) == br.SC_UNIT + br.SC_COLS * (br.SC_COL + br.SC_UNIT) - 24
    assert max(p["y"] + p["height"] for p in boxes.values()) == 720 - 24


def test_showcase_is_lint_clean_and_uses_no_hard_coded_colours():
    assert [f for f in rl.lint(REPORT, MODEL) if f["where"].startswith("showcase")] == []
    assert not rl.HEX.search(json.dumps([v["visual"] for v in visuals().values()]))
    runs = [r for p in visuals()["scHeader"]["visual"]["objects"]["general"][0]["properties"]["paragraphs"]
            for r in p["textRuns"]]
    assert runs and all("color" not in r["textStyle"] for r in runs)        # the theme's text colour applies


def test_every_showcase_visual_has_alt_text_and_tab_order_in_reading_order():
    vs = list(visuals().values())
    for v in vs:
        alt = rl.literal_text(v["visual"]["visualContainerObjects"], "general", "altText")
        assert alt and len(alt) <= 250
    reading = [v["name"] for v in sorted(vs, key=lambda v: (v["position"]["y"], v["position"]["x"]))]
    tabbing = [v["name"] for v in sorted(vs, key=lambda v: v["position"]["tabOrder"])]
    assert reading == tabbing


def test_tile_slicer_value_is_the_documented_tile_style(theme_schema):
    mode = visuals()["scYear"]["visual"]["objects"]["data"][0]["properties"]["mode"]["expr"]["Literal"]["Value"]
    assert mode == "'HorizontalList'"
    assert '{"const": "HorizontalList", "title": "Tile"}' in json.dumps(theme_schema["definitions"]["visual-slicer"])


# ---- the Contoso Night Ride theme --------------------------------------------------------------------------------

def test_night_ride_matches_the_desktop_theme_schema(night_ride, theme_schema):
    errors = list(Draft7Validator(theme_schema).iter_errors(night_ride))
    assert not errors, [e.message for e in errors]


def test_night_ride_schema_still_rejects_a_misspelled_top_level_property(night_ride, theme_schema):
    assert list(Draft7Validator(theme_schema).iter_errors({**night_ride, "backgroundColour": "#000000"}))


def _theme_properties(schema, visual):
    """{object: {property names}} the theme schema documents for one visual type (allOf and $ref resolved)."""
    defs = schema["definitions"]

    def resolve(node):
        while isinstance(node, dict) and "$ref" in node:
            node = defs[node["$ref"].split("/")[-1]]
        return node

    def props(node, out):
        node = resolve(node)
        out.update(node.get("properties", {}))
        for part in node.get("allOf", []):
            props(part, out)
        return out

    objects = props(schema["properties"]["visualStyles"]["properties"][visual]["properties"]["*"], {})
    return {name: set(props(resolve(o).get("items", {}), {})) for name, o in objects.items()}


def test_night_ride_uses_only_properties_the_theme_schema_documents(night_ride, theme_schema):
    # the schema itself lets an unknown property inside a visual style through (README: the 'positon' gotcha)
    unknown = []
    for visual, styles in night_ride["visualStyles"].items():
        known = _theme_properties(theme_schema, "card" if visual == "*" else visual)
        for obj, entries in styles["*"].items():
            for entry in entries:
                unknown += [f"{visual}.{obj}.{p}" for p in entry if p not in known.get(obj, set())]
    assert unknown == []


def test_night_ride_has_no_theme_check_findings(night_ride):
    assert tc.check(night_ride) == []


def test_night_ride_is_dark_and_every_colour_passes_aa_on_it(night_ride):
    bg = night_ride["background"]
    assert tc.luminance(bg) < 0.02                          # a dark theme
    assert min(tc.summary(night_ride)["text_contrast"].values()) >= 4.5     # WCAG AA text
    for c in night_ride["dataColors"] + [night_ride[k] for k in ("good", "neutral", "bad")]:
        assert tc.contrast(c, bg) >= 4.5, c                   # stricter than the 3:1 for graphics: data labels too
    page_bg = night_ride["visualStyles"]["page"]["*"]["background"][0]["color"]["solid"]["color"]
    assert tc.contrast(night_ride["foreground"], page_bg) >= 4.5    # the headline textbox has no background


def test_night_ride_leaves_the_custom_visual_alone(night_ride):
    # Target bullet draws its bars on a fixed light lane, so its default (dark) band colours stay; the theme
    # doesn't restyle the recorded visual
    assert GUID not in night_ride["visualStyles"]


def test_night_ride_is_not_registered_in_the_report():
    # the episode report keeps Contoso Bikes; Night Ride is imported in Desktop in the showcase scene
    report = json.loads((REPORT / "definition/report.json").read_text(encoding="utf-8"))
    assert report["themeCollection"]["customTheme"]["name"] == "ContosoBikes.json"
    assert not (REPORT / "StaticResources/RegisteredResources/ContosoNightRide.json").exists()
