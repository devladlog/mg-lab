"""Checks for Copilot customization files. Every rule names the Learn/VS Code page behind it."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from . import frontmatter
from .globmatch import matches, split_patterns

DOC_INSTR = "https://code.visualstudio.com/docs/agents/reference/custom-instructions-reference"
DOC_PROMPT = "https://code.visualstudio.com/docs/agent-customization/prompt-files"
DOC_SKILL = "https://code.visualstudio.com/docs/agent-customization/agent-skills"
DOC_AGENT = "https://code.visualstudio.com/docs/agents/reference/custom-agent-file-reference"
DOC_MOVE = "https://code.visualstudio.com/docs/agents/run/move-to-copilot"

INSTRUCTION_KEYS = {"name", "description", "applyTo", "excludeAgent"}
PROMPT_KEYS = {"description", "name", "argument-hint", "agent", "model", "tools"}
SKILL_KEYS = {"name", "description", "argument-hint", "user-invocable", "disable-model-invocation", "context"}
AGENT_KEYS = {
    "name", "description", "argument-hint", "advancedOptions", "tools", "agents", "model", "model-policy",
    "reasoning-effort", "skills", "deferred-tool-loading", "strict-tools-list", "include-custom-instructions",
    "github", "user-invocable", "disable-model-invocation", "infer", "target", "mcp-servers", "handoffs", "hooks",
}
AGENT_LOCAL_ONLY = {"handoffs", "agents", "argument-hint", "advancedOptions"}
AGENT_COPILOT_ONLY = {"skills", "mcp-servers"}
BUILTIN_AGENTS = {"ask", "agent", "plan"}
COPILOT_TOOL_ALIASES = {"execute", "read", "edit", "search", "agent", "web", "todo", "*"}
SKILL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
LINK = re.compile(r"\]\(([^)\s#]+)(?:#[^)]*)?\)|#file:(\S+)")


@dataclass(frozen=True)
class Finding:
    severity: str  # error | warn | info
    code: str
    path: str
    message: str
    doc: str = ""

    def line(self) -> str:
        return f"{self.severity.upper():5} {self.code:<22} {self.path}: {self.message}"


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)

    def add(self, severity: str, code: str, path: str, message: str, doc: str = "") -> None:
        self.findings.append(Finding(severity, code, path, message, doc))

    def count(self, severity: str) -> int:
        return sum(1 for f in self.findings if f.severity == severity)


def _repo_files(root: Path) -> list[str]:
    skip = {".git", "node_modules", "__pycache__", ".pytest_cache", ".venv"}
    files = []
    for p in root.rglob("*"):
        if p.is_file() and not (set(p.relative_to(root).parts) & skip):
            files.append(p.relative_to(root).as_posix())
    return sorted(files)


def _unknown_keys(report: Report, rel: str, meta: dict, known: set[str], doc: str) -> None:
    for key in meta:
        if key not in known:
            report.add("warn", "UNKNOWN_KEY", rel, f"'{key}' is not a documented field here", doc)


def _check_links(report: Report, root: Path, file: Path, body: str, rel: str, doc: str) -> None:
    for m in LINK.finditer(body):
        target = m.group(1) or m.group(2)
        if not target or re.match(r"^[a-z][a-z0-9+.-]*:", target) or target.startswith(("~", "${")):
            continue
        if "\\" in target:
            report.add("warn", "LINK_BACKSLASH", rel, f"use '/' separators in '{target}'", doc)
            target = target.replace("\\", "/")
        if not (file.parent / target).resolve().exists():
            report.add("error", "LINK_BROKEN", rel, f"referenced file '{target}' does not exist", doc)


def check_repo(root: Path) -> Report:
    root = root.resolve()
    report = Report()
    files = _repo_files(root)
    github = root / ".github"

    # Project instructions
    project = [p for p in (github / "copilot-instructions.md", root / "AGENTS.md") if p.exists()]
    if not project:
        report.add("info", "NO_PROJECT_FILE", ".", "no .github/copilot-instructions.md or AGENTS.md", DOC_INSTR)
    if len(project) == 2:
        report.add("warn", "TWO_PROJECT_FILES", ".",
                   "both .github/copilot-instructions.md and AGENTS.md exist; there is no precedence rule, keep them consistent", DOC_INSTR)
    for p in project:
        rel = p.relative_to(root).as_posix()
        parsed = frontmatter.parse(p.read_text(encoding="utf-8"))
        if not parsed.body.strip():
            report.add("warn", "EMPTY_FILE", rel, "file is empty", DOC_INSTR)
        if parsed.meta is not None:
            report.add("info", "FRONTMATTER_IGNORED", rel, "project instruction files need no YAML header", DOC_INSTR)
        _check_links(report, root, p, parsed.body, rel, DOC_INSTR)

    # Targeted instructions
    instr_dir = github / "instructions"
    instruction_files = sorted(instr_dir.rglob("*.instructions.md")) if instr_dir.is_dir() else []
    if instr_dir.is_dir():
        for p in sorted(instr_dir.rglob("*.md")):
            if not p.name.endswith(".instructions.md"):
                report.add("warn", "WRONG_SUFFIX", p.relative_to(root).as_posix(),
                           "files in .github/instructions must end with .instructions.md", DOC_INSTR)
    for p in instruction_files:
        rel = p.relative_to(root).as_posix()
        parsed = frontmatter.parse(p.read_text(encoding="utf-8"))
        if parsed.error:
            report.add("error", "BAD_HEADER", rel, parsed.error, DOC_INSTR)
            continue
        meta = parsed.meta or {}
        _unknown_keys(report, rel, meta, INSTRUCTION_KEYS, DOC_INSTR)
        if not parsed.body.strip():
            report.add("warn", "EMPTY_FILE", rel, "no instructions after the header", DOC_INSTR)
        apply_to = meta.get("applyTo")
        if apply_to is None:
            if meta.get("description"):
                report.add("info", "DESCRIPTION_ONLY", rel,
                           "no applyTo: only a Local session can load this by description; use applyTo for file-scoped guidance", DOC_INSTR)
            else:
                report.add("info", "MANUAL_ONLY", rel, "no applyTo and no description: attach it manually", DOC_INSTR)
        elif not isinstance(apply_to, str):
            report.add("error", "APPLYTO_TYPE", rel,
                       "applyTo must be one string; separate several patterns with commas, not a YAML list", DOC_INSTR)
        else:
            patterns = split_patterns(apply_to)
            for pat in patterns:
                if "\\" in pat:
                    report.add("warn", "APPLYTO_BACKSLASH", rel, f"use '/' in pattern '{pat}'", DOC_INSTR)
                if pat.startswith((".github/instructions", "../", "./")):
                    report.add("warn", "APPLYTO_RELATIVE", rel,
                               f"pattern '{pat}' is relative to the workspace root, not to the instructions folder", DOC_INSTR)
            if not any(matches(apply_to, f) for f in files):
                report.add("warn", "APPLYTO_NO_MATCH", rel, f"applyTo '{apply_to}' matches no file in this repository", DOC_INSTR)
        _check_links(report, root, p, parsed.body, rel, DOC_INSTR)

    # Custom agents
    agent_names: set[str] = set()
    agents_dir = github / "agents"
    agent_files = []
    if agents_dir.is_dir():
        for p in sorted(agents_dir.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(root).as_posix()
            if p.name.endswith(".chatmode.md"):
                report.add("warn", "CHATMODE", rel, "custom chat modes were renamed: rename to .agent.md", DOC_AGENT)
            elif p.suffix == ".md":
                agent_files.append(p)
    for p in agent_files:
        rel = p.relative_to(root).as_posix()
        parsed = frontmatter.parse(p.read_text(encoding="utf-8"))
        if parsed.error:
            report.add("error", "BAD_HEADER", rel, parsed.error, DOC_AGENT)
            continue
        meta = parsed.meta or {}
        agent_names.add(str(meta.get("name") or p.name.removesuffix(".agent.md").removesuffix(".md")))
        _unknown_keys(report, rel, meta, AGENT_KEYS, DOC_AGENT)
        if not meta.get("description"):
            report.add("warn", "AGENT_NO_DESC", rel, "description is required by the Copilot schema", DOC_AGENT)
        if "infer" in meta:
            report.add("warn", "AGENT_INFER", rel, "'infer' is deprecated: use user-invocable and disable-model-invocation", DOC_AGENT)
        for key in sorted(AGENT_LOCAL_ONLY & set(meta)):
            report.add("info", "AGENT_LOCAL_ONLY", rel, f"'{key}' is not accepted by the Copilot schema (Local only)", DOC_AGENT)
        for key in sorted(AGENT_COPILOT_ONLY & set(meta)):
            report.add("info", "AGENT_COPILOT_ONLY", rel, f"'{key}' is not accepted by Local (Copilot only)", DOC_AGENT)
        tools = meta.get("tools")
        if tools is not None:
            items = [tools] if isinstance(tools, str) else tools
            if not isinstance(items, list) or not all(isinstance(t, str) for t in items):
                report.add("error", "TOOLS_TYPE", rel, "tools must be a string or a list of strings", DOC_AGENT)
            else:
                for t in items:
                    if t not in COPILOT_TOOL_ALIASES and "/" not in t:
                        report.add("warn", "TOOL_UNKNOWN", rel,
                                   f"tool '{t}' is not a Copilot alias (execute, read, edit, search, agent, web, todo, *) or a qualified name", DOC_AGENT)

    # Prompt files
    prompts_dir = github / "prompts"
    for p in sorted(prompts_dir.rglob("*.prompt.md")) if prompts_dir.is_dir() else []:
        rel = p.relative_to(root).as_posix()
        report.add("info", "PROMPT_LOCAL_ONLY", rel,
                   "prompt files run only in Local harness sessions, which are deprecated (removal February 2027); convert to a skill", DOC_PROMPT)
        parsed = frontmatter.parse(p.read_text(encoding="utf-8"))
        if parsed.error:
            report.add("error", "BAD_HEADER", rel, parsed.error, DOC_PROMPT)
            continue
        meta = parsed.meta or {}
        _unknown_keys(report, rel, meta, PROMPT_KEYS, DOC_PROMPT)
        agent = meta.get("agent")
        if agent is not None and agent not in BUILTIN_AGENTS and agent not in agent_names:
            report.add("error", "AGENT_UNKNOWN", rel,
                       f"agent '{agent}' is not ask, agent, plan or a custom agent in .github/agents", DOC_PROMPT)
        if "tools" in meta and not (isinstance(meta["tools"], list) and all(isinstance(t, str) for t in meta["tools"])):
            report.add("error", "TOOLS_TYPE", rel, "tools must be a list of strings", DOC_PROMPT)
        if not parsed.body.strip():
            report.add("warn", "EMPTY_FILE", rel, "prompt body is empty", DOC_PROMPT)
        _check_links(report, root, p, parsed.body, rel, DOC_PROMPT)

    # Skills
    skills_dir = github / "skills"
    for p in sorted(skills_dir.glob("*/SKILL.md")) if skills_dir.is_dir() else []:
        rel = p.relative_to(root).as_posix()
        parsed = frontmatter.parse(p.read_text(encoding="utf-8"))
        if parsed.error or parsed.meta is None:
            report.add("error", "BAD_HEADER", rel, parsed.error or "SKILL.md needs a YAML header with name and description", DOC_SKILL)
            continue
        meta = parsed.meta
        _unknown_keys(report, rel, meta, SKILL_KEYS, DOC_SKILL)
        name = meta.get("name")
        if not isinstance(name, str) or not name:
            report.add("error", "SKILL_NAME", rel, "name is required", DOC_SKILL)
        else:
            if not SKILL_NAME.match(name) or len(name) > 64:
                report.add("error", "SKILL_NAME", rel,
                           f"name '{name}' must be lowercase letters, numbers and hyphens, 64 characters at most "
                           "(invalid names make the skill silently fail to load)", DOC_SKILL)
            if name != p.parent.name:
                report.add("error", "SKILL_DIR", rel, f"name '{name}' must match the directory '{p.parent.name}'", DOC_SKILL)
        desc = meta.get("description")
        if not isinstance(desc, str) or not desc.strip():
            report.add("error", "SKILL_DESC", rel, "description is required (what it does and when to use it)", DOC_SKILL)
        elif len(desc) > 1024:
            report.add("error", "SKILL_DESC", rel, f"description has {len(desc)} characters; the maximum is 1024", DOC_SKILL)
        if meta.get("context") not in (None, "fork"):
            report.add("error", "SKILL_CONTEXT", rel, "context only accepts 'fork'", DOC_SKILL)
        if meta.get("user-invocable") is False and meta.get("disable-model-invocation") is True:
            report.add("warn", "SKILL_DISABLED", rel, "user-invocable: false and disable-model-invocation: true disable the skill", DOC_SKILL)
        _check_links(report, root, p, parsed.body, rel, DOC_SKILL)

    return report


def explain(root: Path, relpath: str) -> list[str]:
    """Which instruction files would apply when the agent works on `relpath` (Copilot harness rules)."""
    root = root.resolve()
    hits = []
    for name in (".github/copilot-instructions.md", "AGENTS.md"):
        if (root / name).exists():
            hits.append(f"{name} (project-wide)")
    instr_dir = root / ".github" / "instructions"
    for p in sorted(instr_dir.rglob("*.instructions.md")) if instr_dir.is_dir() else []:
        meta = frontmatter.parse(p.read_text(encoding="utf-8")).meta or {}
        apply_to = meta.get("applyTo")
        if isinstance(apply_to, str) and matches(apply_to, relpath):
            hits.append(f"{p.relative_to(root).as_posix()} (applyTo: {apply_to})")
    return hits
