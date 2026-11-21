"""mcpconf: check and convert MCP server configuration files for GitHub Copilot in VS Code.

Two formats exist side by side (VS Code docs, read 21 Nov 2026):
  * editor-managed ("Local"):  .vscode/mcp.json, top-level `servers` (+ `inputs`, `sandbox`)
  * native Copilot harness:    .mcp.json (workspace root) or ~/.copilot/mcp-config.json, top-level `mcpServers`
"""
__version__ = "1.0.0"
