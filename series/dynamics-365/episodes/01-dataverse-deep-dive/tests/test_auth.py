"""auth.token_provider with a stand-in msal module: checks the scope and which MSAL flow is used."""
import sys
import types

import pytest

from dvlab import auth


class FakeConfidential:
    calls = []

    def __init__(self, client_id, authority, client_credential):
        FakeConfidential.calls.append(("init", client_id, authority, client_credential))

    def acquire_token_for_client(self, scopes):
        FakeConfidential.calls.append(("token", scopes))
        return {"access_token": "abc"}


class FakePublic:
    def __init__(self, client_id, authority):
        self.client_id = client_id

    def get_accounts(self):
        return []

    def acquire_token_interactive(self, scopes):
        return {"error": "access_denied", "error_description": "user cancelled"}


@pytest.fixture
def fake_msal(monkeypatch):
    mod = types.SimpleNamespace(ConfidentialClientApplication=FakeConfidential, PublicClientApplication=FakePublic)
    monkeypatch.setitem(sys.modules, "msal", mod)
    FakeConfidential.calls.clear()
    return mod


def test_client_credentials_use_env_url_default_scope(fake_msal, monkeypatch):
    monkeypatch.setenv("AZURE_TENANT_ID", "00000000-0000-0000-0000-000000000000")
    monkeypatch.setenv("AZURE_CLIENT_ID", "00000000-0000-0000-0000-000000000001")
    monkeypatch.setenv("AZURE_CLIENT_SECRET", "not-a-real-secret")
    get = auth.token_provider("https://contoso-dev.crm4.dynamics.com/")
    assert get() == "abc"
    assert ("token", ["https://contoso-dev.crm4.dynamics.com/.default"]) in FakeConfidential.calls
    assert FakeConfidential.calls[0][2] == "https://login.microsoftonline.com/00000000-0000-0000-0000-000000000000"


def test_interactive_failure_raises_a_readable_error(fake_msal, monkeypatch):
    monkeypatch.delenv("AZURE_CLIENT_SECRET", raising=False)
    get = auth.token_provider("https://contoso-dev.crm4.dynamics.com")
    with pytest.raises(RuntimeError, match="access_denied"):
        get()
