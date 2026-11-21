"""Which host serves what. From Learn: a Foundry resource (kind AIServices) exposes three FQDNs under the same custom
subdomain, and the Foundry Tools (Language, Translator, Content Safety, Document Intelligence, Vision) live on
<name>.cognitiveservices.azure.com. Microsoft Entra only works against the custom subdomain, never a regional endpoint."""
from __future__ import annotations

import re
from urllib.parse import urlparse

SUFFIX_TOOLS = "cognitiveservices.azure.com"
SUFFIX_OPENAI = "openai.azure.com"
SUFFIX_FOUNDRY = "services.ai.azure.com"
REGIONAL = re.compile(r"^[a-z0-9]+\.api\.cognitive\.microsoft\.com$|^api\.cognitive\.microsoft(translator)?\.com$")
SUBDOMAIN = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$", re.I)


class EndpointError(ValueError):
    pass


def resource_name(endpoint: str) -> str:
    """The custom subdomain, from any of the three endpoints of the same resource."""
    u = urlparse(endpoint if "//" in endpoint else "https://" + endpoint)
    host = (u.hostname or "").lower()
    if u.scheme != "https":
        raise EndpointError("The endpoint must be https.")
    if REGIONAL.match(host):
        raise EndpointError(f"'{host}' is a regional or global endpoint. Learn: Microsoft Entra authentication always needs the "
                            "custom subdomain of the resource, regional endpoints do not support it.")
    for suffix in (SUFFIX_TOOLS, SUFFIX_OPENAI, SUFFIX_FOUNDRY):
        if host.endswith("." + suffix):
            name = host[: -(len(suffix) + 1)]
            if "." not in name and SUBDOMAIN.match(name):
                return name
    raise EndpointError(f"'{host}' is not <custom-subdomain>.{SUFFIX_TOOLS} (or the .{SUFFIX_OPENAI} / .{SUFFIX_FOUNDRY} sibling).")


def tools_endpoint(endpoint: str) -> str:
    return f"https://{resource_name(endpoint)}.{SUFFIX_TOOLS}"


def all_endpoints(endpoint: str) -> dict[str, str]:
    n = resource_name(endpoint)
    return {"tools": f"https://{n}.{SUFFIX_TOOLS}", "openai": f"https://{n}.{SUFFIX_OPENAI}", "foundry": f"https://{n}.{SUFFIX_FOUNDRY}"}


RESOURCE_ID = re.compile(r"^/subscriptions/[0-9a-f-]{36}/resourceGroups/[\w.()-]+/providers/Microsoft\.CognitiveServices/accounts/[\w.-]+$", re.I)


def check_resource_id(rid: str) -> str:
    rid = rid.strip().rstrip("/")
    if not RESOURCE_ID.match(rid):
        raise EndpointError("Not a Microsoft.CognitiveServices account resource id "
                            "(/subscriptions/<id>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<name>).")
    return rid
