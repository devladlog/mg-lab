"""Everything here is local: the data is synthetic (mlbasics.data), the models are real scikit-learn models. Nothing calls Azure.
Expensive results are computed once per test session on the committed synthetic table."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mlbasics import data, experiments  # noqa: E402


@pytest.fixture(scope="session")
def df():
    return data.generate()


@pytest.fixture(scope="session")
def small():
    return data.generate(n=2400, requesters=150)


@pytest.fixture(scope="session")
def protocol_rows(df):
    return {r["protocol"]: r for r in experiments.compare_protocols(df, kinds=("logistic",))}


@pytest.fixture(scope="session")
def depth_rows(df):
    return experiments.depth_curve(df)


@pytest.fixture(scope="session")
def trained(df):
    return experiments.train_and_test(df)
