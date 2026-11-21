"""Turn the inventory plus a human triage sheet into an upgrade plan for each .agent file.

Source for every rule: Microsoft Learn, "Upgrade agents in SharePoint and OneDrive"
https://learn.microsoft.com/sharepoint/upgrade-sharepoint-agents
  * the table "Agent role -> Recommended path" (the four ROLES below);
  * "On SharePoint sites, prioritize agents with high usage, broad audiences, business-critical scenarios, custom
    instructions, pay-as-you-go dependencies, Teams distribution, or prominent SharePoint placement" (the FACTORS);
  * "consider reviewing agents with no recent use or no clear owner for archival or deletion, instead of upgrading them".
What is ours, not Learn's: the numeric thresholds (HIGH_VIEWS, STALE_DAYS), the score-to-priority mapping and the choice
of 31 March 2027 as the date to plan against (Learn says "after March 2027" and "end of March 2027").
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .inventory import AgentFile, normalize_path

# Learn: ".agent files stop responding to prompts after March 2027". We plan against the last day of that month.
DEADLINE = date(2027, 3, 31)
HIGH_VIEWS = 50       # our threshold for "high usage" (lifetime views); tune it for your tenant
STALE_DAYS = 90       # our threshold for "no recent use"

LEARN = "https://learn.microsoft.com/sharepoint/upgrade-sharepoint-agents"

# role -> (recommended path as Learn names it, next steps taken from the same article)
ROLES: dict[str, tuple[str, list[str]]] = {
    "site-qa": (
        "Use Copilot in SharePoint directly",
        ["Check the intended users have a Microsoft Copilot licence and that Copilot is available on the site",
         "Settings > Site AI: set Copilot as the Main agent for the site",
         "Delete the .agent file (it goes to the recycle bin)"],
    ),
    "site-task": (
        "Convert the agent to a skill",
        ["Prompt Copilot in SharePoint to use the convert-agent-file-to-skill skill (rolling out from mid-November 2026) "
         "with the .agent file, and choose a site or a personal skill",
         "Optional: add a Button web part that opens Copilot with the skill's prompt",
         "Delete the .agent file after the conversion"],
    ),
    "cross-qa": (
        "Upgrade with Microsoft Copilot Agent Builder",
        ["Note who has access and where the agent is used",
         "Edit the .agent file and select Upgrade to Microsoft 365 agent (from mid-November 2026)",
         "Share the upgraded agent (it is private unless the .agent file was shared with everyone in the organisation) "
         "and check users also reach the knowledge sources",
         "Add it to the page with the Agent Chat web part (announced as coming soon) and set Copilot as Main agent"],
    ),
    "studio-custom-engine": (
        "Publish the existing Copilot Studio agent to Microsoft Copilot app",
        ["Do not rebuild it: review its publishing configuration in Copilot Studio",
         "Publish it to the Microsoft Copilot app and the Teams channel",
         "Delete the .agent file after the agent is on the page with the Agent Chat web part"],
    ),
}
UNKNOWN_PATH = "Triage needed: ask the owner what the agent is for"
ARCHIVE_PATH = "Review for archival or deletion (no recent use or no clear owner)"

# Learn's prioritisation factors. 'high usage' is computed from the inventory; the others come from the triage sheet.
FACTORS = ["high_usage", "broad_audience", "business_critical", "custom_instructions", "payg", "teams", "prominent"]
TRIAGE_COLUMNS = ["Path", "Role", "Audience", "BusinessCritical", "CustomInstructions", "PayAsYouGo", "TeamsChat",
                  "ProminentPlacement", "Owner"]


@dataclass
class TriageRow:
    role: str = ""
    broad_audience: bool = False
    business_critical: bool = False
    custom_instructions: bool = False
    payg: bool = False
    teams: bool = False
    prominent: bool = False
    owner: str = ""


@dataclass
class PlanItem:
    file: AgentFile
    role: str
    path_name: str
    steps: list[str]
    factors: list[str]
    priority: str
    archive_candidate: bool
    days_left: int
    notes: list[str] = field(default_factory=list)

    @property
    def score(self) -> int:
        return len(self.factors)


def _yes(value: str) -> bool:
    return (value or "").strip().lower() in {"y", "yes", "true", "1", "x"}


def read_triage(path: Path) -> dict[str, TriageRow]:
    rows: dict[str, TriageRow] = {}
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for raw in csv.DictReader(fh):
            r = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
            if not r.get("path"):
                continue
            role = r.get("role", "").lower()
            if role and role not in ROLES:
                raise ValueError(f"Triage role '{role}' for {r['path']} is not one of: {', '.join(ROLES)}")
            rows[normalize_path(r["path"])] = TriageRow(
                role=role,
                broad_audience=_yes(r.get("audience", "")) or r.get("audience", "").lower() == "broad",
                business_critical=_yes(r.get("businesscritical", "")),
                custom_instructions=_yes(r.get("custominstructions", "")),
                payg=_yes(r.get("payasyougo", "")),
                teams=_yes(r.get("teamschat", "")),
                prominent=_yes(r.get("prominentplacement", "")),
                owner=r.get("owner", ""),
            )
    return rows


def write_triage_template(files: list[AgentFile], out: Path) -> None:
    """One row per agent for the owners to fill in: this is the part search cannot know."""
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(TRIAGE_COLUMNS)
        for f in sorted(files, key=lambda x: x.path.lower()):
            w.writerow([f.path, "", "", "", "", "", "", "", f.owner])


def priority_for(score: int) -> str:
    # Our mapping: three or more of Learn's seven factors is high, one or two medium.
    return "high" if score >= 3 else "medium" if score >= 1 else "low"


def build_plan(files: list[AgentFile], triage: dict[str, TriageRow], today: date,
               high_views: int = HIGH_VIEWS, stale_days: int = STALE_DAYS) -> list[PlanItem]:
    items: list[PlanItem] = []
    for f in files:
        t = triage.get(f.key, TriageRow())
        factors: list[str] = []
        if f.views_lifetime >= high_views:
            factors.append("high_usage")
        for name, on in (("broad_audience", t.broad_audience), ("business_critical", t.business_critical),
                         ("custom_instructions", t.custom_instructions), ("payg", t.payg),
                         ("teams", t.teams), ("prominent", t.prominent)):
            if on:
                factors.append(name)
        owner = t.owner or f.owner
        unused = f.views_recent == 0 and f.modified is not None and (today - f.modified).days > stale_days
        archive = (unused or not owner) and not (t.business_critical or t.payg or t.teams or t.prominent)
        notes: list[str] = []
        if t.role in ROLES:
            path_name, steps = ROLES[t.role]
        elif archive:
            path_name, steps = ARCHIVE_PATH, ["Ask the site owner whether the agent is still needed",
                                              "If not, delete the .agent file (recycle bin) instead of upgrading it"]
        else:
            path_name, steps = UNKNOWN_PATH, ["Fill in the Role column of the triage sheet"]
        if t.role in ROLES and archive:
            notes.append("Little or no use and no clear owner: consider deleting instead of upgrading")
        if t.teams:
            notes.append("Used in a Teams chat: upgrade all agents in that chat at the same time and add the upgraded "
                         "agent again (Learn)")
        if t.payg:
            notes.append("SharePoint agents pay-as-you-go only applies to .agent files; upgraded agents follow the "
                         "Copilot app licensing model (Learn)")
        items.append(PlanItem(f, t.role or "(not triaged)", path_name, steps, factors, priority_for(len(factors)),
                              archive, (DEADLINE - today).days, notes))
    order = {"high": 0, "medium": 1, "low": 2}
    items.sort(key=lambda i: (order[i.priority], -i.score, -i.file.views_lifetime, i.file.path.lower()))
    return items


def render_markdown(items: list[PlanItem], today: date) -> str:
    left = (DEADLINE - today).days
    out = [f"# .agent file upgrade plan ({today.isoformat()})", "",
           f"Planning date: {DEADLINE.isoformat()} ({left} days left). Learn: .agent files stop responding after March 2027.",
           f"Source: {LEARN}", "",
           "| Priority | Agent | Site | Views | Role | Recommended path |", "|---|---|---|---|---|---|"]
    for i in items:
        f = i.file
        out.append(f"| {i.priority} | {f.title} | {f.site_title or f.site_url} | {f.views_lifetime} | {i.role} | {i.path_name} |")
    out.append("")
    for i in items:
        if i.priority == "high" or i.notes:
            out.append(f"## {i.file.title} ({i.priority})")
            out.append("Factors: " + (", ".join(i.factors) or "none"))
            out += [f"{n}. {s}" for n, s in enumerate(i.steps, 1)]
            out += [f"Note: {n}" for n in i.notes]
            out.append("")
    return "\n".join(out)


def render_csv(items: list[PlanItem], out) -> None:
    w = csv.writer(out)
    w.writerow(["Priority", "Title", "Path", "Site", "Role", "RecommendedPath", "Factors", "ArchiveCandidate", "DaysLeft"])
    for i in items:
        w.writerow([i.priority, i.file.title, i.file.path, i.file.site_title or i.file.site_url, i.role, i.path_name,
                    ";".join(i.factors), "yes" if i.archive_candidate else "no", i.days_left])
