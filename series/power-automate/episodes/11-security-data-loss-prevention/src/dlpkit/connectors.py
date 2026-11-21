"""Connector identity and the connectors that data policies can't block.

A connector id in a data policy looks like `/providers/Microsoft.PowerApps/apis/shared_sharepointonline`;
a flow definition calls the same connector `shared_sharepointonline`. We compare the last segment,
lower-cased, so both spellings meet.
"""
from __future__ import annotations

PREFIX = "/providers/Microsoft.PowerApps/apis/"

# The built-in HTTP action. Learn's endpoint-filtering example uses the connector id "http" for it; the ids
# of "HTTP Webhook" and "When an HTTP request is received" are not on Learn, so dlpkit reports them as
# "not evaluated" instead of guessing.
HTTP = "http"


def norm_id(raw: str) -> str:
    return raw.rstrip("/").rsplit("/", 1)[-1].lower()


# Display names for the connectors our flows and tests use (names as Learn writes them).
NAMES = {
    "shared_sharepointonline": "SharePoint",
    "shared_office365": "Microsoft 365 Outlook",
    "shared_office365users": "Microsoft 365 Users",
    "shared_teams": "Microsoft Teams",
    "shared_approvals": "Approvals",
    "shared_commondataserviceforapps": "Dataverse",
    "shared_excelonlinebusiness": "Excel Online (Business)",
    "shared_msnweather": "MSN Weather",
    HTTP: "HTTP",
}

# "List of connectors that you can't block" (Learn: Connector classification). They can be Business or
# Non-business, never Blocked. The ids follow the convention shared_<slug of the connector's reference
# page on Learn> (the Approvals, Notifications, Dataverse and Dataverse (legacy) links in that table confirm
# the slugs approvals, flowpush, commondataserviceforapps and commondataservice).
UNBLOCKABLE = {
    "shared_commondataserviceforapps", "shared_commondataservice", "shared_approvals", "shared_flowpush",
    "shared_powerappsnotification", "shared_powerappsnotificationv2",
    "shared_excelonlinebusiness", "shared_office365groups", "shared_office365", "shared_office365users",
    "shared_teams", "shared_onedriveforbusiness", "shared_onenote", "shared_planner", "shared_powerbi",
    "shared_sharepointonline", "shared_yammer",
}
# Also on that list, whose ids we did not write down because we could not confirm the slug:
# Defender for Cloud Apps, Dynamics 365 Customer Voice, Kaizala, Microsoft 365 Groups Mail, Microsoft To-Do
# (Business), Shifts, Skype for Business Online, Microsoft Copilot Studio.


def display(cid: str, names: dict[str, str] | None = None) -> str:
    cid = norm_id(cid)
    return (names or {}).get(cid) or NAMES.get(cid) or cid
