import json
import zipfile

import pytest
import yaml

from dakit.cli import main
from dakit.icons import png_size
from dakit.package import PackageError, build
from conftest import PACKAGE

APP_ID = "11111111-2222-3333-4444-555555555555"
VALUES = {"APP_ID": APP_ID, "VENDOR_API_KEY_REGISTRATION_ID": "reg-demo-0001"}
URL = "https://example-tunnel.devtunnels.example/"


def make(tmp_path, **kw):
    out = tmp_path / "dist" / "vendor-desk.zip"
    warnings = build(PACKAGE, out, VALUES, api_url=URL, **kw)
    return out, warnings


def test_zip_layout_has_manifest_and_icons_at_the_root(tmp_path):
    out, warnings = make(tmp_path)
    assert warnings == []
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        assert names[0] == "manifest.json"                      # Learn: manifest.json and icons at the root
        assert {"color.png", "outline.png", "declarativeAgent.json", "vendor-renewals-plugin.json", "openapi.yaml", "adaptiveCards/renewal.json"} <= set(names)
        assert all("${{" not in z.read(n).decode("utf-8", "ignore") for n in names if n.endswith((".json", ".yaml")))
        assert png_size(z.read("color.png")) == (192, 192)
        assert png_size(z.read("outline.png")) == (32, 32)
        assert z.testzip() is None
    assert out.stat().st_size < 50_000


def test_values_are_substituted(tmp_path):
    out, _ = make(tmp_path, version="1.2.3")
    with zipfile.ZipFile(out) as z:
        app = json.loads(z.read("manifest.json"))
        plugin = json.loads(z.read("vendor-renewals-plugin.json"))
        spec = yaml.safe_load(z.read("openapi.yaml"))
    assert app["id"] == APP_ID and app["version"] == "1.2.3"
    assert plugin["runtimes"][0]["auth"]["reference_id"] == "reg-demo-0001"
    assert spec["servers"] == [{"url": "https://example-tunnel.devtunnels.example"}]
    assert "paths" in spec and "components" in spec        # the rest of the spec survives the rewrite


def test_build_is_reproducible(tmp_path):
    a, _ = make(tmp_path)
    first = a.read_bytes()
    a.unlink()
    b, _ = make(tmp_path)
    assert b.read_bytes() == first


def test_no_scratch_folder_is_left_behind(tmp_path):
    make(tmp_path)
    assert [p.name for p in (tmp_path / "dist").iterdir()] == ["vendor-desk.zip"]


def test_bad_inputs_are_refused(tmp_path):
    with pytest.raises(PackageError, match="GUID"):
        build(PACKAGE, tmp_path / "a.zip", {**VALUES, "APP_ID": "not-a-guid"}, api_url=URL)
    with pytest.raises(PackageError, match="https"):
        build(PACKAGE, tmp_path / "b.zip", VALUES, api_url="http://localhost:8080")
    assert not (tmp_path / "b.zip").exists()
    with pytest.raises(PackageError, match="unresolved placeholders"):
        build(PACKAGE, tmp_path / "c.zip", {"APP_ID": APP_ID}, api_url=URL)


def test_broken_package_is_not_zipped(tmp_path, pkg):
    (pkg / "declarativeAgent.json").write_text("{}")
    with pytest.raises(PackageError):
        build(pkg, tmp_path / "d.zip", VALUES, api_url=URL)
    assert not (tmp_path / "d.zip").exists()


def test_cli_package(tmp_path, capsys):
    out = tmp_path / "x.zip"
    rc = main(["package", str(PACKAGE), "--out", str(out), "--app-id", APP_ID, "--api-url", URL, "--auth-id", "reg-1"])
    assert rc == 0 and out.exists()
    assert main(["package", str(PACKAGE), "--out", str(tmp_path / "y.zip"), "--app-id", "nope", "--api-url", URL, "--auth-id", "r"]) == 1
