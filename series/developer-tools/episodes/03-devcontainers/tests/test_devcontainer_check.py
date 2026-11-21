"""tools/devcontainer_check.py against responses recorded from mcr.microsoft.com (and live, with ONLINE=1)."""
import json
import os

import pytest

from conftest import APP, dc


@pytest.mark.parametrize("text,expected", [
    ('{"a": "https://x"} // c', {"a": "https://x"}),
    ('{"a": 1, /* b */ "b": [1, 2,],}', {"a": 1, "b": [1, 2]}),
    ('{"a": "// not a comment", "b": "x,]"}', {"a": "// not a comment", "b": "x,]"}),
    ('{"a": "quote \\" // still string"}', {"a": 'quote " // still string'}),
])
def test_strip_jsonc(text, expected):
    assert json.loads(dc.strip_jsonc(text)) == expected


@pytest.mark.parametrize("ref,registry,repo,tag", [
    ("mcr.microsoft.com/devcontainers/dotnet:3-10.0-noble", "mcr.microsoft.com", "devcontainers/dotnet", "3-10.0-noble"),
    ("ubuntu:24.04", "registry-1.docker.io", "library/ubuntu", "24.04"),
    ("ghcr.io/contoso/dev:1", "ghcr.io", "contoso/dev", "1"),
    ("localhost:5000/dev", "localhost:5000", "dev", "latest"),
])
def test_image_ref_parse(ref, registry, repo, tag):
    r = dc.ImageRef.parse(ref)
    assert (r.registry, r.repository, r.tag) == (registry, repo, tag)


def test_digest_references_are_rejected():
    with pytest.raises(ValueError, match="digest"):
        dc.ImageRef.parse("mcr.microsoft.com/devcontainers/dotnet@sha256:" + "0" * 64)


@pytest.mark.parametrize("tag,floating,major", [
    ("3-10.0-noble", "10.0-noble", 3), ("1-10.0", "10.0", 1), ("2.3.5-10.0-noble", "10.0-noble", 2),
    ("10.0-noble", None, None), ("3.12-bookworm", None, None), ("dev-10.0", None, None),
])
def test_floating_tag_and_pinned_major(tag, floating, major):
    r = dc.ImageRef("mcr.microsoft.com", "devcontainers/dotnet", tag)
    assert (r.floating_tag(), r.pinned_major()) == (floating, major)


def test_the_old_major_pin_is_stuck_on_a_release_candidate(recorded_registry):
    code, report = dc.check("mcr.microsoft.com/devcontainers/dotnet:1-10.0-noble", recorded_registry)
    assert code == 1 and report["status"] == "stale"
    assert report["pinned"]["toolchain"]["DOTNET_SDK_VERSION"].startswith("10.0.100-rc.")
    assert report["floating"]["version"].startswith("3.")
    assert "move to 3-10.0-noble" in report["message"]


def test_our_pin_is_current(recorded_registry, devcontainer):
    code, report = dc.check(devcontainer["image"], recorded_registry)
    assert code == 0 and report["status"] == "ok"
    assert report["pinned"]["toolchain"]["DOTNET_SDK_VERSION"] == report["floating"]["toolchain"]["DOTNET_SDK_VERSION"]


def test_image_metadata_lists_what_the_image_adds(recorded_registry, devcontainer):
    info = recorded_registry.image_info(dc.ImageRef.parse(devcontainer["image"]))
    assert "ghcr.io/devcontainers/features/node:2" in info.features
    assert {"dbaeumer.vscode-eslint", "ms-dotnettools.csharp"} <= set(info.extensions)


def test_main_exit_codes_and_output(recorded_registry, capsys):
    cfg = str(APP / ".devcontainer/devcontainer.json")
    assert dc.main([cfg], registry=recorded_registry) == 0
    assert "OK" in capsys.readouterr().out
    assert dc.main([cfg, "--image", "mcr.microsoft.com/devcontainers/dotnet:1-10.0-noble"],
                   registry=recorded_registry) == 1
    out = capsys.readouterr().out
    assert "STALE" in out and "10.0.100-rc." in out
    assert dc.main([cfg, "--image", "mcr.microsoft.com/devcontainers/dotnet:9-99.0"], registry=recorded_registry) == 2


def test_json_output(recorded_registry, capsys):
    dc.main([str(APP / ".devcontainer/devcontainer.json"), "--json"], registry=recorded_registry)
    assert json.loads(capsys.readouterr().out)["status"] == "ok"


@pytest.mark.skipif(os.environ.get("ONLINE") != "1", reason="set ONLINE=1 to query mcr.microsoft.com")
def test_live_registry(devcontainer):
    code, report = dc.check(devcontainer["image"], dc.Registry())
    assert code in (0, 1), report
