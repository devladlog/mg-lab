"""The other way to get an image: no Dockerfile, the .NET SDK builds it (`/t:PublishContainer`).
Writing to an archive needs no Docker daemon. Opt-in, because it downloads the ~70 MB base image layers:

    SDK_CONTAINER=1 python3 -m pytest tests/test_sdk_container.py
"""
import json
import os
import shutil
import subprocess
import tarfile

import pytest

from conftest import APP

pytestmark = pytest.mark.skipif(os.environ.get("SDK_CONTAINER") != "1" or shutil.which("dotnet") is None,
                                reason="set SDK_CONTAINER=1 (downloads the base image layers)")


@pytest.fixture(scope="module")
def image(tmp_path_factory):
    out = tmp_path_factory.mktemp("sdk") / "orders-api.tar.gz"
    res = subprocess.run(
        ["dotnet", "publish", "src/Contoso.Orders.Api/Contoso.Orders.Api.csproj", "-c", "Release",
         "--os", "linux", "--arch", "x64", "/t:PublishContainer",
         f"-p:ContainerArchiveOutputPath={out}", "-p:ContainerImageTag=dev"],
        cwd=APP, capture_output=True, text=True, timeout=600)
    assert res.returncode == 0, res.stdout[-3000:]
    assert "on top of base image 'mcr.microsoft.com/dotnet/aspnet:10.0-noble-chiseled-extra'" in res.stdout
    with tarfile.open(out) as t:
        manifest = json.load(t.extractfile("manifest.json"))[0]
        config = json.load(t.extractfile(manifest["Config"]))
        paths = set()
        for layer in manifest["Layers"]:
            with tarfile.open(fileobj=t.extractfile(layer)) as lt:
                paths |= {m.name.lstrip("./") for m in lt.getmembers()}
    yield manifest, config, paths
    out.unlink()


def test_sdk_image_is_non_root_on_8080_from_the_same_base(image):
    manifest, config, paths = image
    c = config["config"]
    assert "app/Contoso.Orders.Api.dll" in paths
    assert manifest["RepoTags"] == ["contoso/orders-api:dev"]
    assert c["User"] == "1654"                          # APP_UID, documented on Learn
    assert "8080/tcp" in c["ExposedPorts"]
    assert c["Labels"]["org.opencontainers.image.base.name"] == "mcr.microsoft.com/dotnet/aspnet:10.0-noble-chiseled-extra"
    assert c["Entrypoint"] == ["dotnet", "/app/Contoso.Orders.Api.dll"]


def test_but_it_has_no_data_folder_for_sqlite(image):
    """The SDK route has no build stage to create /data owned by the app user. With SQLite in a volume,
    that is the reason this repo keeps the Dockerfile (Compose with SQL Server works with either)."""
    _, config, paths = image
    assert not any(p == "data" or p.startswith("data/") for p in paths)
    assert not any(e.startswith("Database__Provider=") for e in config["config"]["Env"])
