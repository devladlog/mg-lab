"""Validate an agent app package folder: three official JSON Schemas plus the cross-file rules Learn documents."""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml
from jsonschema import Draft7Validator

from .findings import Finding

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas"
SCHEMAS = {
    "app": "app-manifest-1.30.schema.json",
    "agent": "declarative-agent-1.9.schema.json",
    "plugin": "plugin-manifest-2.4.schema.json",
}
PLACEHOLDER = re.compile(r"\$\{\{([A-Z0-9_]+)\}\}")

# Limits from Learn: declarative agent schema 1.9 and plugin manifest schema 2.4.
AGENT_NAME_MAX, AGENT_DESC_MAX, AGENT_INSTR_MAX = 100, 1000, 8000
STARTERS_MAX, ACTIONS_MIN, ACTIONS_MAX = 12, 1, 10
PLUGIN_NAME_HUMAN_MAX, PLUGIN_DESC_HUMAN_MAX, PLUGIN_DESC_MODEL_MAX = 20, 100, 2048


def load_schema(kind: str) -> dict:
    return json.loads((SCHEMA_DIR / SCHEMAS[kind]).read_text(encoding="utf-8"))


def schema_findings(doc: object, kind: str, where: str) -> list[Finding]:
    schema = load_schema(kind)
    # The published schemas say draft-04 but use `const`, which draft-04 validators silently ignore: use draft-07.
    out = []
    for err in sorted(Draft7Validator(schema).iter_errors(doc), key=lambda e: list(map(str, e.absolute_path))):
        path = "/".join(map(str, err.absolute_path)) or "(root)"
        out.append(Finding("error", f"{where} {path}", err.message[:160]))
    return out


def unknown_keys(doc: dict, kind: str, where: str) -> list[Finding]:
    """Learn: unrecognised properties make the whole document invalid (the published schema does not always say so)."""
    known = set(load_schema(kind).get("properties", {})) | {"$schema"}
    return [Finding("error", where, f"unknown property {k!r} (Learn: unrecognised properties make the document invalid)")
            for k in doc if k not in known]


def _load_json(path: Path, findings: list[Finding]) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        findings.append(Finding("error", path.name, "file not found"))
    except ValueError as e:
        findings.append(Finding("error", path.name, f"not valid JSON: {e}"))
    return None


def placeholders(text: str) -> set[str]:
    return set(PLACEHOLDER.findall(text))


def validate_package(folder: Path, strict: bool = False) -> list[Finding]:
    """`strict`: unresolved ${{NAME}} placeholders are errors (use on the substituted package)."""
    folder = Path(folder)
    out: list[Finding] = []
    app = _load_json(folder / "manifest.json", out)
    if app is None:
        return out
    raw_app = (folder / "manifest.json").read_text(encoding="utf-8")
    # The app id is a ${{APP_ID}} placeholder in source: schema-check a copy with a zero GUID in its place.
    app_for_schema = json.loads(PLACEHOLDER.sub("00000000-0000-0000-0000-000000000000", raw_app))
    out += schema_findings(app_for_schema, "app", "manifest.json")
    for icon in ("color", "outline"):
        name = (app.get("icons") or {}).get(icon)
        if name and not (folder / name).exists() and not _can_generate_icons(folder):
            out.append(Finding("error", "manifest.json", f"icons.{icon} points to {name} which is not in the folder"))

    agents = (app.get("copilotAgents") or {}).get("declarativeAgents") or []
    if len(agents) != 1:
        out.append(Finding("error", "manifest.json copilotAgents.declarativeAgents",
                           "an app package holds exactly one declarative agent (Learn: root.copilotAgents)"))
    for ref in agents:
        out += _check_agent(folder, ref.get("file", ""))

    if strict:
        for p in sorted(folder.rglob("*")):
            if p.is_file() and p.suffix in {".json", ".yaml", ".yml"}:
                left = placeholders(p.read_text(encoding="utf-8"))
                if left:
                    out.append(Finding("error", p.relative_to(folder).as_posix(), f"unresolved placeholders: {', '.join(sorted(left))}"))
    return out


def _can_generate_icons(folder: Path) -> bool:
    return True  # `dakit package` writes color.png and outline.png when they are missing


def _check_agent(folder: Path, rel: str) -> list[Finding]:
    out: list[Finding] = []
    agent = _load_json(folder / rel, out)
    if agent is None:
        return out
    out += schema_findings(agent, "agent", rel)
    out += unknown_keys(agent, "agent", rel)
    if len(agent.get("name", "")) > AGENT_NAME_MAX:
        out.append(Finding("error", rel, f"name is longer than {AGENT_NAME_MAX} characters"))
    if len(agent.get("description", "")) > AGENT_DESC_MAX:
        out.append(Finding("error", rel, f"description is longer than {AGENT_DESC_MAX} characters"))
    instr = agent.get("instructions", "")
    if not instr.strip():
        out.append(Finding("error", rel, "instructions are required and must not be blank (Learn: 8,000 characters or less)"))
    elif len(instr) > AGENT_INSTR_MAX:
        out.append(Finding("error", rel, f"instructions are {len(instr)} characters, the limit is {AGENT_INSTR_MAX}"))
    if len(agent.get("conversation_starters", [])) > STARTERS_MAX:
        out.append(Finding("error", rel, f"more than {STARTERS_MAX} conversation starters"))
    caps = [c.get("name") for c in agent.get("capabilities", [])]
    if len(caps) != len(set(caps)):
        out.append(Finding("error", rel, "capabilities contains the same capability twice (Learn: at most one of each type)"))
    actions = agent.get("actions", [])
    if actions and not ACTIONS_MIN <= len(actions) <= ACTIONS_MAX:
        out.append(Finding("error", rel, f"actions must hold {ACTIONS_MIN} to {ACTIONS_MAX} entries"))
    for action in actions:
        if "file" in action:
            out += _check_plugin(folder, action["file"])
    for card in agent.get("conversation_starters", []):
        if not card.get("text", "").strip():
            out.append(Finding("error", rel, "a conversation starter has no text"))
    return out


def openapi_operations(spec: dict) -> dict[str, str]:
    """operationId -> HTTP method (upper case)."""
    ops = {}
    for item in (spec.get("paths") or {}).values():
        for method, op in item.items():
            if method.lower() in {"get", "put", "post", "delete", "patch", "head", "options"} and isinstance(op, dict):
                if "operationId" in op:
                    ops[op["operationId"]] = method.upper()
    return ops


def _check_plugin(folder: Path, rel: str) -> list[Finding]:
    out: list[Finding] = []
    plugin = _load_json(folder / rel, out)
    if plugin is None:
        return out
    out += schema_findings(plugin, "plugin", rel)
    out += unknown_keys(plugin, "plugin", rel)
    if len(plugin.get("name_for_human", "")) > PLUGIN_NAME_HUMAN_MAX:
        out.append(Finding("warning", rel, f"name_for_human is longer than {PLUGIN_NAME_HUMAN_MAX} characters: Learn says characters beyond 20 may be ignored"))
    if len(plugin.get("description_for_human", "")) > PLUGIN_DESC_HUMAN_MAX:
        out.append(Finding("warning", rel, f"description_for_human is longer than {PLUGIN_DESC_HUMAN_MAX} characters: the rest may be ignored"))
    if len(plugin.get("description_for_model", "")) > PLUGIN_DESC_MODEL_MAX:
        out.append(Finding("warning", rel, f"description_for_model is longer than {PLUGIN_DESC_MODEL_MAX} characters: the rest may be ignored"))

    function_names = [f.get("name") for f in plugin.get("functions", [])]
    if len(function_names) != len(set(function_names)):
        out.append(Finding("error", rel, "function names must be unique within the plugin"))

    ops: dict[str, str] = {}
    bound: list[str] = []
    for i, rt in enumerate(plugin.get("runtimes", [])):
        where = f"{rel} runtimes[{i}]"
        spec_ref = (rt.get("spec") or {}).get("url")
        if rt.get("type") == "OpenApi":
            if not spec_ref:
                if "api_description" not in (rt.get("spec") or {}):
                    out.append(Finding("error", where, "OpenApi runtime needs spec.url or spec.api_description"))
            elif not re.match(r"https?://", spec_ref):
                spec_path = folder / spec_ref
                if not spec_path.exists():
                    out.append(Finding("error", where, f"spec.url {spec_ref} is not in the package folder"))
                else:
                    try:
                        ops = openapi_operations(yaml.safe_load(spec_path.read_text(encoding="utf-8")))
                    except yaml.YAMLError as e:
                        out.append(Finding("error", spec_ref, f"not valid YAML: {e}"))
        bound += rt.get("run_for_functions", [])
        for fn in rt.get("run_for_functions", []):
            if "*" not in fn and fn not in function_names:
                out.append(Finding("error", where, f"run_for_functions names {fn}, which is not in functions"))
    for fn in plugin.get("functions", []):
        name = fn.get("name")
        if ops and name not in ops:
            out.append(Finding("error", rel, f"function {name} has no operationId {name} in the OpenAPI description (Learn: must match)"))
        method = ops.get(name)
        caps = fn.get("capabilities") or {}
        handling = (caps.get("security_info") or {}).get("data_handling", [])
        if "security_info" not in caps:
            out.append(Finding("warning", rel, f"function {name} has no security_info: Learn says it then cannot interact with other plugins or capabilities of the agent"))
        if method and method != "GET":
            if "ResourceStateUpdate" not in handling:
                out.append(Finding("warning", rel, f"function {name} uses {method} but security_info.data_handling lacks ResourceStateUpdate"))
            if (caps.get("confirmation") or {}).get("type") != "AdaptiveCard":
                out.append(Finding("warning", rel, f"function {name} changes data ({method}) without an AdaptiveCard confirmation"))
        tpl = ((caps.get("response_semantics") or {}).get("static_template") or {})
        if "file" in tpl:
            card = folder / tpl["file"]
            if not card.exists():
                out.append(Finding("error", rel, f"static_template file {tpl['file']} is not in the package folder"))
            else:
                try:
                    if json.loads(card.read_text(encoding="utf-8")).get("type") != "AdaptiveCard":
                        out.append(Finding("error", tpl["file"], "not an Adaptive Card (type must be AdaptiveCard)"))
                except ValueError as e:
                    out.append(Finding("error", tpl["file"], f"not valid JSON: {e}"))
    for name in ops:
        if ops and name not in function_names and plugin.get("functions"):
            out.append(Finding("warning", rel, f"OpenAPI operation {name} is not exposed as a function"))
    return out
