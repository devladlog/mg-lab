"""Read, lint and render a database CONSTITUTION.md for GitHub Copilot in SSMS.

Learn ("Execution context for GitHub Copilot in SQL Server Management Studio"): the constitution is stored as the
database-level extended property named CONSTITUTION.md; its YAML front matter may hold agentExecuteAsUser, the database
user or SQL login that SSMS impersonates (EXECUTE AS) for every Copilot query on that database. Learn's advice:
a dedicated low-privilege account, never sa, dbo or another highly privileged account.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_FRONT = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)(.*)\Z", re.DOTALL)

# names that are, or are conventionally, highly privileged (Learn names sa and dbo; the rest is our judgement)
PRIVILEGED_NAMES = {"sa", "dbo", "sys", "information_schema", "guest", "public", "db_owner", "sysadmin", "securityadmin",
                    "serveradmin", "setupadmin", "processadmin", "diskadmin", "dbcreator", "bulkadmin"}


# Learn, sp_addextendedproperty: "The size of @value can't be more than 7,500 bytes" (the parameter is sql_variant)
MAX_VALUE_BYTES = 7500


@dataclass
class Constitution:
    front: dict[str, str]
    body: str

    @property
    def execute_as_user(self) -> str | None:
        v = self.front.get("agentExecuteAsUser")
        return v.strip() if v else None


def parse_constitution(text: str) -> Constitution:
    text = text.lstrip("﻿")
    m = _FRONT.match(text)
    if not m:
        return Constitution({}, text)
    front: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            raise ValueError(f"front matter line is not 'key: value': {line!r}")
        k, v = line.split(":", 1)
        front[k.strip()] = v.strip().strip("'\"")
    return Constitution(front, m.group(2))


def lint_constitution(text: str) -> list[str]:
    """Return a list of problems (empty list = ok)."""
    problems: list[str] = []
    try:
        c = parse_constitution(text)
    except ValueError as e:
        return [str(e)]
    user = c.execute_as_user
    if not c.front:
        problems.append("no YAML front matter: agentExecuteAsUser is only read from the front matter, so Copilot "
                        "will run queries as the signed-in user")
    elif user is None:
        problems.append("front matter has no agentExecuteAsUser")
    else:
        bare = user.strip("[]")
        if bare.lower() in PRIVILEGED_NAMES:
            problems.append(f"agentExecuteAsUser is '{bare}': Learn says not to use sa, dbo or other highly "
                            "privileged accounts")
        if re.search(r"admin|owner|root", bare, re.IGNORECASE):
            problems.append(f"agentExecuteAsUser '{bare}' looks privileged by name: check its permissions")
    unknown = set(c.front) - {"agentExecuteAsUser"}
    if unknown:
        problems.append("front matter keys not documented on Learn (ignored by SSMS as far as we know): "
                        + ", ".join(sorted(unknown)))
    size = len(text.replace("\r\n", "\n").rstrip("\n").encode("utf-16-le"))
    if size > MAX_VALUE_BYTES:
        problems.append(f"the constitution is {size} bytes as nvarchar; sp_addextendedproperty accepts at most "
                        f"{MAX_VALUE_BYTES} bytes in @value (Learn), so it cannot be stored as is")
    if not c.body.strip():
        problems.append("empty body: add the coding standards and restricted operations Copilot must follow")
    return problems


def _quote_literal(value: str) -> str:
    return "N'" + value.replace("'", "''") + "'"


def render_tsql(text: str, database: str, update: bool = False) -> str:
    """The T-SQL that stores the constitution, as in Learn (sp_addextendedproperty / sp_updateextendedproperty)."""
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", database):
        raise ValueError("database name: letters, digits and underscore only (the script uses it in USE [...])")
    proc = "sp_updateextendedproperty" if update else "sp_addextendedproperty"
    body = text.lstrip("﻿").replace("\r\n", "\n").rstrip("\n")
    return (f"USE [{database}];\nGO\n"
            f"EXECUTE {proc}\n    @name = N'CONSTITUTION.md',\n    @value = {_quote_literal(body)};\nGO\n")
