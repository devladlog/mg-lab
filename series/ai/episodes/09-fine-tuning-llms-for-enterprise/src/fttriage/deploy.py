"""Deploy (and remove) the fine-tuned model with the Azure management REST API, as Learn's "deploy a fine-tuned
model for testing" page shows. The model name only exists after training, so this is a script, not Bicep."""
from __future__ import annotations

import re
import time

import requests

API_VERSION = "2025-07-01-preview"   # the version used in Learn's deploy examples
MANAGEMENT = "https://management.azure.com"
# Learn spells the Developer SKU three ways ("developertier" in the REST sample, "Developer" in the CLI sample,
# "DeveloperTier" in the deployment types table); we send the table's spelling. Pass --sku to try another.
SKUS = ("DeveloperTier", "Standard", "GlobalStandard")
NAME_RX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,63}$")
MODEL_RX = re.compile(r"^(?:[A-Za-z0-9._-]+\.ft-[0-9a-f]{32}(?:[A-Za-z0-9._-]*)|ftchkpt-[0-9a-f]{32})$")


def _url(subscription: str, group: str, account: str, name: str, management: str) -> str:
    return (f"{management.rstrip('/')}/subscriptions/{subscription}/resourceGroups/{group}/providers/"
            f"Microsoft.CognitiveServices/accounts/{account}/deployments/{name}")


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def get_token(credential=None) -> str:
    from azure.identity import DefaultAzureCredential
    return (credential or DefaultAzureCredential()).get_token(f"{MANAGEMENT}/.default").token


def deploy(token: str, subscription: str, group: str, account: str, name: str, model_id: str, *,
           sku: str = "DeveloperTier", capacity: int = 50, management: str = MANAGEMENT,
           poll_seconds: float = 10, timeout_seconds: float = 1800, sleep=time.sleep, http=requests) -> dict:
    if sku not in SKUS:
        raise ValueError(f"sku must be one of {SKUS}")
    if not NAME_RX.match(name):
        raise ValueError("deployment name: 2-64 characters, letters, digits, dot, underscore, hyphen")
    if not MODEL_RX.match(model_id):
        raise ValueError("model id must be a fine-tuned model ('<base>.ft-<32 hex>...') or a checkpoint ('ftchkpt-<32 hex>')")
    url = _url(subscription, group, account, name, management)
    body = {"sku": {"name": sku, "capacity": capacity},
            "properties": {"model": {"format": "OpenAI", "name": model_id, "version": "1"}}}
    r = http.put(url, params={"api-version": API_VERSION}, headers=_headers(token), json=body, timeout=60)
    if r.status_code >= 300:
        raise RuntimeError(f"deployment request failed: {r.status_code} {r.text[:300]}")
    deadline = time.monotonic() + timeout_seconds
    while True:
        g = http.get(url, params={"api-version": API_VERSION}, headers=_headers(token), timeout=60)
        g.raise_for_status()
        state = g.json().get("properties", {}).get("provisioningState")
        if state == "Succeeded":
            return g.json()
        if state in ("Failed", "Canceled"):
            raise RuntimeError(f"deployment {name} {state}: {g.text[:300]}")
        if time.monotonic() > deadline:
            raise TimeoutError(f"deployment {name} still {state} after {timeout_seconds:.0f}s")
        sleep(poll_seconds)


def delete(token: str, subscription: str, group: str, account: str, name: str, *, management: str = MANAGEMENT,
           http=requests) -> None:
    r = http.delete(_url(subscription, group, account, name, management), params={"api-version": API_VERSION},
                    headers=_headers(token), timeout=60)
    if r.status_code not in (200, 202, 204):
        raise RuntimeError(f"delete failed: {r.status_code} {r.text[:300]}")
