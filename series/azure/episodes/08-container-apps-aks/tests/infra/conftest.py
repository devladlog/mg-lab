import json
import pathlib
import subprocess

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]


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
def aca() -> dict:
    return bicep("aca.bicep")


@pytest.fixture(scope="session")
def aks() -> dict:
    return bicep("aks.bicep")


@pytest.fixture(scope="session")
def k8s() -> dict:
    docs = {}
    for f in sorted((ROOT / "k8s").glob("*.yaml")):
        for d in yaml.safe_load_all(f.read_text()):
            docs[d["kind"]] = d
    return docs
