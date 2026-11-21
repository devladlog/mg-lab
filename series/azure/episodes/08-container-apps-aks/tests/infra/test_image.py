"""Builds the real container image with the .NET SDK (no Docker daemon) and checks what the platforms rely on."""
import json
import shutil
import subprocess
import tarfile

import pytest

from conftest import ROOT

pytestmark = pytest.mark.skipif(shutil.which("dotnet") is None, reason="dotnet SDK not installed")


@pytest.fixture(scope="module")
def image_config(tmp_path_factory) -> dict:
    out = tmp_path_factory.mktemp("image") / "orders.tar.gz"
    subprocess.run(
        ["dotnet", "publish", str(ROOT / "src" / "Contoso.Orders.Api"), "-c", "Release", "-m:1",
         "/t:PublishContainer", f"-p:ContainerArchiveOutputPath={out}", "-p:Version=1.2.3"],
        check=True, capture_output=True, text=True, timeout=600)
    with tarfile.open(out) as tar:
        manifest = json.load(tar.extractfile("manifest.json"))
        assert manifest[0]["RepoTags"] == ["contoso/orders-api:1.2.3"]
        return json.load(tar.extractfile(manifest[0]["Config"]))["config"]


def test_listens_on_8080_as_the_ingress_and_probes_expect(image_config):
    assert "8080/tcp" in image_config["ExposedPorts"]
    assert "ASPNETCORE_HTTP_PORTS=8080" in image_config["Env"]


def test_runs_as_a_numeric_non_root_user(image_config):
    # runAsNonRoot in k8s/deployment.yaml needs a numeric UID the kubelet can verify
    assert image_config["User"] == "1654"


def test_version_comes_from_the_build_and_entrypoint_is_the_app(image_config):
    assert image_config["Labels"]["org.opencontainers.image.version"] == "1.2.3"
    assert image_config["Entrypoint"] == ["dotnet", "/app/Contoso.Orders.Api.dll"]
