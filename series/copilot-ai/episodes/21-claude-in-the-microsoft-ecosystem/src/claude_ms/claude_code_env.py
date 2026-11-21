"""Environment activators that point Claude Code at Foundry deployments.

Variables are the ones Learn documents in "Configure Claude Code for Microsoft Foundry":
CLAUDE_CODE_USE_FOUNDRY=1, ANTHROPIC_FOUNDRY_RESOURCE (or ANTHROPIC_FOUNDRY_BASE_URL) and
ANTHROPIC_DEFAULT_{SONNET,HAIKU,OPUS}_MODEL. No API key is ever written: sign in with `az login` (Microsoft Entra ID)
or set ANTHROPIC_FOUNDRY_API_KEY yourself.
"""
from __future__ import annotations

from typing import Optional

from .client import resolve_resource

FAMILIES = ("sonnet", "haiku", "opus")


def build_env(resource: str, models: Optional[dict] = None) -> dict:
    name = resolve_resource(resource, env={})
    env = {"CLAUDE_CODE_USE_FOUNDRY": "1", "ANTHROPIC_FOUNDRY_RESOURCE": name}
    for family, deployment in (models or {}).items():
        if family not in FAMILIES:
            raise ValueError(f"unknown family '{family}', expected one of {', '.join(FAMILIES)}")
        if not deployment or any(c.isspace() or c in "\"'$`" for c in deployment):
            raise ValueError(f"bad deployment name for {family}: {deployment!r}")
        env[f"ANTHROPIC_DEFAULT_{family.upper()}_MODEL"] = deployment
    return env


def render(env: dict, shell: str) -> str:
    if shell == "bash":
        lines = ["# Claude Code on Microsoft Foundry. Sign in with: az login (Microsoft Entra ID)."]
        lines += [f'export {k}="{v}"' for k, v in env.items()]
    elif shell == "powershell":
        lines = ["# Claude Code on Microsoft Foundry. Sign in with: az login (Microsoft Entra ID)."]
        lines += [f'$env:{k} = "{v}"' for k, v in env.items()]
    else:
        raise ValueError("shell must be 'bash' or 'powershell'")
    return "\n".join(lines) + "\n"
