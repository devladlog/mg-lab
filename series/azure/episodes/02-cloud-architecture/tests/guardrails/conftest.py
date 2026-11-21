"""Compile the Bicep once per session and expose every resource, including those inside modules."""
import json
import pathlib
import subprocess

import pytest

INFRA = pathlib.Path(__file__).resolve().parents[2] / "infra"


def bicep(*args: str) -> dict:
    out = subprocess.run(["bicep", *args, "--stdout"], cwd=INFRA, check=True, capture_output=True, text=True)
    return json.loads(out.stdout)


def walk(template: dict, module: str = "main"):
    """Yield (module, symbolic name, resource) for a compiled ARM template and its nested deployments."""
    resources = template.get("resources", [])
    items = resources.items() if isinstance(resources, dict) else ((r.get("name"), r) for r in resources)
    for symbolic, res in items:
        if res.get("type") == "Microsoft.Resources/deployments" and "template" in res.get("properties", {}):
            yield from walk(res["properties"]["template"], symbolic)
        elif not res.get("existing"):
            yield module, symbolic, res


@pytest.fixture(scope="session")
def main_template() -> dict:
    return bicep("build", "main.bicep")


@pytest.fixture(scope="session")
def resources(main_template) -> list[tuple[str, str, dict]]:
    return list(walk(main_template))


@pytest.fixture(scope="session")
def of_type(resources):
    def pick(rtype: str) -> list[dict]:
        return [r for _, _, r in resources if r["type"].lower() == rtype.lower()]
    return pick


@pytest.fixture(scope="session")
def governance_template() -> dict:
    return bicep("build", "governance.bicep")


@pytest.fixture(scope="session")
def params():
    return lambda env: bicep("build-params", f"env/{env}.bicepparam")
