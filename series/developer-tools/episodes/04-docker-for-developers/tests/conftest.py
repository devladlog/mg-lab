import sys
from pathlib import Path

import pytest
import yaml

EPISODE = Path(__file__).resolve().parents[1]
APP = EPISODE / "src" / "orders-app"
SCHEMAS = Path(__file__).resolve().parent / "schemas"

sys.path.insert(0, str(APP / "tools"))
import container_lint as cl  # noqa: E402


@pytest.fixture(scope="session")
def dockerfile_text() -> str:
    return (APP / "Dockerfile").read_text()


@pytest.fixture(scope="session")
def stages(dockerfile_text):
    return cl.parse_dockerfile(dockerfile_text)


@pytest.fixture(scope="session")
def compose() -> dict:
    return yaml.safe_load((APP / "compose.yaml").read_text())
