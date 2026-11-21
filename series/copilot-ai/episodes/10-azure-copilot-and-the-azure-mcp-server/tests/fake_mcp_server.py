"""Test helper: a tiny stdio MCP server (newline-delimited JSON-RPC) used ONLY to test the client in probe.py offline.
The demo never uses it: the episode records the real azmcp server."""
import json
import sys

TOOLS = [{"name": "group_list", "annotations": {"readOnlyHint": True}}, {"name": "subscription_list", "annotations": {"readOnlyHint": True}}]
for line in sys.stdin:
    msg = json.loads(line)
    if "id" not in msg:
        continue
    if msg["method"] == "initialize":
        result = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}, "serverInfo": {"name": "fake", "version": "0"}}
        print(json.dumps({"jsonrpc": "2.0", "method": "notifications/message", "params": {"data": "noise"}}), flush=True)
    elif msg["method"] == "tools/list":
        if msg["params"].get("cursor") == "p2":
            result = {"tools": [TOOLS[1]]}
        else:
            result = {"tools": [TOOLS[0]], "nextCursor": "p2"}
    elif msg["method"] == "tools/call":
        if msg["params"]["name"] == "boom":
            print(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32000, "message": "boom failed"}}), flush=True)
            continue
        result = {"content": [{"type": "text", "text": json.dumps(msg["params"]["arguments"])}]}
    else:
        result = {}
    print(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": result}), flush=True)
