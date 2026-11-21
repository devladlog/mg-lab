"""Azure AI Content Safety, keyless: harm categories (analyze text) and Prompt Shields (user prompt + documents).

The Python SDK (azure-ai-contentsafety 1.0.0, the latest on PyPI) defaults to api-version 2023-10-01, which Learn
lists as deprecated since 1 March 2025. We pin the current GA version, 2024-09-01, for both calls. Prompt Shields has
no method in that SDK, so it goes through the same client's send_request (same endpoint, same Entra ID auth).
Careful: the SDK's base URL is already "{endpoint}/contentsafety", so the relative path is "/text:shieldPrompt";
"/contentsafety/text:shieldPrompt" would become /contentsafety/contentsafety/... and return 404.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from azure.ai.contentsafety import ContentSafetyClient
from azure.ai.contentsafety.models import AnalyzeTextOptions, AnalyzeTextOutputType
from azure.core.rest import HttpRequest

API_VERSION = "2024-09-01"
CATEGORIES = ("Hate", "Sexual", "Violence", "SelfHarm")

# Learn, input requirements: analyze text 10K characters; Prompt Shields prompt 10K characters,
# up to five documents with a total of 10K characters.
MAX_TEXT = 10_000
MAX_DOCS = 5
MAX_DOCS_TOTAL = 10_000


def make_safety_client(endpoint: str, credential=None) -> ContentSafetyClient:
    if credential is None:
        from azure.identity import DefaultAzureCredential

        credential = DefaultAzureCredential()
    return ContentSafetyClient(endpoint, credential, api_version=API_VERSION)


def analyze(client: ContentSafetyClient, text: str) -> dict[str, int]:
    """Severity per harm category, four levels (0, 2, 4, 6)."""
    if len(text) > MAX_TEXT:
        raise ValueError(f"text is {len(text)} characters; analyze text accepts {MAX_TEXT}. Split it first.")
    result = client.analyze_text(AnalyzeTextOptions(
        text=text, categories=list(CATEGORIES), output_type=AnalyzeTextOutputType.FOUR_SEVERITY_LEVELS))
    return {str(c.category): int(c.severity or 0) for c in result.categories_analysis}


@dataclass
class ShieldResult:
    user_attack: bool
    document_attacks: list[bool] = field(default_factory=list)


def shield(client: ContentSafetyClient, user_prompt: str, documents: list[str] | None = None) -> ShieldResult:
    """Prompt Shields: one boolean for the prompt, one per document. The API flags; the caller decides."""
    documents = list(documents or [])
    if len(user_prompt) > MAX_TEXT:
        raise ValueError(f"prompt is {len(user_prompt)} characters; Prompt Shields accepts {MAX_TEXT}")
    if len(documents) > MAX_DOCS or sum(map(len, documents)) > MAX_DOCS_TOTAL:
        raise ValueError(f"Prompt Shields accepts up to {MAX_DOCS} documents and {MAX_DOCS_TOTAL} characters in total")
    request = HttpRequest("POST", "/text:shieldPrompt", params={"api-version": API_VERSION},
                          json={"userPrompt": user_prompt, "documents": documents})
    response = client.send_request(request)
    response.raise_for_status()
    data = response.json()
    return ShieldResult(
        user_attack=bool(data.get("userPromptAnalysis", {}).get("attackDetected")),
        document_attacks=[bool(d.get("attackDetected")) for d in data.get("documentsAnalysis", [])],
    )
