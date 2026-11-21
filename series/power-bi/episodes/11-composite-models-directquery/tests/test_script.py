import re

import yaml

from conftest import EP, SRC

SCRIPT = yaml.safe_load((EP / "script.yaml").read_text(encoding="utf-8"))
SCENES = SCRIPT["scenes"]


def test_header():
    for k in ("episode", "slug", "series_label", "series_name", "file_prefix", "title", "subtitle", "voice", "thumbnail_text", "youtube", "sources"):
        assert k in SCRIPT
    assert SCRIPT["series_name"] == "DEVLADLOG Power BI" and SCRIPT["file_prefix"] == "power-bi" and SCRIPT["voice"] == "am_michael"
    y = SCRIPT["youtube"]["title"]
    assert y.endswith("| DEVLADLOG Power BI #11") and len(y) <= 100 and "<" not in y and ">" not in y
    assert SCRIPT["sources"][0].startswith("https://www.devladlog.com/articles/power-bi/2026-03-31-composite-models")


def test_scene_mix_and_narration_length():
    assert 12 <= len(SCENES) <= 16
    words = sum(len(s["narration"].split()) for s in SCENES)
    assert 750 <= words <= 900, words
    assert SCENES[0]["type"] == "title" and SCENES[-1]["type"] == "outro"
    assert SCENES[-1]["heading"] == "Code on GitHub, guides on devladlog.com" and SCENES[-1]["sub"] == "github.com/devladlog/mg-lab"
    screens = [s for s in SCENES if s["type"] == "screen"]
    assert 3 <= len(screens) <= 5
    assert all(s["image"].startswith("screens/") and s["bar"] and s["demo"] for s in screens)
    shorts = [s for s in SCENES if "short" in s]
    assert len(shorts) == 3 and any(s["id"] == "gotcha" for s in shorts)
    for s in SCENES:
        assert not re.search(r"[*#`]|[^\x00-ɏ’]", s["narration"]), s["id"]


def test_code_scenes_are_short_and_come_from_the_source_files():
    corpus = ""
    for p in SRC.rglob("*"):
        if p.is_file() and p.suffix in {".tmdl", ".sql", ".dax", ".cs", ".py", ".json"} and "bin" not in p.parts and "obj" not in p.parts and "data" not in p.parts:
            corpus += "\n".join(l.strip() for l in p.read_text(encoding="utf-8").splitlines()) + "\n"
    for s in SCENES:
        if s["type"] != "code":
            continue
        lines = [l for l in s["code"].splitlines() if l.strip()]
        assert len(lines) <= 16, s["id"]
        for l in lines:
            assert l.strip() in corpus, f"{s['id']}: not found in src: {l.strip()}"


def test_demo_md_covers_every_screen_scene():
    demo = (EP / "demo.md").read_text(encoding="utf-8")
    assert demo.startswith("# ") and "## Lab environment" in demo
    for s in SCENES:
        if s["type"] == "screen":
            assert f"`{s['id']}`" in demo and s["image"] in demo, s["id"]
    low = demo.lower()
    assert "needs tenant" in low and "mask" in low and "tear" in low


def test_no_real_names_or_ids_anywhere():
    files = list(EP.rglob("*.md")) + [EP / "script.yaml"] + [p for p in SRC.rglob("*") if p.suffix in {".tmdl", ".sql", ".dax", ".pbip", ".pbir", ".pbism"}]
    for p in files:
        text = p.read_text(encoding="utf-8")
        for g in re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", text):
            assert g.startswith("00000000-0000-0000-0000-0000"), f"{p.name}: {g}"
        assert not re.search(r"devladlog (tenant|workspace)", text, re.I)
