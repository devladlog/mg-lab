"""Tokens for the Dataverse Web API with MSAL. The scope is '<environment URL>/.default'.

Two modes:
- client credentials (an app registration + an application user in the environment): set AZURE_CLIENT_SECRET
- interactive sign-in (a person at the keyboard): leave AZURE_CLIENT_SECRET empty

MSAL caches tokens in memory, so calling the provider before every request is cheap.
"""
from __future__ import annotations

import os
from typing import Callable

# Sample AppId that Microsoft Learn provides "for development and prototyping purposes" in OAuth flows
# (Use connection strings in XRM tooling). For production, register your own app in Microsoft Entra ID.
DEFAULT_PUBLIC_CLIENT_ID = "51f81489-12ee-4a9e-aaae-a2591f45987d"


def token_provider(env_url: str) -> Callable[[], str]:
    import msal  # imported lazily: explain, who and audit run offline without it

    scope = [env_url.rstrip("/") + "/.default"]
    tenant = os.environ.get("AZURE_TENANT_ID", "organizations")
    authority = f"https://login.microsoftonline.com/{tenant}"
    secret = os.environ.get("AZURE_CLIENT_SECRET")

    if secret:
        app = msal.ConfidentialClientApplication(os.environ["AZURE_CLIENT_ID"], authority=authority,
                                                 client_credential=secret)

        def get() -> str:
            result = app.acquire_token_for_client(scopes=scope)
            return _token(result)
        return get

    pub = msal.PublicClientApplication(os.environ.get("AZURE_CLIENT_ID", DEFAULT_PUBLIC_CLIENT_ID), authority=authority)

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
