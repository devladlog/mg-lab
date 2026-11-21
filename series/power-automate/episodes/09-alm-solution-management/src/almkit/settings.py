"""Deployment settings files (Learn: "Pre-populate connection references and environment variables").

Shape: {"EnvironmentVariables": [{"SchemaName", "Value"}], "ConnectionReferences":
[{"LogicalName", "ConnectionId", "ConnectorId"}]}. `pac solution create-settings` writes it with empty values.
A committed file may hold ${TOKENS} for what only the target environment knows (connection IDs, URLs);
render() fills them from the pipeline's variables and refuses to continue when one is missing.
"""
from __future__ import annotations

import json
import re
from typing import Mapping

TOKEN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
CONNECTION_ID = re.compile(r"^[0-9a-fA-F]{32}$|^[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")


class SettingsError(Exception):
    pass


def tokens_in(text: str) -> list[str]:
    return sorted(set(TOKEN.findall(text)))


def render(template: str, values: Mapping[str, str]) -> str:
    """Replace every ${NAME}; raise (naming all of them) when some have no value."""
    missing = [t for t in tokens_in(template) if not values.get(t)]
    if missing:
        raise SettingsError("no value for " + ", ".join(missing))

    def sub(m: re.Match) -> str:
        return json.dumps(values[m.group(1)])[1:-1]  # JSON-escaped, so a quote or backslash can't break the file

    return TOKEN.sub(sub, template)


def template_for(solution) -> dict:
    """What a settings file for this solution must contain: one entry per variable and connection reference."""
    return {
        "EnvironmentVariables": [{"SchemaName": s, "Value": ""} for s in sorted(solution.env_vars)],
        "ConnectionReferences": [
            {"LogicalName": ln, "ConnectionId": "", "ConnectorId": cid} for ln, cid in sorted(solution.conn_refs.items())
        ],
    }
