import json
import sys
from pathlib import Path

import pytest

EPISODE = Path(__file__).resolve().parents[1]
APP = EPISODE / "src" / "orders-app"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
SCHEMAS = Path(__file__).resolve().parent / "schemas"

sys.path.insert(0, str(APP / "tools"))
import devcontainer_check as dc  # noqa: E402


@pytest.fixture(scope="session")
def devcontainer() -> dict:
    return dc.load_jsonc(APP / ".devcontainer" / "devcontainer.json")


@pytest.fixture(scope="session")
def features_meta() -> dict:
    return json.loads((FIXTURES / "features.json").read_text())


@pytest.fixture(scope="session")
def recorded_registry():
    """Registry client that replays responses recorded from mcr.microsoft.com (tests/fixtures/registry.json)."""
    responses = json.loads((FIXTURES / "registry.json").read_text())
    calls = []

    def fetch(url, accept):
        calls.append(url)
        return (200, {}, responses[url].encode()) if url in responses else (404, {}, b"{}")

    reg = dc.Registry(fetch=fetch)
    reg.calls = calls
    return reg
