"""Which Microsoft licence model does a declarative agent need? Source: the table 'Agent capabilities and licensing
models' on Learn (Set up your development environment for your plugin, read 21 Nov 2026).

Tiers, lowest to highest:
  0 all          Copilot Chat without usage-based billing is enough
  1 payg         needs usage-based billing (Copilot Credits) or a Microsoft 365 Copilot licence
  2 licensed     needs a Microsoft 365 Copilot licence (metered usage alone does not help)
Capabilities that Learn's table does not list are reported as 'unlisted': check Learn, do not assume."""
from __future__ import annotations

import json
from pathlib import Path

TIERS = ["all", "payg", "licensed"]

# capability name in the manifest -> (table row on Learn, tier)
CAPABILITY_TIER = {
    "WebSearch": ("Custom knowledge: Web search / Scoped web search", "all"),
    "GraphicArt": ("Image generator", "all"),
    "CodeInterpreter": ("Code interpreter", "all"),
    "GraphConnectors": ("Custom knowledge: Copilot connectors", "payg"),
    "OneDriveAndSharePoint": ("Custom knowledge: SharePoint data", "payg"),
    "EmbeddedKnowledge": ("Custom knowledge: Embedded file content", "payg"),
    "Dataverse": ("Custom knowledge: Dataverse", "payg"),
    "Email": ("Custom knowledge: Email", "licensed"),
    "People": ("Custom knowledge: People", "licensed"),
    "TeamsMessages": ("Custom knowledge: Teams messages", "licensed"),
    "Meetings": ("Custom knowledge: Teams meetings", "licensed"),
}
# manifest sections that Learn lists as available to all: custom actions, custom instructions
ALWAYS_ALL = {"actions": "Custom actions", "instructions": "Custom instructions"}


def assess(agent: dict) -> dict:
    rows, unlisted = [], []
    for part, label in ALWAYS_ALL.items():
        if agent.get(part):
            rows.append({"item": part, "learn_row": label, "tier": "all"})
    for cap in agent.get("capabilities", []):
        name = cap.get("name")
        if name in CAPABILITY_TIER:
            label, tier = CAPABILITY_TIER[name]
            rows.append({"item": name, "learn_row": label, "tier": tier})
        else:
            unlisted.append(name)
    needed = max((TIERS.index(r["tier"]) for r in rows), default=0)
    return {"needs": TIERS[needed], "rows": rows, "unlisted": unlisted}


def render(result: dict) -> str:
    text = {"all": "Copilot Chat without usage-based billing is enough (no Copilot licence, no billing policy).",
            "payg": "Needs usage-based billing (Copilot Credits) or a Microsoft 365 Copilot licence.",
            "licensed": "Needs a Microsoft 365 Copilot licence."}
    lines = [f"Required: {result['needs']}  -  {text[result['needs']]}", ""]
    for r in result["rows"]:
        lines.append(f"  {r['tier']:8} {r['item']:22} (Learn row: {r['learn_row']})")
    for name in result["unlisted"]:
        lines.append(f"  unlisted {name}: not in Learn's licensing table, check the capability's own Learn page")
    return "\n".join(lines)


def assess_file(path: Path) -> dict:
    return assess(json.loads(Path(path).read_text(encoding="utf-8")))
