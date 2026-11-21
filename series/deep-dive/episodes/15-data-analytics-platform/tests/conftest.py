import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from analytics import synthetic as syn  # noqa: E402


@pytest.fixture(scope="session")
def history():
    return syn.generate_history()


@pytest.fixture(scope="session")
def lake(tmp_path_factory, history):
    """A local 'lake' with the two bronze loads (second one carries four bad rows)."""
    root = tmp_path_factory.mktemp("lake")
    syn.write_bronze(syn.delta(history, None, syn.T1), root, "2026-10-31", "run1")
    syn.write_bronze(syn.inject_defects(syn.delta(history, syn.T1, syn.T2)), root, "2026-11-14", "run2")
    return root


@pytest.fixture(scope="session")
def warehouse(lake):
    from analytics.localsql import LocalWarehouse
    wh = LocalWarehouse(lake)
    yield wh
    wh.close()
