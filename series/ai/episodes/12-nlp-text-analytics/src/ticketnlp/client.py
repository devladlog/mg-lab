"""The Azure Language client with an Entra token: no key. Needs the resource's custom-subdomain endpoint."""
from __future__ import annotations

from azure.ai.textanalytics import TextAnalyticsClient


def make_client(endpoint: str, credential=None, **kwargs) -> TextAnalyticsClient:
    """Needs a role with the Language analyze-text data action (the Bicep file assigns Cognitive Services Language Reader).
    Entra ID only works against https://<custom-subdomain>.cognitiveservices.azure.com/ (Learn), not a regional endpoint."""
    from azure.identity import DefaultAzureCredential

    return TextAnalyticsClient(endpoint.rstrip("/"), credential or DefaultAzureCredential(), **kwargs)
