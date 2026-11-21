import copy
import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def invoice_result():
    """A fresh copy of the fictional Fabrikam invoice result (REST shape)."""
    return json.loads((FIXTURES / "invoice_fabrikam.json").read_text(encoding="utf-8"))


@pytest.fixture
def fields(invoice_result):
    return invoice_result["documents"][0]["fields"]


def clone(result):
    return copy.deepcopy(result)
