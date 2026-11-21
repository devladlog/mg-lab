"""The draft script must match the repository: excerpts come from real files, shape follows the brief."""
import re
from pathlib import Path

import yaml

EP = Path(__file__).resolve().parents[1]
SCRIPT = yaml.safe_load((EP / "script.yaml").read_text(encoding="utf-8"))


def _corpus() -> str:
    parts = []
    for p in (EP / "src").rglob("*"):
        if p.is_file() and p.suffix in {".py", ".cs", ".md", ".yml", ".yaml", ".patch", ".csproj"} and "bin" not in p.parts and "obj" not in p.parts:
            parts.append(p.read_text(encoding="utf-8"))
    return "\n".join(parts)


def test_header_fields():
    for key in ("episode", "slug", "series_label", "series_name", "file_prefix", "title", "subtitle", "voice", "thumbnail_text", "youtube", "sources"):
        assert key in SCRIPT, key
    assert SCRIPT["series_label"] == "COPILOT & AI" and SCRIPT["series_name"] == "DEVLADLOG Copilot & AI"
    yt = SCRIPT["youtube"]["title"]
    assert len(yt) <= 100 and "<" not in yt and ">" not in yt and yt.endswith(f"| DEVLADLOG Copilot & AI #{SCRIPT['episode']}")
    assert EP.name.endswith(SCRIPT["slug"])


def test_scene_shape():
    scenes = SCRIPT["scenes"]
    assert 12 <= len(scenes) <= 16
    assert scenes[0]["type"] == "title" and scenes[0].get("short") == "hook"
    assert scenes[-1]["type"] == "outro" and scenes[-1]["heading"] == "Code on GitHub, guides on devladlog.com" and scenes[-1]["sub"] == "github.com/devladlog/mg-lab"
    assert sum(1 for s in scenes if s.get("short")) == 3
    screens = [s for s in scenes if s["type"] == "screen"]
    assert 3 <= len(screens) <= 5
    for s in screens:
        assert s["image"].startswith("screens/") and s["bar"] and s["demo"]
    ids = [s["id"] for s in scenes]
    assert len(ids) == len(set(ids))


def test_narration_length_and_plain_text():
    words = sum(len(s["narration"].split()) for s in SCRIPT["scenes"])
    assert 700 <= words <= 950, words
    for s in SCRIPT["scenes"]:
        assert not re.search(r"[*_`#|<>]", s["narration"]), s["id"]


def test_code_excerpts_are_short_and_real():
    corpus = _corpus()
    corpus_lines = {ln.strip() for ln in corpus.splitlines()}
    for s in SCRIPT["scenes"]:
        if s["type"] != "code" or s.get("lang") == "bash":
            continue
        lines = s["code"].rstrip("\n").splitlines()
        assert len(lines) <= 16, s["id"]
        for ln in lines:
            if ln.strip():
                assert ln.strip() in corpus_lines, f"{s['id']}: not found in src: {ln!r}"
