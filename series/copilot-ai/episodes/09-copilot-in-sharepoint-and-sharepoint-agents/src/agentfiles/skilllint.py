"""Lint a Markdown skill file before you upload it as a Copilot in SharePoint site skill.

What Learn documents about site skills (https://learn.microsoft.com/sharepoint/copilot-in-sharepoint-skills): they are
Markdown files stored at /Agent Assets/Skills/<skill-name>/SKILL.md and "if you edit the .md skill file directly, keep
the format intact". Learn does not publish a SharePoint-specific schema. The rules below are the documented rules for the
same SKILL.md format in other Microsoft products, and every finding names the page it comes from:
  CS  = Copilot Studio, "Add and manage an uploaded skill" (load-time checks: valid YAML front matter, name, description,
        single-line description, UTF-8 without BOM)
        https://learn.microsoft.com/microsoft-copilot-studio/agents-experience/skills-add-existing
  AB  = Agent Builder, "Add skills to your declarative agent" (instructions under 20,000 characters)
        https://learn.microsoft.com/plugins/agent-builder-add-skills
  AS  = Agent Skills in Visual Studio (name: lowercase letters, numbers, hyphens, at most 64, matches the folder;
        description at most 1,024 characters; keep SKILL.md under 500 lines)
        https://learn.microsoft.com/visualstudio/ide/copilot-agent-skills
So a clean result means "valid by the documented rules", not "accepted by SharePoint": the tenant is the final test.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_NAME = 64
MAX_DESCRIPTION = 1024
MAX_BODY = 20_000
MAX_LINES = 500


@dataclass(frozen=True)
class Finding:
    level: str   # "error" or "warning"
    rule: str
    message: str
    source: str  # CS, AB, AS


def split_front_matter(text: str) -> tuple[str | None, str]:
    """Return (front matter text or None, body)."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, text
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[1:i]), "\n".join(lines[i + 1:])
    return None, text


def lint_text(text: str, folder_name: str | None = None) -> list[Finding]:
    findings: list[Finding] = []
    fm_text, body = split_front_matter(text)
    if fm_text is None:
        return [Finding("error", "front-matter", "No YAML front matter block (--- ... ---) at the top of the file", "CS")]
    try:
        meta = yaml.safe_load(fm_text)
    except yaml.YAMLError as exc:
        first = str(exc).splitlines()[0] if str(exc) else "invalid YAML"
        return [Finding("error", "front-matter", f"Invalid YAML front matter ({first}). Quote values that contain a colon, "
                                                 "for example description: \"My: skill\"", "CS")]
    if not isinstance(meta, dict):
        return [Finding("error", "front-matter", "Front matter must be a mapping of key: value pairs", "CS")]

    name = meta.get("name")
    desc = meta.get("description")
    if not isinstance(name, str) or not name.strip():
        findings.append(Finding("error", "name", "Missing or empty name", "CS"))
    else:
        if len(name) > MAX_NAME or not NAME_RE.match(name):
            findings.append(Finding("warning", "name-format", f"name '{name}' should use lowercase letters, numbers and "
                                    f"hyphens only, at most {MAX_NAME} characters", "AS"))
        if folder_name and name != folder_name:
            findings.append(Finding("warning", "name-folder", f"name '{name}' does not match the folder '{folder_name}' "
                                    "(the site skill path is /Agent Assets/Skills/<skill-name>/SKILL.md)", "AS"))
    if not isinstance(desc, str) or not desc.strip():
        findings.append(Finding("error", "description", "Missing or empty description", "CS"))
    else:
        if "\n" in desc.strip():
            findings.append(Finding("warning", "description-lines", "Description spans several lines: use a single-line "
                                    "summary of the skill's purpose", "CS"))
        if len(desc) > MAX_DESCRIPTION:
            findings.append(Finding("error", "description-length", f"Description has {len(desc)} characters; the limit "
                                    f"is {MAX_DESCRIPTION}", "AS"))
    if not body.strip():
        findings.append(Finding("error", "body", "No instructions after the front matter", "CS"))
    if len(body) >= MAX_BODY:
        findings.append(Finding("error", "body-length", f"Instructions have {len(body)} characters; keep them under "
                                f"{MAX_BODY}", "AB"))
    if len(text.splitlines()) > MAX_LINES:
        findings.append(Finding("warning", "lines", f"More than {MAX_LINES} lines: move detail to separate files", "AS"))
    return findings


def lint_file(path: Path) -> list[Finding]:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        return [Finding("error", "encoding", "File starts with a UTF-8 byte-order mark: save as UTF-8 without BOM", "CS")]
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return [Finding("error", "encoding", "File is not valid UTF-8", "CS")]
    folder = path.parent.name if path.name.lower() == "skill.md" else None
    return lint_text(text, folder)
