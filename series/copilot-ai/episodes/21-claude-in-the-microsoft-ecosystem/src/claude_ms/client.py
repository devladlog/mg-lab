"""Build the Anthropic SDK client for a Claude deployment in Microsoft Foundry.

Learn (Deploy and use Claude models in Microsoft Foundry): the Messages API lives at
https://<resource>.services.ai.azure.com/anthropic/v1/messages, Microsoft Entra ID tokens use the scope
https://ai.azure.com/.default, and the `model` parameter is the *deployment name*.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Callable, Optional

ENTRA_SCOPE = "https://ai.azure.com/.default"
_RESOURCE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*$")


class ConfigError(ValueError):
    """Raised when the Foundry connection settings are missing or malformed."""


@dataclass(frozen=True)
class Connection:
    resource: str
    auth: str  # "entra" or "api-key"


def resolve_resource(resource: Optional[str] = None, env: Optional[dict] = None) -> str:
    """The Foundry resource *name* (not a URL). Falls back to ANTHROPIC_FOUNDRY_RESOURCE."""
    env = os.environ if env is None else env
    value = (resource or env.get("ANTHROPIC_FOUNDRY_RESOURCE") or "").strip()
    if not value:
        raise ConfigError("Foundry resource name missing: pass --resource or set ANTHROPIC_FOUNDRY_RESOURCE")
    if not _RESOURCE_RE.match(value):
        raise ConfigError(
            f"'{value}' is not a resource name. Use only the name, for example 'mglabfoundry21', "
            "not a URL: the SDK builds https://<name>.services.ai.azure.com/anthropic itself"
        )
    return value


def build_client(
    resource: Optional[str] = None,
    *,
    api_key: Optional[str] = None,
    token_provider: Optional[Callable[[], str]] = None,
    http_client: Any = None,
    env: Optional[dict] = None,
    max_retries: int = 2,
):
    """Return (client, Connection).

    Auth order: explicit token_provider, explicit api_key, ANTHROPIC_FOUNDRY_API_KEY, then Microsoft Entra ID
    through DefaultAzureCredential (the recommended path; the only one when the resource has local auth disabled).
    """
    from anthropic import AnthropicFoundry  # imported late so the pure helpers work without the SDK

    env = os.environ if env is None else env
    name = resolve_resource(resource, env)
    key = api_key or env.get("ANTHROPIC_FOUNDRY_API_KEY") or None
    kwargs: dict = {"resource": name, "max_retries": max_retries}
    if http_client is not None:
        kwargs["http_client"] = http_client
    if token_provider is not None:
        kwargs["azure_ad_token_provider"] = token_provider
        auth = "entra"
    elif key:
        kwargs["api_key"] = key
        auth = "api-key"
    else:
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider

        kwargs["azure_ad_token_provider"] = get_bearer_token_provider(DefaultAzureCredential(), ENTRA_SCOPE)
        auth = "entra"
    return AnthropicFoundry(**kwargs), Connection(resource=name, auth=auth)
