from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

DOC_CONFIG = "https://code.visualstudio.com/docs/agents/reference/mcp-configuration"
DOC_MIGRATE = "https://code.visualstudio.com/docs/agent-customization/migrate-customizations"
DOC_GITHUB = "https://github.com/github/github-mcp-server/blob/main/docs/remote-server.md"
DOC_AZURE = "https://learn.microsoft.com/azure/developer/azure-mcp-server/tools/"

EDITOR = "editor"  # servers
NATIVE = "native"  # mcpServers

EDITOR_ONLY_FIELDS = ("envFile", "dev", "sandboxEnabled", "sandbox")
TYPES = {"stdio", "http", "sse"}
SECRET_PATTERNS = [
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"), "GitHub token"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"), "GitHub fine-grained token"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\."), "JWT"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"), "API key (sk-...)"),
    (re.compile(r"(?i)\bbearer\s+(?![\$\{])[A-Za-z0-9._~+/=-]{16,}"), "literal bearer token"),
]
VAR = re.compile(r"\$\{([^}]+)\}")
INPUT_REF = re.compile(r"\$\{input:([^}]+)\}")
BARE = re.compile(r"(?<!\$)\$[A-Za-z_][A-Za-z0-9_]*")


@dataclass(frozen=True)
class Finding:
    severity: str  # error | warn | info
    code: str
    server: str
    message: str
    doc: str = ""

    def line(self) -> str:
        where = f"[{self.server}] " if self.server else ""
        return f"{self.severity.upper():5} {self.code:<20} {where}{self.message}"


@dataclass
class Report:
    fmt: str | None = None
    findings: list[Finding] = field(default_factory=list)

    def add(self, severity, code, server, message, doc=""):
        self.findings.append(Finding(severity, code, server, message, doc))

    def count(self, severity: str) -> int:
        return sum(1 for f in self.findings if f.severity == severity)


def detect(doc: dict) -> str | None:
    if "servers" in doc and "mcpServers" not in doc:
        return EDITOR
    if "mcpServers" in doc and "servers" not in doc:
        return NATIVE
    return None


def _strings(value):
    """Yield every string inside a JSON value."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)


def check(doc: dict) -> Report:
    report = Report(fmt=detect(doc))
    if report.fmt is None:
        both = "servers" in doc and "mcpServers" in doc
        report.add("error", "FORMAT", "",
                   "both `servers` and `mcpServers` are present" if both
                   else "no top-level `servers` (editor format) or `mcpServers` (native Copilot format)", DOC_CONFIG)
        return report
    key = "servers" if report.fmt == EDITOR else "mcpServers"
    servers = doc[key]
    if not isinstance(servers, dict) or not servers:
        report.add("error", "NO_SERVERS", "", f"`{key}` must be an object with at least one server", DOC_CONFIG)
        return report

    declared = {i.get("id") for i in doc.get("inputs", []) if isinstance(i, dict)} if report.fmt == EDITOR else set()
    used_inputs: set[str] = set()
    if report.fmt == NATIVE:
        for editor_key in ("inputs", "sandbox"):
            if editor_key in doc:
                report.add("error", "EDITOR_ONLY", "", f"top-level `{editor_key}` is editor-only; do not copy it into a native file", DOC_CONFIG)

    for name, cfg in servers.items():
        if not isinstance(cfg, dict):
            report.add("error", "SERVER_TYPE", name, "server entry must be an object", DOC_CONFIG)
            continue
        if re.search(r"\s|[^\w.-]", name):
            report.add("warn", "SERVER_NAME", name, "avoid whitespace and special characters in server names (docs: camelCase, e.g. githubIntegration)", DOC_CONFIG)
        stype = cfg.get("type")
        if stype is None:
            inferred = "stdio" if "command" in cfg else "http" if "url" in cfg else None
            sev = "warn" if report.fmt == EDITOR else "info"
            report.add(sev, "TYPE_MISSING", name,
                       "`type` is documented as required in the VS Code reference (the Azure MCP Server sample on Learn omits it)"
                       if report.fmt == EDITOR else "no `type`; stdio or http is inferred only by some clients, state it", DOC_CONFIG)
            stype = inferred
        if stype not in TYPES:
            report.add("error", "TYPE_UNKNOWN", name, f"type '{stype}' is not stdio, http or sse", DOC_CONFIG)
            continue
        if stype == "stdio" and not cfg.get("command"):
            report.add("error", "NO_COMMAND", name, "stdio server needs `command`", DOC_CONFIG)
        if stype in ("http", "sse"):
            url = cfg.get("url")
            if not url:
                report.add("error", "NO_URL", name, f"{stype} server needs `url`", DOC_CONFIG)
            else:
                parsed = urlparse(url)
                if parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
                    report.add("warn", "INSECURE_URL", name, f"{url} is plain http to a non-local host", DOC_CONFIG)
                if parsed.hostname == "api.githubcopilot.com":
                    readonly = "readonly" in parsed.path or str((cfg.get("headers") or {}).get("X-MCP-Readonly", "")).lower() == "true"
                    if not readonly:
                        report.add("info", "GITHUB_READWRITE", name,
                                   "remote GitHub server without /readonly or X-MCP-Readonly: write tools are available (approvals still apply)", DOC_GITHUB)
        args = cfg.get("args") or []
        for a in args:
            if isinstance(a, str) and re.match(r"^@azure/mcp@latest$", a):
                report.add("warn", "UNPINNED_LATEST", name,
                           "`@azure/mcp@latest` runs whatever is newest on every start (it was a 4.0.0-beta on 21 Nov 2026); pin a version", DOC_AZURE)
        if stype == "stdio" and any(isinstance(a, str) and a.startswith("@azure/mcp") for a in args) and "--read-only" not in args:
            report.add("info", "AZURE_READWRITE", name, "no --read-only: tools may create or change Azure resources under your credentials", DOC_AZURE)

        for field_name in EDITOR_ONLY_FIELDS:
            if field_name in cfg and report.fmt == NATIVE:
                report.add("error", "EDITOR_ONLY", name, f"`{field_name}` is editor-only; do not copy it into a native file", DOC_CONFIG)
        if "oauth" in cfg and report.fmt == NATIVE:
            report.add("error", "OAUTH_SHAPE", name, "native files use flat `oauthClientId`, not the nested `oauth` object", DOC_CONFIG)
        if "oauthClientId" in cfg and report.fmt == EDITOR:
            report.add("warn", "OAUTH_SHAPE", name, "editor format uses `oauth: {clientId}`; `oauthClientId` is the native field", DOC_CONFIG)

        for text in _strings({k: v for k, v in cfg.items() if k in ("env", "headers", "args", "url", "command")}):
            for pattern, label in SECRET_PATTERNS:
                if pattern.search(text):
                    report.add("error", "SECRET_LITERAL", name, f"looks like a literal {label}; never commit credentials, use a variable", DOC_CONFIG)
                    break
            for match in VAR.finditer(text):
                ref = match.group(1)
                if ref.startswith("input:"):
                    used_inputs.add(ref[len("input:"):])
                    if report.fmt == NATIVE:
                        report.add("error", "INPUT_IN_NATIVE", name, f"${{{ref}}}: input prompts are not supported in native files; use ${{NAME}}", DOC_CONFIG)
                elif ref.startswith(("command:",)) and report.fmt == NATIVE:
                    report.add("error", "COMMAND_IN_NATIVE", name, f"${{{ref}}} is not supported in native files", DOC_CONFIG)
                elif ref.startswith("env:") and report.fmt == NATIVE:
                    report.add("warn", "ENV_SYNTAX", name, f"${{{ref}}} is the editor syntax; native files use ${{{ref[4:]}}}", DOC_CONFIG)
            if BARE.search(text) and "${" not in text:
                report.add("warn", "BARE_VARIABLE", name, "bare $NAME is treated as literal text by the VS Code MCP client; use ${NAME}", DOC_CONFIG)
        tools = cfg.get("tools")
        if report.fmt == NATIVE and tools == ["*"]:
            report.add("info", "ALL_TOOLS", name, 'tools ["*"] exposes every tool of the server (list names to limit; approvals still apply)', DOC_CONFIG)

    if report.fmt == EDITOR:
        for ref in sorted(used_inputs - declared):
            report.add("error", "INPUT_UNDECLARED", "", f"${{input:{ref}}} is used but not declared in `inputs`", DOC_CONFIG)
        for ref in sorted(declared - used_inputs - {None}):
            report.add("warn", "INPUT_UNUSED", "", f"input '{ref}' is declared but never used", DOC_CONFIG)
    return report


def _env_name(input_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", input_id).strip("_").upper()


@dataclass
class Conversion:
    doc: dict
    notes: list[str] = field(default_factory=list)
    env_vars: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def to_native(doc: dict, add_tools_star: bool = False) -> Conversion:
    """Editor format (`servers`) to native Copilot format (`mcpServers`), following the documented differences."""
    if detect(doc) != EDITOR:
        raise ValueError("input is not an editor-format file (top-level `servers`)")
    leaked = [f for f in check(doc).findings if f.code == "SECRET_LITERAL"]
    if leaked:
        raise ValueError("refusing to convert: " + "; ".join(f"[{f.server}] {f.message}" for f in leaked)
                         + ". Remove the credential (and rotate it) before converting")
    result = Conversion(doc={"mcpServers": {}})
    inputs = {i.get("id"): i for i in doc.get("inputs", []) if isinstance(i, dict)}
    for name, original in doc["servers"].items():
        cfg = copy.deepcopy(original)
        if any(m.group(1).startswith("command:") for s in _strings(cfg) for m in VAR.finditer(s)):
            result.skipped.append(name)
            result.notes.append(f"[{name}] skipped: uses ${{command:...}}, which has no native equivalent (change it by hand)")
            continue
        if "type" not in cfg:
            cfg["type"] = "stdio" if "command" in cfg else "http"
            result.notes.append(f"[{name}] added type '{cfg['type']}'")
        for dropped in EDITOR_ONLY_FIELDS:
            if dropped in cfg:
                del cfg[dropped]
                result.notes.append(f"[{name}] dropped editor-only `{dropped}`")
        if "oauth" in cfg:
            oauth = cfg.pop("oauth")
            if isinstance(oauth, dict) and "clientId" in oauth:
                cfg["oauthClientId"] = oauth["clientId"]
                result.notes.append(f"[{name}] oauth.clientId -> oauthClientId (a client secret set in the editor does not move)")

        def rewrite(text: str, server=name) -> str:
            def sub(m: re.Match[str]) -> str:
                ref = m.group(1)
                if ref.startswith("input:"):
                    input_id = ref[len("input:"):]
                    var = _env_name(input_id)
                    if var not in result.env_vars:
                        result.env_vars.append(var)
                    kind = inputs.get(input_id, {})
                    extra = " (a password input: set it in the environment, never in the file)" if kind.get("password") else ""
                    result.notes.append(f"[{server}] ${{input:{input_id}}} -> ${{{var}}}: set {var} in the environment of the host that runs the harness{extra}")
                    return "${" + var + "}"
                if ref.startswith("env:"):
                    return "${" + ref[4:] + "}"
                return m.group(0)

            return VAR.sub(sub, text)

        def walk(value):
            if isinstance(value, str):
                return rewrite(value)
            if isinstance(value, dict):
                return {k: walk(v) for k, v in value.items()}
            if isinstance(value, list):
                return [walk(v) for v in value]
            return value

        cfg = walk(cfg)
        if add_tools_star and "tools" not in cfg:
            cfg["tools"] = ["*"]
        result.doc["mcpServers"][name] = cfg
    if doc.get("inputs"):
        result.notes.append("top-level `inputs` dropped: prompting is an editor feature")
    if doc.get("sandbox"):
        result.notes.append("top-level `sandbox` dropped: editor sandboxing is separate from the Copilot harness sandbox")
    return result


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
