"""What a data policy can't see: an allowed connector sending data to the wrong place.

Learn: data policies "are connector aware, but they don't control connections made using the connector".
So a flow that only uses SharePoint and Outlook passes every policy, and can still email a list to
someone outside the company. This rule reads the literal recipients of Outlook "Send an email (V2)".
Recipients that come from an expression or an environment variable can't be read statically; they are
listed as not checked, never as safe.
"""
from __future__ import annotations

import re

from flowkit.lint import Finding, definition_of, iter_actions

SEND_OPS = {"SendEmailV2"}
RECIPIENT_KEYS = ("emailMessage/To", "emailMessage/Cc", "emailMessage/Bcc")
_ADDR = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)")
_INTERP = re.compile(r"@\{.*?\}")


def external_recipients(flow: dict, allowed_domains: set[str]) -> tuple[list[Finding], list[str]]:
    allowed = {d.lower().lstrip("@") for d in allowed_domains}
    findings: list[Finding] = []
    unchecked: list[str] = []
    for name, action, *_ in iter_actions(definition_of(flow).get("actions") or {}):
        inputs = action.get("inputs") if isinstance(action.get("inputs"), dict) else {}
        if (inputs.get("host") or {}).get("operationId") not in SEND_OPS:
            continue
        params = inputs.get("parameters") or {}
        for key in RECIPIENT_KEYS:
            value = params.get(key)
            if not isinstance(value, str) or not value:
                continue
            if value.startswith("@"):               # a pure expression: @parameters(...), @triggerBody()...
                unchecked.append(f"{name}: {key} comes from an expression")
                continue
            for m in _ADDR.finditer(_INTERP.sub("", value)):
                domain = m.group(1).lower()
                if not any(domain == a or domain.endswith("." + a) for a in allowed):
                    findings.append(Finding("warning", f"actions.{name}", f"{key} sends to {m.group(0)}, outside "
                                            f"{', '.join(sorted(allowed))}: a data policy can't see this"))
    return findings, unchecked
