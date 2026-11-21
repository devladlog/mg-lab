"""Turn interactions into the numbers an admin asks for first."""
from __future__ import annotations

from collections import Counter
from datetime import datetime

from .parse import Interaction


def load_user_list(text: str) -> set[str]:
    """One UPN per line (also accepts commas); blank lines and # comments ignored."""
    users: set[str] = set()
    for line in text.splitlines():
        line = line.split("#", 1)[0]
        for part in line.replace(",", " ").split():
            users.add(part.strip().lower())
    return users


def summarise(items: list[Interaction], licensed: set[str] | None = None, since: datetime | None = None) -> dict:
    if since is not None:
        items = [i for i in items if i.created and i.created >= since]
    total = len(items)
    users = Counter(i.user for i in items)
    hosts = Counter(i.app_host or "(none)" for i in items)
    identities = Counter(i.app_identity or "(none)" for i in items)
    agents = Counter((i.agent_name or i.agent_id) for i in items if i.agent_name or i.agent_id)
    models = Counter(m for i in items for m in i.models)
    web = sum(1 for i in items if i.web_search)
    summary = {
        "interactions": total,
        "users": len(users),
        "threads": len({i.thread_id for i in items if i.thread_id}),
        "byUser": dict(users.most_common()),
        "byAppHost": dict(hosts.most_common()),
        "byAppIdentity": dict(identities.most_common()),
        "webSearch": {"count": web, "share": round(web / total, 3) if total else 0.0},
        "withAccessedResources": sum(1 for i in items if i.resources),
        "withSensitivityLabels": sum(1 for i in items if i.labelled_resources),
        "agents": dict(agents.most_common()),
        "models": dict(models.most_common()),
        "flags": {
            "jailbreakDetected": sum(1 for i in items if i.jailbreak),
            "xpiaDetected": sum(1 for i in items if i.xpia),
            "dlpEvaluationDeferred": sum(1 for i in items if i.dlp_deferred),
        },
    }
    if licensed is not None:
        lic = [i for i in items if i.user in licensed]
        summary["licence"] = {
            "licensedInteractions": len(lic),
            "unlicensedInteractions": total - len(lic),
            "unlicensedUsers": sorted(u for u in users if u not in licensed),
        }
    return summary


def format_text(s: dict) -> str:
    lines = [
        f"Copilot interactions: {s['interactions']} by {s['users']} user(s) in {s['threads']} thread(s)",
        f"Web search used: {s['webSearch']['count']} ({s['webSearch']['share']:.0%})",
        f"Touched organisational files: {s['withAccessedResources']} (with a sensitivity label: {s['withSensitivityLabels']})",
        "",
        "By app host:",
    ]
    lines += [f"  {k:<16} {v}" for k, v in s["byAppHost"].items()]
    lines.append("By user:")
    lines += [f"  {k:<28} {v}" for k, v in s["byUser"].items()]
    if s["agents"]:
        lines.append("Agents:")
        lines += [f"  {k:<28} {v}" for k, v in s["agents"].items()]
    if s["models"]:
        lines.append("Model providers:")
        lines += [f"  {k:<28} {v}" for k, v in s["models"].items()]
    flags = s["flags"]
    lines.append(
        f"Flags: jailbreak {flags['jailbreakDetected']}, XPIA {flags['xpiaDetected']}, "
        f"DLP evaluation deferred {flags['dlpEvaluationDeferred']}"
    )
    if "licence" in s:
        lic = s["licence"]
        lines.append(
            f"Licence split: {lic['licensedInteractions']} licensed, {lic['unlicensedInteractions']} unlicensed "
            f"(unlicensed users: {', '.join(lic['unlicensedUsers']) or 'none'})"
        )
    return "\n".join(lines)
