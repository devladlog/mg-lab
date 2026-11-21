"""A minimal MCP client over stdio: start the real azmcp server, initialize, list tools, optionally call one.

MCP's stdio transport is newline-delimited JSON-RPC 2.0 messages on the server's stdin and stdout. This client sends
`initialize`, the `notifications/initialized` notification, then `tools/list` (and `tools/call`). Listing tools needs no
Azure sign-in; calling one uses the credentials the server finds (Azure CLI, VS Code, environment...), so a call needs
the tenant.
"""
from __future__ import annotations

import json
import re
import subprocess

from .catalog import as_command

PROTOCOL = "2025-06-18"


class McpError(RuntimeError):
    pass


class StdioClient:
    def __init__(self, command: list[str], timeout: float = 90.0):
        self.proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     text=True, bufsize=1)
        self.timeout = timeout
        self._id = 0

    def _send(self, msg: dict) -> None:
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()

    def request(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        msg = {"jsonrpc": "2.0", "id": self._id, "method": method}
        if params is not None:
            msg["params"] = params
        self._send(msg)
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise McpError(f"Server closed the pipe while waiting for {method}")
            reply = json.loads(line)
            if reply.get("id") == self._id and ("result" in reply or "error" in reply):
                if "error" in reply:
                    raise McpError(f"{method}: {reply['error'].get('message')}")
                return reply["result"]
            # anything else (log notifications, server-initiated requests) is ignored by this simple client

    def notify(self, method: str) -> None:
        self._send({"jsonrpc": "2.0", "method": method})

    def initialize(self) -> dict:
        result = self.request("initialize", {"protocolVersion": PROTOCOL, "capabilities": {},
                                             "clientInfo": {"name": "azmcp-audit", "version": "0.1.0"}})
        self.notify("notifications/initialized")
        return result

    def list_tools(self) -> list[dict]:
        tools, cursor = [], None
        while True:
            result = self.request("tools/list", {"cursor": cursor} if cursor else {})
            tools += result["tools"]
            cursor = result.get("nextCursor")
            if not cursor:
                return tools

    def call(self, name: str, arguments: dict | None = None) -> dict:
        return self.request("tools/call", {"name": name, "arguments": arguments or {}})

    def close(self) -> None:
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def list_server_tools(azmcp: str, args: list[str]) -> tuple[dict, list[dict]]:
    with StdioClient(as_command(azmcp) + args) as c:
        info = c.initialize()
        return info, c.list_tools()


def call_server_tool(azmcp: str, args: list[str], name: str, arguments: dict) -> dict:
    with StdioClient(as_command(azmcp) + args) as c:
        c.initialize()
        return c.call(name, arguments)


def namespace_surface(azmcp: str, args: list[str]) -> tuple[list[str], set[str]]:
    """Start the server in --mode namespace and return (published tool names, every command reachable through them).

    In namespace mode the server publishes one tool per namespace (with the parameters intent, command, parameters, learn).
    Calling it with learn=true lists the commands behind it without executing anything. Tools without those parameters
    (group_list, subscription_list, ...) are single commands and count as themselves.
    """
    with StdioClient(as_command(azmcp) + args) as c:
        c.initialize()
        published = c.list_tools()
        commands: set[str] = set()
        for t in published:
            props = set(t.get("inputSchema", {}).get("properties", {}))
            if {"intent", "command", "learn"} <= props:
                text = c.call(t["name"], {"learn": True})["content"][0]["text"]
                commands |= set(re.findall(r'"command":"([a-z0-9_\-]+)"', text))
            else:
                commands.add(t["name"])
        return [t["name"] for t in published], commands
