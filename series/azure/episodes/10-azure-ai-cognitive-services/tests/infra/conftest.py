import json
import pathlib
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def main() -> dict:
    out = subprocess.run(["bicep", "build", str(ROOT / "infra" / "main.bicep"), "--stdout"],
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def resource(template: dict, rtype: str) -> dict:
    found = [r for r in template["resources"] if r["type"].lower() == rtype.lower()]
    assert len(found) == 1, f"expected one {rtype}, found {len(found)}"
    return found[0]
