"""The tool catalog of an Azure MCP Server build.

`azmcp tools list` (Azure MCP Server 4.0.0-beta.9, measured on 21 November 2026) prints JSON:
  {"status": 200, "results": [{"command": "group list", "description": "...",
     "metadata": {"operationPlane": "control", "destructive": {"value": false, "description": "..."},
                  "readOnly": {"value": true, ...}, "secret": {...}, "openWorld": {...}, ...}}]}
The MCP tool name the server publishes is the command with spaces replaced by underscores ("group list" -> group_list).
The six annotation names are the ones Learn documents under "Tool annotations for Azure MCP Server".
https://learn.microsoft.com/azure/developer/azure-mcp-server/tools/#tool-annotations-for-azure-mcp-server
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Tool:
    command: str
    description: str
    read_only: bool
    destructive: bool
    idempotent: bool
    open_world: bool
    secret: bool
    local_required: bool

    @property
    def name(self) -> str:
        return self.command.replace(" ", "_")

    @property
    def namespace(self) -> str:
        return self.command.split(" ", 1)[0]


def _flag(meta: dict, key: str) -> bool:
    v = meta.get(key, False)
    return bool(v.get("value")) if isinstance(v, dict) else bool(v)


def parse_catalog(text: str) -> list[Tool]:
    data = json.loads(text)
    results = data["results"] if isinstance(data, dict) else data
    tools = []
    for r in results:
        meta = r.get("metadata", {})
        tools.append(Tool(
            command=r["command"], description=r.get("description", ""),
            read_only=_flag(meta, "readOnly"), destructive=_flag(meta, "destructive"),
            idempotent=_flag(meta, "idempotent"), open_world=_flag(meta, "openWorld"),
            secret=_flag(meta, "secret"), local_required=_flag(meta, "localRequired"),
        ))
    return tools


def load_catalog(path: Path) -> list[Tool]:
    return parse_catalog(path.read_text(encoding="utf-8"))


def as_command(azmcp: str) -> list[str]:
    """--azmcp can be a path to azmcp, or a command with arguments, e.g. 'node C:/tmp/azmcp/node_modules/@azure/mcp/index.js'
    (handy on Windows, where the npm shim is azmcp.cmd)."""
    return shlex.split(azmcp, posix=(os.name != "nt"))


def run_tools_list(azmcp: str, timeout: int = 120) -> str:
    """Run `azmcp tools list` (no Azure sign-in needed: it only describes the tools)."""
    proc = subprocess.run(as_command(azmcp) + ["tools", "list"], capture_output=True, text=True, timeout=timeout, check=True)
    return proc.stdout
