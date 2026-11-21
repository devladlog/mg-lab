import json
import pathlib
import subprocess
import sys

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "netplan"))
sys.path.insert(0, str(ROOT / "infra"))


def bicep(name: str) -> dict:
    out = subprocess.run(["bicep", "build", str(ROOT / "infra" / name), "--stdout"],
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def resources(template: dict, rtype: str) -> list[dict]:
    return [r for r in template["resources"] if r["type"].lower() == rtype.lower()]


def one(template: dict, rtype: str) -> dict:
    found = resources(template, rtype)
    assert len(found) == 1, f"expected one {rtype}, found {len(found)}"
    return found[0]


@pytest.fixture(scope="session")
def main() -> dict:
    return bicep("main.bicep")


@pytest.fixture(scope="session")
def plan() -> dict:
    return json.loads((ROOT / "src" / "netplan" / "plan.json").read_text())


@pytest.fixture(scope="session")
def cloud_init() -> dict:
    return yaml.safe_load((ROOT / "infra" / "cloud-init.yaml").read_text())
