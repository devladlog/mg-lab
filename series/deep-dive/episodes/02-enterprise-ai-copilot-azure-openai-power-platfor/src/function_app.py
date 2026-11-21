"""POST /api/ask  — the copilot's single tool. Called by the Power Platform custom connector with the user's token.

Platform: App Service authentication requires a valid Entra token for this app (Return401 otherwise), so the
function itself is anonymous at the Functions level and reads the caller from X-MS-CLIENT-PRINCIPAL.
App settings: SEARCH_ENDPOINT, SEARCH_INDEX, OPENAI_ENDPOINT, CHAT_DEPLOYMENT, AZURE_CLIENT_ID.
"""
from __future__ import annotations

import json
import logging
import os

import azure.functions as func
import openai
from azure.core.exceptions import HttpResponseError

from copilot.answer import ask, make_openai
from copilot.identity import GroupOverage, Unauthenticated, parse_client_principal
from copilot.retrieval import Retriever

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)
log = logging.getLogger("copilot")

_deps = None


def get_deps():
    """(Retriever, OpenAI client) — one per worker; tests replace this function."""
    global _deps
    if _deps is None:
        from azure.identity import DefaultAzureCredential
        from azure.search.documents import SearchClient

        cred = DefaultAzureCredential()
        search = SearchClient(os.environ["SEARCH_ENDPOINT"], os.environ["SEARCH_INDEX"], cred)
        _deps = (Retriever(search), make_openai(os.environ["OPENAI_ENDPOINT"], cred))
    return _deps


def _json(status: int, payload: dict) -> func.HttpResponse:
    return func.HttpResponse(json.dumps(payload), status_code=status, mimetype="application/json")


def handle(req: func.HttpRequest) -> func.HttpResponse:
    try:
        caller = parse_client_principal(req.headers.get("X-MS-CLIENT-PRINCIPAL"))
    except Unauthenticated as e:
        return _json(401, {"error": str(e)})
    except GroupOverage:
        return _json(403, {"error": "Your account is in too many groups for this copilot to trim documents safely. "
                                    "Ask an admin to assign the HR groups to the app (groups assigned to the application)."})
    try:
        question = (req.get_json() or {}).get("question", "")
    except ValueError:
        return _json(400, {"error": "Body must be JSON: {\"question\": \"...\"}"})

    retriever, llm = get_deps()
    try:
        result = ask(question, caller, retriever, llm)
    except ValueError as e:
        return _json(400, {"error": str(e)})
    except openai.BadRequestError as e:
        if getattr(e, "code", None) == "content_filter":     # Azure OpenAI's error code for a filtered prompt
            return _json(422, {"error": "The question was blocked by the content filter."})
        raise
    except (openai.RateLimitError, HttpResponseError) as e:
        log.warning("Upstream throttled or failed: %s", type(e).__name__)
        return _json(503, {"error": "The copilot is busy. Try again in a moment."})

    # Log who asked and how much it cost, never the question text or the answer (they can be sensitive).
    log.info("ask by %s: %d sources, grounded=%s, usage=%s",
             caller.object_id, result.sources_considered, result.grounded, result.usage)
    return _json(200, result.to_dict())


@app.route(route="ask", methods=["POST"])
def ask_route(req: func.HttpRequest) -> func.HttpResponse:
    return handle(req)
