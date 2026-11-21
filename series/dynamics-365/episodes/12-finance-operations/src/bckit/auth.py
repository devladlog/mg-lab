"""Tokens for Dataverse with MSAL (the Business Central container uses basic authentication, see bc.py).

- client credentials: set AZURE_CLIENT_ID and AZURE_CLIENT_SECRET (the app needs an application user in the environment)
- interactive sign-in: leave AZURE_CLIENT_SECRET empty; with no AZURE_CLIENT_ID the Microsoft Learn sample client id is
  used for prototyping, as in episodes 1-11
"""
from __future__ import annotations

import os
from typing import Callable

DATAVERSE_SAMPLE_CLIENT_ID = "51f81489-12ee-4a9e-aaae-a2591f45987d"


def token_provider(resource_url: str) -> Callable[[], str]:
    import msal  # lazy: the offline runs and the tests don't need it

    scope = [resource_url.rstrip("/") + "/.default"]
    tenant = os.environ.get("AZURE_TENANT_ID", "organizations")
    authority = f"https://login.microsoftonline.com/{tenant}"
    secret = os.environ.get("AZURE_CLIENT_SECRET")
    client_id = os.environ.get("AZURE_CLIENT_ID") or (DATAVERSE_SAMPLE_CLIENT_ID if not secret else None)
    if not client_id:
        raise SystemExit("set AZURE_CLIENT_ID (the app that goes with AZURE_CLIENT_SECRET)")

    if secret:
        app = msal.ConfidentialClientApplication(client_id, authority=authority, client_credential=secret)
        return lambda: _token(app.acquire_token_for_client(scopes=scope))

    pub = msal.PublicClientApplication(client_id, authority=authority)

    def get_interactive() -> str:
        accounts = pub.get_accounts()
        result = pub.acquire_token_silent(scope, account=accounts[0]) if accounts else None
        if not result:
            result = pub.acquire_token_interactive(scopes=scope)
        return _token(result)
    return get_interactive


def _token(result: dict) -> str:
    if "access_token" not in result:
        raise RuntimeError(f"Token request failed: {result.get('error')}: {result.get('error_description')}")
    return result["access_token"]
