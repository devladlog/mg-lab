import json
import pathlib
import subprocess
import sys

import pytest

EP = pathlib.Path(__file__).resolve().parents[2]
INFRA = EP / "infra"
sys.path.insert(0, str(EP / "tools"))


def bicep(*args: str) -> tuple[dict, str]:
    p = subprocess.run(["bicep", *args, "--stdout"], cwd=INFRA, check=True, capture_output=True, text=True)
    return json.loads(p.stdout), p.stderr


@pytest.fixture(scope="session")
def compiled():
    return bicep("build", "identity.bicep")


@pytest.fixture(scope="session")
def template(compiled):
    return compiled[0]


@pytest.fixture(scope="session")
def resources(template):
    return template["resources"]          # languageVersion 2.0: symbolic name -> resource
