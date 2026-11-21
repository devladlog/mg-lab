"""Tokens with MSAL. The scope is '<environment URL>/.default' for finance and operations and for Dataverse.

finance and operations (Learn, Service endpoints overview): register a Microsoft Entra app, then register its client id
in the environment (System administration > Setup > Microsoft Entra applications) with a service user. So there is no
shared sample client id here: AZURE_CLIENT_ID is required.
- client credentials: set AZURE_CLIENT_SECRET (service to service, shared secret)
- interactive sign-in (authorization code grant): leave AZURE_CLIENT_SECRET empty; the app needs the delegated
  permission to access Dynamics AX data
Dataverse: the same app can be used if it has an application user in that environment; with no AZURE_CLIENT_SECRET the
interactive mode uses the Microsoft Learn sample client id for prototyping, as in episodes 1-11.
"""
from __future__ import annotations

import os
from typing import Callable, Optional

DATAVERSE_SAMPLE_CLIENT_ID = "51f81489-12ee-4a9e-aaae-a2591f45987d"


def token_provider(resource_url: str, *, dataverse: bool = False) -> Callable[[], str]:
    import msal  # lazy: the offline runs and the tests don't need it

    scope = [resource_url.rstrip("/") + "/.default"]
    tenant = os.environ.get("AZURE_TENANT_ID", "organizations")
    authority = f"https://login.microsoftonline.com/{tenant}"
    secret = os.environ.get("AZURE_CLIENT_SECRET")
    client_id: Optional[str] = os.environ.get("AZURE_CLIENT_ID") or (DATAVERSE_SAMPLE_CLIENT_ID if dataverse and not secret else None)
    if not client_id:
        raise SystemExit("set AZURE_CLIENT_ID (the Microsoft Entra app registered in finance and operations)")

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
