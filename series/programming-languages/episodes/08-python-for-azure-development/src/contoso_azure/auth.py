"""Which credential, when. Learn: DefaultAzureCredential for local development, a specific credential in Azure."""

from __future__ import annotations

from azure.core.credentials import TokenCredential
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential


def build_credential(mode: str, managed_identity_client_id: str | None = None) -> TokenCredential:
    """'dev': the DefaultAzureCredential chain (environment, managed identity, Azure CLI, VS Code, ...).
    'azure': exactly the managed identity, so nothing else can be picked up by accident."""
    if mode == "dev":
        return DefaultAzureCredential(exclude_managed_identity_credential=True)
    if mode == "azure":
        return ManagedIdentityCredential(client_id=managed_identity_client_id)
    raise ValueError(f"Unknown auth mode '{mode}': use 'dev' or 'azure'.")
