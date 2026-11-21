"""Contract check, request builders and scorer for the inspection triage routes. Standard library plus jsonschema."""
import json
import re
from pathlib import Path

import jsonschema

HERE = Path(__file__).resolve().parent
SRC = HERE.parent
SCHEMA = json.loads((SRC / "contract" / "triage.schema.json").read_text(encoding="utf-8"))
SYSTEM_PROMPT = (SRC / "prompts" / "system.md").read_text(encoding="utf-8").strip()
SEVERITIES = ["Info", "Minor", "Major", "Critical"]
ANTHROPIC_VERSION = "2026-10-21"  # platform.claude.com/docs/en/api/versioning lists 2026-10-21, 2023-06-01 and 2023-01-01


def load_golden(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def parse_model_text(text):
    """Model text -> (dict or None, error or None). Accepts bare JSON or JSON inside a code fence; nothing else."""
    if text is None:
        return None, "empty"
    t = text.strip()
    m = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", t, re.S)
    if m:
        t = m.group(1)
    try:
        obj = json.loads(t)
    except json.JSONDecodeError as e:
        return None, f"not json: {e.msg}"
    try:
        jsonschema.validate(obj, SCHEMA)
    except jsonschema.ValidationError as e:
        return None, f"contract: {e.message}"
    return obj, None


def user_message(notes):
    return f"Notes: {notes}"


def openai_body(model, notes, image_b64=None):
    """Azure OpenAI v1 / OpenAI chat completions body."""
    content = [{"type": "text", "text": user_message(notes)}]
    if image_b64:
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}", "detail": "low"}})
    return {"model": model, "temperature": 0, "max_tokens": 300,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": content}]}


def anthropic_body(model, notes, image_b64=None):
    """Anthropic Messages API body."""
    content = []
    if image_b64:
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64}})
    content.append({"type": "text", "text": user_message(notes)})
    return {"model": model, "max_tokens": 300, "system": SYSTEM_PROMPT, "messages": [{"role": "user", "content": content}]}


def openai_text(resp):
    return resp["choices"][0]["message"]["content"]


def anthropic_text(resp):
    return "".join(b.get("text", "") for b in resp.get("content", []) if b.get("type") == "text")


def usage(resp):
    u = resp.get("usage", {})
    return u.get("prompt_tokens", u.get("input_tokens", 0)), u.get("completion_tokens", u.get("output_tokens", 0))


def score(golden, answers):
    """answers: {id: model text or None}. Under-calls of Major/Critical are the dangerous misses and are counted separately."""
    n = len(golden)
    invalid = sev_ok = cat_ok = under = 0
    rows = []
    for g in golden:
        obj, err = parse_model_text(answers.get(g["id"]))
        if err:
            invalid += 1
            rows.append({"id": g["id"], "error": err})
            continue
        s_ok, c_ok = obj["severity"] == g["severity"], obj["category"] == g["category"]
        sev_ok += s_ok
        cat_ok += c_ok
        gap = SEVERITIES.index(g["severity"]) - SEVERITIES.index(obj["severity"])
        is_under = gap > 0 and SEVERITIES.index(g["severity"]) >= 2
        under += is_under
        rows.append({"id": g["id"], "severity": obj["severity"], "category": obj["category"], "severity_ok": s_ok, "category_ok": c_ok, "under_call": is_under})
    return {"n": n, "invalid": invalid, "severity_correct": sev_ok, "category_correct": cat_ok, "under_calls": under,
            "severity_accuracy": round(sev_ok / n, 3) if n else 0.0, "category_accuracy": round(cat_ok / n, 3) if n else 0.0, "rows": rows}
