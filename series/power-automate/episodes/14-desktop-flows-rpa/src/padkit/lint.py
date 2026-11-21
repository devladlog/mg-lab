"""Rules on the text a desktop flow copies as (Power Automate for desktop: select actions, copy).

Rules and where they come from (Microsoft Learn):
  PAD001  a declared output is never assigned: the cloud flow would read an empty value
  PAD002  a literal value is put into a variable that looks like a secret ("Sensitive variables are not meant to
          protect hard-coded data ... you shouldn't hardcode critical data in plain text")
  PAD003  a message dialog in a flow that also runs unattended ("Unattended desktop flows keep the screen locked")
  PAD004  free text (an input) pasted into script text: "Include variables in the script because they evaluate before
          the script runs", i.e. the text becomes code
"""
from __future__ import annotations

import re

from .contract import Finding

SECRET_NAME = re.compile(r"(passw|pwd|secret|token|apikey|api_key|connectionstring)", re.I)
SET_RE = re.compile(r"^\s*SET\s+(\w+)\s+TO\s+(.*)$")
ASSIGN_RE = re.compile(r"=>\s*(\w+)")
SCRIPT_RE = re.compile(r"^\s*Scripting\.Run\w+\.Run\w+\b")
LITERAL_RE = re.compile(r"^\$'''(.*)'''\s*$")
DISPLAY_RE = re.compile(r"^\s*Display\.\w+")


def _logical_lines(text: str):
    for n, line in enumerate(text.splitlines(), start=1):
        if line.strip() and not line.lstrip().startswith("#"):
            yield n, line


def lint_script(text: str, contract: dict, run_mode: str = "attended") -> list[Finding]:
    out: list[Finding] = []
    assigned: set[str] = set()
    inputs = {i["name"] for i in contract["inputs"]}
    for n, line in _logical_lines(text):
        m = SET_RE.match(line)
        if m:
            name, value = m.groups()
            assigned.add(name)
            lit = LITERAL_RE.match(value.strip())
            if SECRET_NAME.search(name) and lit and lit.group(1) and not re.fullmatch(r"%\w+%", lit.group(1)):
                out.append(Finding("error", "PAD002", f"line {n}", f"'{name}' gets a hard-coded value; use a sensitive input or a credential"))
        assigned.update(ASSIGN_RE.findall(line))
        if DISPLAY_RE.match(line) and run_mode == "unattended":
            out.append(Finding("error", "PAD003", f"line {n}", "a message dialog cannot be answered in an unattended run"))
        if SCRIPT_RE.match(line):
            script = line.split("Script:", 1)[-1]
            for var in re.findall(r"%([A-Za-z_]\w*)", script):
                if var in inputs:
                    out.append(Finding("error", "PAD004", f"line {n}",
                                       f"input '{var}' is pasted into script text before it runs: write it to a file and read the file"))
    for o in contract["outputs"]:
        if o["name"] not in assigned:
            out.append(Finding("error", "PAD001", "script", f"output '{o['name']}' is never assigned"))
    return out
