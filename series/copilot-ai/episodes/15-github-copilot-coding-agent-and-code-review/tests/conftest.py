from pathlib import Path

import pytest

DEMO = Path(__file__).resolve().parents[1] / "src" / "demo-repo"


@pytest.fixture
def demo() -> Path:
    return DEMO
