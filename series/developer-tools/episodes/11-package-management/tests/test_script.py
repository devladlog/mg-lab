"""script.yaml against the repository: the header the renderer needs, the length, that every configuration excerpt on
screen is a real line of a real file, and that the output and numbers on screen are the ones the other tests assert."""

from __future__ import annotations

import re
import subprocess
import sys

import yaml
from conftest import APP, CONSUMER, EPISODE, FIXTURES

SCRIPT = yaml.safe_load((EPISODE / "script.yaml").read_text(encoding="utf-8"))
SCENES = {s["id"]: s for s in SCRIPT["scenes"]}
# scene id -> files its configuration lines come from
SOURCES = {
    "cpm": ["Directory.Packages.props", "tests/Contoso.Orders.Api.Tests/Contoso.Orders.Api.Tests.csproj"],
    "audit-props": ["Directory.Build.props"],
    "pipeline": ["azure-pipelines.yml"],
}


def test_header_and_shape():
    assert (SCRIPT["episode"], SCRIPT["slug"], SCRIPT["series_label"]) == (11, "package-management", "DEV TOOLS")
    assert SCRIPT["file_prefix"] == "developer-tools" and SCRIPT["voice"] == "am_michael"
    title = SCRIPT["youtube"]["title"]
    assert len(title) <= 100 and "<" not in title and ">" not in title and title.endswith("| DEVLADLOG Dev Tools #11")
    assert SCRIPT["sources"] == [
        "https://www.devladlog.com/articles/developer-tools/2025-12-31-package-management-complete-guide-2025/"]
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
        real = {line.strip() for rel in rels for line in (APP / rel).read_text(encoding="utf-8").splitlines()}
        for line in SCENES[scene_id]["code"].splitlines():
            code = line.strip()
            if code and not code.startswith(("#", "<!--")):
                assert code in real, f"{scene_id}: {code!r} is not in {rels}"


def test_mapping_excerpt_is_the_shipped_consumer_config():
    real = {line.strip() for line in (CONSUMER / "nuget.config").read_text(encoding="utf-8").splitlines()}
    for line in SCENES["mapping"]["code"].splitlines():
        assert line.strip() in real, line


def test_the_fix_scene_shows_what_the_tool_prints_and_the_pin_the_tests_apply():
    code = SCENES["fix"]["code"]
    saved = FIXTURES / "dotnet-package-list-vuln.json"
    out = subprocess.run([sys.executable, str(APP / "tools" / "pkg_audit.py"), "--from-json", str(saved)],
                         capture_output=True, text=True, check=False).stdout
    assert "1 known vulnerabilities (1 at high or above):" in out and "1 known vulnerabilities (1 at high or above):" in code
    assert "HIGH  Newtonsoft.Json 10.0.1 in Contoso.Orders.LegacyClient" in code
    assert "https://github.com/advisories/GHSA-5crp-9r3c-p9vr" in code and "No known vulnerabilities in the packages NuGet resolved." in code
    assert '<PackageVersion Include="Newtonsoft.Json" Version="13.0.4" />' in code
    assert 'Label="Pinned transitive packages"' in code


def test_the_gotcha_and_the_hash_error_are_the_messages_the_tests_assert():
    tests = (EPISODE / "tests" / "test_feeds_and_mapping.py").read_text() + (EPISODE / "tests" / "test_pip_hashes.py").read_text()
    for text in ("NU1403", "Package content hash validation failed for Contoso.Orders.Contracts.1.0.0",
                 "THESE PACKAGES DO NOT MATCH THE HASHES FROM THE REQUIREMENTS FILE"):
        assert text in tests
    assert "error NU1403: Package content hash validation failed for Contoso.Orders.Contracts.1.0.0." in SCENES["gotcha"]["code"]
    assert "THESE PACKAGES DO NOT MATCH THE HASHES FROM THE REQUIREMENTS FILE." in SCENES["pip"]["code"]
    assert "ruff==0.16.9" in SCENES["pip"]["code"] and "ruff-0.16.9" in SCENES["pip"]["code"]


def test_versions_named_on_screen_are_the_ones_in_the_repository():
    props = (APP / "Directory.Packages.props").read_text()
    assert 'Include="xunit" Version="2.9.3"' in props and 'Include="Microsoft.EntityFrameworkCore.Sqlite" Version="10.0.15"' in props
    assert "<VersionPrefix>1.0.0</VersionPrefix>" in (APP / "src/Contoso.Orders.Contracts/Contoso.Orders.Contracts.csproj").read_text()
