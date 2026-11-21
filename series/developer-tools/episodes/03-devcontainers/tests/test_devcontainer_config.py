"""Static checks of .devcontainer/devcontainer.json: official schema plus the team's own rules."""
import json
import re
import subprocess

import jsonschema
import pytest
from referencing import Registry, Resource

from conftest import APP, SCHEMAS, dc

PIN = re.compile(r"^(?P<image_major>\d+)-(?P<dotnet>\d+\.\d+)-(?P<os>[a-z]+)$")


def schema_validators():
    base = json.loads((SCHEMAS / "devContainer.base.schema.json").read_text())
    vscode = json.loads((SCHEMAS / "devContainer.vscode.schema.json").read_text())
    codespaces = json.loads((SCHEMAS / "devContainer.codespaces.schema.json").read_text())
    # The VS Code schema points its "settings" at VS Code's own settings registry (vscode://...), which only
    # exists inside VS Code. Map it to "any object" so the rest of the schema still validates.
    vscode_only = Registry().with_resource(
        "vscode://schemas/settings/machine",
        Resource.from_contents({"$schema": "http://json-schema.org/draft-07/schema#", "type": "object"}))
    return [jsonschema.Draft201909Validator(base), jsonschema.Draft7Validator(vscode, registry=vscode_only),
            jsonschema.Draft7Validator(codespaces, registry=vscode_only)]


def schema_errors(config: dict) -> list[str]:
    return [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}"
            for v in schema_validators() for e in v.iter_errors(config)]


def test_matches_the_official_schemas(devcontainer):
    assert schema_errors(devcontainer) == []


def test_schema_catches_a_typo_in_a_lifecycle_property(devcontainer):
    broken = {**devcontainer, "postCreateComand": devcontainer["postCreateCommand"]}  # one 'm'
    assert schema_errors(broken), "a misspelled property must fail validation"


def test_no_trailing_commas_because_the_schema_disallows_them():
    # The schema says allowComments: true, allowTrailingCommas: false. Drop the full-line comments and the
    # rest must be strict JSON.
    raw = (APP / ".devcontainer" / "devcontainer.json").read_text()
    json.loads(re.sub(r"(?m)^\s*//.*$", "", raw))


def test_vscode_schema_rejects_an_extension_id_without_publisher(devcontainer):
    vs = dict(devcontainer["customizations"]["vscode"], extensions=["csdevkit"])
    broken = {**devcontainer, "customizations": {"vscode": vs}}
    assert any("extensions" in e for e in schema_errors(broken))


def test_image_is_microsoft_dotnet_with_a_pinned_image_major(devcontainer):
    ref = dc.ImageRef.parse(devcontainer["image"])
    assert ref.registry == "mcr.microsoft.com" and ref.repository == "devcontainers/dotnet"
    m = PIN.match(ref.tag)
    assert m, f"tag {ref.tag!r} should look like <image major>-<dotnet>-<os>, e.g. 3-10.0-noble"


def test_image_dotnet_matches_the_projects_and_global_json(devcontainer):
    dotnet = PIN.match(dc.ImageRef.parse(devcontainer["image"]).tag).group("dotnet")
    global_json = json.loads((APP / "global.json").read_text())
    assert global_json["sdk"]["version"].startswith(dotnet.split(".")[0] + ".")
    assert global_json["sdk"]["rollForward"] == "latestFeature"   # image SDK 10.0.4xx satisfies 10.0.100
    for csproj in APP.rglob("*.csproj"):
        assert f"<TargetFramework>net{dotnet}</TargetFramework>" in csproj.read_text(), csproj.name


def test_features_are_pinned_to_a_major_version(devcontainer):
    for ref in devcontainer["features"]:
        assert re.fullmatch(r"ghcr\.io/devcontainers/features/[a-z-]+:\d+", ref), ref


def test_feature_options_exist_in_the_published_manifests(devcontainer, features_meta):
    for ref, options in devcontainer["features"].items():
        meta = features_meta[ref]
        for name, value in options.items():
            assert name in meta["options"], f"{ref}: unknown option {name!r}"
            spec = meta["options"][name]
            assert {"boolean": bool, "string": str}[spec["type"]] is type(value), f"{ref}.{name}"
            allowed = spec.get("enum")
            if allowed:
                assert value in allowed


def test_python_feature_uses_the_distro_python_without_extra_tools(devcontainer):
    assert devcontainer["features"]["ghcr.io/devcontainers/features/python:1"] == {
        "version": "os-provided", "installTools": False}


def test_forwarded_port_is_the_port_the_api_listens_on(devcontainer):
    launch = json.loads((APP / "src/Contoso.Orders.Api/Properties/launchSettings.json").read_text())
    port = int(launch["profiles"]["http"]["applicationUrl"].rsplit(":", 1)[1])
    assert port == 8080
    assert port in devcontainer["forwardPorts"]
    assert str(port) in devcontainer["portsAttributes"]


def test_extensions_are_valid_and_removals_target_something_we_actually_get(devcontainer, features_meta,
                                                                            recorded_registry):
    exts = devcontainer["customizations"]["vscode"]["extensions"]
    assert len(exts) == len(set(exts))
    added = [e for e in exts if not e.startswith("-")]
    removed = [e[1:] for e in exts if e.startswith("-")]
    assert "ms-dotnettools.csdevkit" in added
    image_exts = recorded_registry.image_info(dc.ImageRef.parse(devcontainer["image"])).extensions
    feature_exts = [x for f in devcontainer["features"]
                    for x in features_meta[f]["customizations"].get("vscode", {}).get("extensions", [])]
    for r in removed:
        assert r in image_exts + feature_exts, f"-{r} removes nothing: neither the image nor a Feature adds it"


def test_nuget_volume_belongs_to_the_remote_user_and_post_create_fixes_ownership(devcontainer):
    user = devcontainer["remoteUser"]
    assert user != "root"
    (mount,) = devcontainer["mounts"]
    parts = dict(p.split("=", 1) for p in mount.split(","))
    assert parts["type"] == "volume" and parts["target"] == f"/home/{user}/.nuget/packages"
    script = (APP / ".devcontainer/post-create.sh").read_text()
    assert 'sudo chown -R "$(id -u):$(id -g)" "$nuget"' in script


def test_post_create_script_exists_and_is_lf_only(devcontainer):
    cmd = devcontainer["postCreateCommand"]
    assert cmd == "bash .devcontainer/post-create.sh"
    script = APP / cmd.split()[1]
    data = script.read_bytes()
    assert b"\r\n" not in data, "CRLF in a shell script breaks it in the Linux container"
    assert data.startswith(b"#!/usr/bin/env bash\n")
    assert b"set -euo pipefail" in data
    subprocess.run(["bash", "-n", str(script)], check=True)


def test_gitattributes_keeps_shell_scripts_lf_on_windows_checkouts(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".gitattributes").write_text((APP / ".gitattributes").read_text())
    out = subprocess.run(["git", "check-attr", "eol", ".devcontainer/post-create.sh"], cwd=tmp_path,
                         capture_output=True, text=True, check=True).stdout
    assert out.strip().endswith("eol: lf")


@pytest.mark.parametrize("key", ["containerEnv", "remoteEnv"])
def test_no_secrets_in_environment(devcontainer, key):
    for name, value in devcontainer.get(key, {}).items():
        assert not re.search(r"(?i)password|secret|token|key", name), name
