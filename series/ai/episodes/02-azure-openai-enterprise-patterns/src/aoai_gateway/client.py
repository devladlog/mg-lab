"""An OpenAI client that talks to the gateway, not to Azure OpenAI directly.

The app holds one secret: its APIM subscription key (per team, revocable, with its own token budget). It never sees
an Azure OpenAI key (they are disabled) and never needs the Azure OpenAI role: the gateway calls the model with its
own managed identity. Store the subscription key in Key Vault or app settings, not in code.
"""
from __future__ import annotations

from typing import Any

# The OpenAI SDK always sends "Authorization: Bearer <api_key>". The gateway authenticates the caller with the
# "api-key" header and overwrites Authorization with its own managed-identity token, so this value never matters.
UNUSED_BEARER = "not-used-behind-gateway"


def gateway_base_url(gateway_url: str, api_path: str = "aoai") -> str:
    """https://<apim>.azure-api.net + /aoai + /openai/v1/  (the Azure OpenAI v1 surface, proxied)."""
    return f"{gateway_url.rstrip('/')}/{api_path.strip('/')}/openai/v1/"


def make_gateway_client(gateway_url: str, subscription_key: str, *, api_path: str = "aoai", max_retries: int = 2,
                        **kwargs: Any):
    from openai import OpenAI  # lazy import: the pure modules and their tests don't need the SDK

    if not subscription_key:
        raise ValueError("subscription_key is required (APIM subscription for this team/app)")
    return OpenAI(
        base_url=gateway_base_url(gateway_url, api_path),
        api_key=UNUSED_BEARER,
        default_headers={"api-key": subscription_key},
        max_retries=max_retries,
        **kwargs,
    )
