"""One identity, one endpoint, four services: the cheapest real call of each, with the verdict explained.

Every probe goes to https://<custom-subdomain>.cognitiveservices.azure.com with the same Entra token. Nothing here reads
a key. The texts are fictional and harmless; no probe writes anything."""
from __future__ import annotations

from dataclasses import dataclass

from .endpoints import tools_endpoint
from .http import Api, Reply

LANGUAGE_API = "2023-04-01"            # GA analyze-text version also used in episode 12
SAFETY_API = "2024-09-01"              # Learn: "The current version is: api-version=2024-09-01"
TRANSLATOR_API = "3.0"
DOCINTEL_API = "2024-11-30"            # the version the Python SDK 1.0.x speaks (v4.0 GA)


@dataclass
class Result:
    id: str
    service: str
    operation: str
    status: int
    ms: int
    request_id: str = ""
    verdict: str = ""
    hint: str = ""
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.verdict == "ok"


def judge(status: int, reply: Reply | None = None, error: str = "") -> tuple[str, str]:
    """Verdict and what to do, by HTTP status. The hints are Learn's documented causes."""
    if status == 0:
        return "unreachable", f"No HTTP status ({error or 'network error'}). Check DNS, proxy and that the subdomain exists; a private endpoint needs private DNS."
    if 200 <= status < 300:
        return "ok", ""
    if status == 401:
        return "unauthorized", ("Token not accepted. Entra needs the custom-subdomain endpoint (not a regional one) and the scope "
                                "https://cognitiveservices.azure.com/.default; check the tenant of the signed-in account.")
    if status == 403:
        return "forbidden", ("The identity has no data-plane role on this resource. Owner and Contributor are management roles only; "
                             "assign Cognitive Services User and wait up to five minutes for the assignment to propagate.")
    if status == 404:
        return "not-found", "This API path or version is not served by this resource or region. Check the version and Learn's region table."
    if status == 429:
        ra = reply.retry_after if reply else ""
        return "throttled", "Rate limit reached" + (f"; the service asks for {ra} s" if ra else "") + ". Back off, do not loop."
    if status >= 500:
        return "service-error", "Service-side error. Retry with backoff; if it persists check Azure status and quote the request id."
    return "client-error", "The request was refused as sent; read the error code."


def _run(id_: str, service: str, operation: str, call, summarise) -> Result:
    r: Reply = call()
    verdict, hint = judge(r.status, r, r.error)
    detail = ""
    if verdict == "ok":
        try:
            detail = summarise(r.body)
        except (KeyError, IndexError, TypeError):
            verdict, hint, detail = "unexpected-shape", "HTTP 200 but the body is not the documented shape.", r.text[:120]
    else:
        detail = r.error_code()
    return Result(id_, service, operation, r.status, r.ms, r.request_id, verdict, hint, detail)


def language_detect(api: Api, base: str) -> Result:
    body = {"kind": "LanguageDetection", "analysisInput": {"documents": [{"id": "1", "text": "O VPN voltou a falhar esta manhã."}]}}
    return _run("language", "Language", "language detection", lambda: api.call("POST", f"{base}/language/:analyze-text?api-version={LANGUAGE_API}", body=body),
                lambda b: "{} ({:.2f})".format(b["results"]["documents"][0]["detectedLanguage"]["iso6391Name"], b["results"]["documents"][0]["detectedLanguage"]["confidenceScore"]))


def translator(api: Api, base: str) -> Result:
    body = [{"Text": "The VPN failed again this morning."}]
    return _run("translator", "Translator", "translate en to pt", lambda: api.call("POST", f"{base}/translator/text/v3.0/translate?api-version={TRANSLATOR_API}&to=pt", body=body),
                lambda b: "{} [{}]".format(b[0]["translations"][0]["text"], b[0]["translations"][0]["to"]))


def content_safety(api: Api, base: str) -> Result:
    body = {"text": "The printer on floor two is out of toner.", "outputType": "FourSeverityLevels"}
    return _run("safety", "Content Safety", "analyze text", lambda: api.call("POST", f"{base}/contentsafety/text:analyze?api-version={SAFETY_API}", body=body),
                lambda b: ", ".join(f"{c['category']}={c['severity']}" for c in b["categoriesAnalysis"]))


def document_intelligence(api: Api, base: str) -> Result:
    """Through the real SDK, so the path is the SDK's and not our guess: the administration client's resource details
    (how many custom models, what the limit is). It reads, and analyses no document."""
    from azure.ai.documentintelligence import DocumentIntelligenceAdministrationClient
    from azure.core.exceptions import HttpResponseError
    import time

    t0 = time.perf_counter()
    try:
        client = DocumentIntelligenceAdministrationClient(base, api.credential, transport=api.transport, retry_total=api.retries)
        d = client.get_resource_details()
        ms = int((time.perf_counter() - t0) * 1000)
        return Result("docintel", "Document Intelligence", "resource details (SDK)", 200, ms, "", "ok", "",
                      f"custom models {d.custom_document_models.count} of {d.custom_document_models.limit}")
    except HttpResponseError as ex:
        ms = int((time.perf_counter() - t0) * 1000)
        status = ex.status_code or 0
        rid = ""
        if ex.response is not None:
            h = {k.lower(): v for k, v in ex.response.headers.items()}
            rid = h.get("apim-request-id") or h.get("x-ms-request-id") or ""
        verdict, hint = judge(status, None, str(ex))
        return Result("docintel", "Document Intelligence", "resource details (SDK)", status, ms, rid, verdict, hint, (ex.message or str(ex))[:300])
    except Exception as ex:                          # noqa: BLE001 - transport errors carry no status
        return Result("docintel", "Document Intelligence", "resource details (SDK)", 0, int((time.perf_counter() - t0) * 1000), "",
                      *judge(0, None, f"{type(ex).__name__}: {ex}"), detail=str(ex)[:200])


PROBES = {"language": language_detect, "translator": translator, "safety": content_safety, "docintel": document_intelligence}


def run_probes(api: Api, endpoint: str, only: list[str] | None = None) -> list[Result]:
    base = tools_endpoint(endpoint)
    ids = only or list(PROBES)
    unknown = [i for i in ids if i not in PROBES]
    if unknown:
        raise ValueError(f"Unknown probe(s): {', '.join(unknown)}. Known: {', '.join(PROBES)}")
    return [PROBES[i](api, base) for i in ids]


def render(results: list[Result]) -> str:
    lines = [f"{'service':<22} {'operation':<24} {'http':>4} {'ms':>6}  {'verdict':<12} detail"]
    for r in results:
        lines.append(f"{r.service:<22} {r.operation:<24} {r.status:>4} {r.ms:>6}  {r.verdict:<12} {r.detail}")
    for r in results:
        if r.hint:
            lines.append(f"  -> {r.service}: {r.hint}" + (f" (request id {r.request_id})" if r.request_id else ""))
    ok = sum(r.ok for r in results)
    lines.append(f"{ok} of {len(results)} services answered with the same identity.")
    return "\n".join(lines)
