import json
import os

import httpx2 as httpx
import pytest

from llm_sidebyside import gemini_adapter, openai_adapter

SAMPLES = os.path.join(os.path.dirname(__file__), "..", "src", "samples")

GOOD = {
    "vendors": [
        {"name": "Fabrikam Cloud", "renews": "2027-03-31", "yearly_cost_eur": 18400, "notice_days": 60},
        {"name": "Northwind Print", "renews": "2027-06-14", "yearly_cost_eur": 4200},
        {"name": "Adventure Works Telecom", "renews": "2027-09-02", "yearly_cost_eur": 9900, "notice_days": 30},
        {"name": "Litware Security", "renews": "2026-11-30", "yearly_cost_eur": 12500},
    ],
    "first_to_renew": "Litware Security",
    "total_yearly_cost_eur": 45000,
}


class Wire:
    """Scripted endpoint: pops one (status, json, headers) per request and records what the SDK really sent."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests = []

    def handler(self, request):
        self.requests.append({"url": str(request.url), "headers": dict(request.headers), "body": json.loads(request.content or b"{}")})
        status, body, *rest = self.replies.pop(0)
        return httpx.Response(status, json=body, headers=rest[0] if rest else None)

    def http(self):
        return httpx.Client(transport=httpx.MockTransport(self.handler))

    def openai(self):
        return openai_adapter.build_client(api_key="sk-test", http_client=self.http())

    def gemini(self):
        return gemini_adapter.build_client(api_key="g-test", http_client=self.http())


# ---- OpenAI Responses shapes --------------------------------------------------------------------------------------

def oa_resp(text=None, *, status="completed", items=None, refusal=None, usage=(100, 40, 10, 0), incomplete=None):
    output = list(items or [])
    if text is not None:
        output.append({"type": "message", "id": "msg_1", "role": "assistant", "status": "completed",
                       "content": [{"type": "output_text", "text": text, "annotations": []}]})
    if refusal is not None:
        output.append({"type": "message", "id": "msg_1", "role": "assistant", "status": "completed",
                       "content": [{"type": "refusal", "refusal": refusal}]})
    i, o, r, c = usage
    return {"id": "resp_1", "object": "response", "created_at": 1, "status": status, "model": "gpt-6.2-sol", "output": output,
            "incomplete_details": incomplete, "parallel_tool_calls": True, "tool_choice": "auto", "tools": [],
            "usage": {"input_tokens": i, "output_tokens": o, "total_tokens": i + o,
                      "input_tokens_details": {"cached_tokens": c}, "output_tokens_details": {"reasoning_tokens": r}}}


def oa_call(args, call_id="call_1"):
    return {"type": "function_call", "id": "fc_1", "call_id": call_id, "name": "get_vendor_renewals", "arguments": json.dumps(args), "status": "completed"}


# ---- Gemini Interactions shapes -----------------------------------------------------------------------------------

def gm_resp(text=None, *, status="completed", steps=None, usage=(120, 30, 12, 0)):
    steps = list(steps or [])
    if text is not None:
        steps.append({"type": "model_output", "content": [{"type": "text", "text": text}]})
    i, o, t, c = usage
    return {"id": "int_1", "status": status, "model": "gemini-3.8-flash", "role": "model", "steps": steps,
            "usage": {"total_input_tokens": i, "total_output_tokens": o, "total_thought_tokens": t, "total_cached_tokens": c, "total_tokens": i + o + t}}


def gm_call(args, call_id="fc1"):
    return {"type": "function_call", "id": call_id, "name": "get_vendor_renewals", "arguments": args}


@pytest.fixture
def data():
    from llm_sidebyside import contract
    return contract.load_vendors(os.path.join(SAMPLES, "vendors.json"))
