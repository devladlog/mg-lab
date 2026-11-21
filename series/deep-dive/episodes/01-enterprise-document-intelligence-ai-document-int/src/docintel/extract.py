"""Call Azure AI Document Intelligence (v4.0, API 2024-11-30) with the prebuilt invoice model."""
from __future__ import annotations

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest

MODEL_ID = "prebuilt-invoice"


def make_client(endpoint: str, credential=None) -> DocumentIntelligenceClient:
    """Keyless by default: the function's managed identity needs 'Cognitive Services User' on the resource."""
    if credential is None:
        from azure.identity import DefaultAzureCredential  # AZURE_CLIENT_ID selects the user-assigned identity

        credential = DefaultAzureCredential()
    return DocumentIntelligenceClient(endpoint=endpoint, credential=credential)


def analyze_invoice(client: DocumentIntelligenceClient, data: bytes, *, locale: str | None = None, **kwargs) -> dict:
    """Send the bytes (base64Source), wait for the long-running operation, return the result as a dict."""
    poller = client.begin_analyze_document(
        MODEL_ID, AnalyzeDocumentRequest(bytes_source=data), locale=locale, **kwargs
    )
    return poller.result().as_dict()
