"""Convert a Local-harness prompt file into an agent skill.

The VS Code migration page says conversion adds `disable-model-invocation: true` (explicit invocation is
kept) and that a skill does not preserve a prompt's `agent`, `model` or `tools`. This does the same on
files and reports exactly what was lost, so the person can re-check it.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import frontmatter
from .rules import LINK

DROPPED = ("agent", "model", "tools")


@dataclass
class Conversion:
    skill_dir: Path
    skill_file: Path
    notes: list[str] = field(default_factory=list)


def skill_name_from(prompt_path: Path, meta: dict) -> str:
    raw = str(meta.get("name") or prompt_path.name.removesuffix(".prompt.md"))
    name = re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-")[:64].strip("-")
    if not name:
        raise ValueError(f"cannot derive a skill name from '{raw}'")
    return name


def _rebase_links(body: str, old_dir: Path, new_dir: Path) -> str:
    def fix(match: re.Match[str]) -> str:
        text = match.group(0)
        target = match.group(1) or match.group(2)
        if not target or re.match(r"^[a-z][a-z0-9+.-]*:", target) or target.startswith(("~", "${")):
            return text
        absolute = (old_dir / target).resolve()
        rebased = Path(os.path.relpath(absolute, new_dir)).as_posix()
        return text.replace(target, rebased)

    return LINK.sub(fix, body)


def prompt_to_skill(prompt_path: Path, skills_root: Path) -> Conversion:
    parsed = frontmatter.parse(prompt_path.read_text(encoding="utf-8"))
    if parsed.error:
        raise ValueError(f"{prompt_path.name}: {parsed.error}")
    meta = parsed.meta or {}
    name = skill_name_from(prompt_path, meta)
    skill_dir = skills_root / name
    if skill_dir.exists():
        raise FileExistsError(f"{skill_dir} already exists; the converter never overwrites")
    notes: list[str] = []
    description = str(meta.get("description") or "").strip()
    if not description:
        first = next((ln.strip() for ln in parsed.body.splitlines() if ln.strip()), "")
        description = first[:1024]
        notes.append("no description in the prompt: used its first line; a skill description should say what it does and when to use it")
    header: dict = {"name": name, "description": description}
    if meta.get("argument-hint"):
        header["argument-hint"] = meta["argument-hint"]
    header["disable-model-invocation"] = True
    for key in DROPPED:
        if key in meta:
            notes.append(f"'{key}: {meta[key]}' is not preserved by a skill: check the agent, model and tool choice in the Copilot session")
    if "${input:" in parsed.body:
        notes.append("the body uses ${input:...} variables: run the skill once and check that the agent still asks for them")
    if "#tool:" in parsed.body:
        notes.append("the body references #tool:...: check that the tool exists in the Copilot harness")
    if name != skill_name_from(prompt_path, {}) and not meta.get("name"):
        notes.append(f"skill name normalised to '{name}'")
    body = _rebase_links(parsed.body, prompt_path.parent, skill_dir)
    skill_dir.mkdir(parents=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        "---\n" + yaml.safe_dump(header, sort_keys=False, allow_unicode=True, width=1000) + "---\n\n" + body.rstrip() + "\n",
        encoding="utf-8",
    )
    return Conversion(skill_dir, skill_file, notes)
