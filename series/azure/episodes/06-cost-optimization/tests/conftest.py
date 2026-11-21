import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"
sys.path.insert(0, str(ROOT / "src"))

from costwatch.prices import RetailPrices  # noqa: E402


def no_network(url):
    raise AssertionError(f"test tried to call the Retail Prices API: {url}")


@pytest.fixture
def prices(tmp_path):
    """Real API answers captured on 21 Nov 2026 (EUR, Sweden Central/Global); never calls the API."""
    cache = tmp_path / "prices.json"
    shutil.copy(FIXTURES / "retail-prices-cache.json", cache)
    return RetailPrices(currency="EUR", fetch=no_network, cache_file=cache)


@pytest.fixture
def whatif():
    return lambda name: json.loads((FIXTURES / name).read_text())


@pytest.fixture
def fake_az(tmp_path, monkeypatch):
    log = tmp_path / "az.log"
    monkeypatch.setenv("FAKE_AZ_DIR", str(FIXTURES / "graph"))
    monkeypatch.setenv("FAKE_AZ_LOG", str(log))
    monkeypatch.delenv("FAKE_AZ_PAGED", raising=False)
    monkeypatch.delenv("FAKE_AZ_FAIL", raising=False)

    class Az:
        path = str(Path(__file__).parent / "fakes" / "az")

        @staticmethod
        def calls():
            return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    return Az
