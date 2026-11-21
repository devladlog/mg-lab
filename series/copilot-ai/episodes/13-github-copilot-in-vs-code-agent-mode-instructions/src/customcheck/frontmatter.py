"""Split an optional YAML header (between --- lines) from the Markdown body."""
from __future__ import annotations

from dataclasses import dataclass

import yaml


@dataclass
class Parsed:
    meta: dict | None  # None when there is no header
    body: str
    error: str | None = None


def parse(text: str) -> Parsed:
    text = text.lstrip("﻿")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return Parsed(None, text)
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            header = "\n".join(lines[1:index])
            body = "\n".join(lines[index + 1 :]).lstrip("\n")
            try:
                meta = yaml.safe_load(header) if header.strip() else {}
            except yaml.YAMLError as exc:
                return Parsed({}, body, f"invalid YAML header: {str(exc).splitlines()[0]}")
            if not isinstance(meta, dict):
                return Parsed({}, body, "YAML header is not a mapping")
            return Parsed(meta, body)
    return Parsed({}, text, "YAML header is not closed with ---")
