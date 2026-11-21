import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dvlab.client import DataverseClient  # noqa: E402
from dvlab.fake import FakeDataverse      # noqa: E402

ENV = "https://contoso-dev.crm4.dynamics.com"


class Recorder:
    """Wraps the fake to keep every request (method, url, headers) for assertions."""

    def __init__(self, fake: FakeDataverse):
        self.fake = fake
        self.requests = []

    def send(self, request, **kwargs):
        self.requests.append(request)
        return self.fake.send(request, **kwargs)

    def close(self):
        pass


@pytest.fixture
def fake():
    return FakeDataverse(key_polls_until_active=2)


@pytest.fixture
def make_client(fake):
    def _make(**kw):
        rec = Recorder(fake)
        s = requests.Session()
        s.mount("https://", rec)
        sleeps = []
        c = DataverseClient(ENV, lambda: "t0ken", session=s, solution=kw.pop("solution", "MGLabDataverse"),
                            sleep=sleeps.append, **kw)
        c.recorder, c.sleeps = rec, sleeps
        return c
    return _make


@pytest.fixture
def client(make_client):
    return make_client()


@pytest.fixture
def provisioned(client):
    from dvlab.cli import provision
    provision(client, out=lambda s: None)
    return client
