"""tsql_gate: a review gate for T-SQL that an AI assistant (or anyone) wrote, run BEFORE you press Execute.

It is a second pair of eyes, not a security boundary. The boundary is SQL Server's permission system: see
sql/02-copilot-user.sql and CONSTITUTION.md (agentExecuteAsUser)."""

from .gate import Finding, check_text, check_file, Severity, exit_code  # noqa: F401
from .constitution import parse_constitution, lint_constitution, render_tsql  # noqa: F401

__version__ = "1.0.0"
