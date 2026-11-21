"""One OpenAI client for chat (vision), Whisper and TTS: the Azure OpenAI v1 endpoint with an Entra token, no key."""
from __future__ import annotations

import openai

SCOPE = "https://ai.azure.com/.default"


def make_client(endpoint: str, credential=None) -> openai.OpenAI:
    """Needs the Cognitive Services OpenAI User role on the account. Keys are disabled on the resource."""
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider

    provider = get_bearer_token_provider(credential or DefaultAzureCredential(), SCOPE)
    return openai.OpenAI(base_url=f"{endpoint.rstrip('/')}/openai/v1/", api_key=provider)
